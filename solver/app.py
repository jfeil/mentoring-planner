"""A small browser front end, so the planner works without a shell.

One page, two cards: plan an existing workbook (upload it, get the planned one back)
and create a new one (which classes, how many groups each, which topics, which weeks,
then a grid to mark the trips in).

Only the standard library is used, so the packaged executable stays small, and the
server binds to localhost: it handles the files of the person sitting at this machine.
"""

from __future__ import annotations

import datetime
import http.server
import re
import socketserver
import tempfile
import urllib.parse
import webbrowser
from importlib import resources
from pathlib import Path

from solver import UnfeasibleError, WorkbookError, load_workbook, solve
from solver.report import write_plan
from solver.scaffold import Spec, example_trips, group_names, mondays, parse_classes, write_scaffold

MAX_UPLOAD = 8 * 1024 * 1024  # a mentoring workbook is a few hundred kilobytes


def serve(bind: str = "127.0.0.1", port: int = 0, open_browser: bool = True) -> int:
    """Serve the front end until stopped. Returns the exit status."""

    try:
        server = _Server((bind, port), _Handler)
    except OSError:
        if not port:
            raise
        print(f"port {port} is busy, taking another one")
        server = _Server((bind, 0), _Handler)
    address = f"http://{bind}:{server.server_address[1]}/"
    print(f"mentoring planner listening on {address}")
    print("press Ctrl+C to stop")
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mentoring-planner"

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        params = urllib.parse.parse_qs(query)
        if route == "/":
            self._html(_page("index.html", error=""))
        elif route == "/template":
            self._template_page(params)
        else:
            self._html(_page("index.html", error=_error("Nothing here: " + route)), status=404)

    def do_POST(self) -> None:
        route, _, query = self.path.partition("?")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            self._html(_page("index.html", error=_error("that file is too large")), status=400)
            return
        body = self.rfile.read(length)
        if route == "/plan":
            self._plan(body)
        elif route == "/template/create":
            params = urllib.parse.parse_qs(body.decode("utf-8", "replace"))
            self._template_download(params)
        else:
            self._html(_page("index.html", error=_error("Nothing here: " + route)), status=404)

    # -- the two jobs ----------------------------------------------------------

    def _plan(self, body: bytes) -> None:
        fields = _multipart(body, self.headers.get("Content-Type") or "")
        upload = fields.get("workbook")
        name, data = upload if upload else ("", b"")
        if not name:
            self._html(_page("index.html", error=_error("no workbook was uploaded")), status=400)
            return
        if not name.lower().endswith((".xlsx", ".xlsm")):
            self._html(
                _page("index.html", error=_error(f"'{name}' is not an .xlsx workbook")), status=400
            )
            return
        if not data:
            self._html(_page("index.html", error=_error(f"'{name}' is empty")), status=400)
            return
        try:
            planned = _plan_bytes(data)
        except (WorkbookError, UnfeasibleError) as error:
            self._html(_page("index.html", error=_error(str(error))), status=400)
            return
        except Exception as error:  # a broken sheet should never close the window
            self._html(_page("index.html", error=_error(f"{type(error).__name__}: {error}")), 500)
            return
        self._xlsx(planned, _swap(name, "planned"))

    def _template_page(self, params: dict[str, list[str]]) -> None:
        try:
            spec = _spec_from_form(params)
        except (ValueError, WorkbookError) as error:
            self._html(_page("index.html", error=_error(str(error))), status=400)
            return
        self._html(_template_page(spec))

    def _template_download(self, params: dict[str, list[str]]) -> None:
        try:
            spec = _spec_from_form(params)
        except (ValueError, WorkbookError) as error:
            self._html(_page("index.html", error=_error(str(error))), status=400)
            return
        try:
            _apply_settings(spec, params)
            _apply_trips(spec, params)
        except (ValueError, WorkbookError) as error:
            self._html(_template_page(spec, error=str(error)), status=400)
            return
        with tempfile.TemporaryDirectory() as folder:
            path = write_scaffold(Path(folder) / "template.xlsx", spec)
            if not (params.get("plan") or [""])[0]:
                self._xlsx(path.read_bytes(), "mentoring-template.xlsx")
                return
            try:
                planned = _plan_bytes(path.read_bytes())
            except (WorkbookError, UnfeasibleError) as error:
                self._html(_template_page(spec, error=str(error)), status=400)
                return
            self._xlsx(planned, "mentoring-plan.xlsx")

    # -- plumbing --------------------------------------------------------------

    def _html(self, page: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def _xlsx(self, data: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # quieter than the default
        if not self.path.startswith("/favicon"):
            super().log_message(format, *args)


def _plan_bytes(data: bytes) -> bytes:
    """The planner over an uploaded workbook; the result comes back as bytes."""

    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "input.xlsx"
        source.write_bytes(data)
        workbook = load_workbook(source)
        plan = solve(workbook)
        write_plan(source, workbook, plan)
        return source.read_bytes()


def _spec_from_form(params: dict[str, list[str]]) -> Spec:
    """The classes, topics and weeks of the generator form."""

    def one(key: str, default: str = "") -> str:
        return (params.get(key) or [default])[0].strip()

    tutored = parse_classes(one("classes").split())
    if not tutored:
        raise ValueError("name at least one class, e.g. 6a:2 6b:2")
    topics = one("topics").split()
    if not topics:
        raise ValueError("name at least one topic, e.g. Reading Maths")
    dates = _dates(one("start"), int(one("count", "10")))
    return Spec(
        tutored=tutored,
        peer_classes=one("peer_classes").split(),
        topics=topics,
        weeks=[date.isocalendar()[1] for date in dates],
        week_dates=dates,
    )


def _dates(start: str, count: int) -> list[datetime.date]:
    """The Mondays of the weeks the form asks for."""

    if count < 1 or count > 53:
        raise ValueError("the number of weeks has to be between 1 and 53")
    try:
        first = datetime.date.fromisoformat(start)
    except ValueError:
        raise ValueError(f"'{start}' is not a date") from None
    return mondays(first, count)


def _apply_settings(spec: Spec, params: dict[str, list[str]]) -> None:
    def number(key: str) -> int | None:
        value = (params.get(key) or [""])[0].strip()
        if not value:
            return None
        if not value.isdigit() or not 0 < int(value) < 100:
            raise ValueError(f"'{key}' needs a number between 1 and 99, or nothing")
        return int(value)

    spec.peer_cap = number("peer_cap")
    spec.group_week_cap = number("group_week_cap")
    text = (params.get("blackouts") or [""])[0]
    weeks = set(spec.weeks)
    blackouts = {int(part) for part in re.findall(r"\d{1,2}", text)}
    unknown = sorted(blackouts - weeks)
    if unknown:
        raise ValueError(
            "blackout weeks " + ", ".join(map(str, unknown)) + " are outside the weeks of this sheet ("
            + ", ".join(map(str, sorted(weeks))) + ")"
        )
    spec.blackouts = sorted(blackouts)


def _apply_trips(spec: Spec, params: dict[str, list[str]]) -> None:
    """The ticked 'class:week' boxes from the grid."""

    trips: dict[str, list[int]] = {}
    for mark in params.get("trip", []):
        cls, _, week = mark.partition(":")
        if not week.isdigit():
            raise ValueError(f"'{mark}' is not a class and a week")
        trips.setdefault(cls, []).append(int(week))
    spec.trips = trips


def _template_page(spec: Spec, error: str = "") -> bytes:
    """The grid: one row per class, one column per week."""

    labels = [
        f'<th class="week">W{week}<span>{_monday(spec, index)}</span></th>'
        for index, (week) in enumerate(spec.weeks)
    ]
    rows = []
    for cls, kind in _grid_classes(spec):
        marks = _example(spec, cls)
        cells = [
            f'<td class="{kind}"><input type="checkbox" name="trip" value="{cls}:{week}"'
            f"{_tick(week in marks)}></td>"
            for week in spec.weeks
        ]
        note = "peers" if kind == "peer" else "tutored"
        rows.append(f'<tr><th class="cls">{cls} <span class="hint">({note})</span></th>{"".join(cells)}</tr>')
    fields = "".join(
        f'<input type=hidden name="{key}" value="{urllib.parse.quote(value)}">'
        for key, value in [
            ("classes", " ".join(f"{cls}:{splits}" for cls, splits in spec.tutored)),
            ("peer_classes", " ".join(spec.peer_classes)),
            ("topics", " ".join(spec.topics)),
            ("start", spec.week_dates[0].isoformat()),
            ("count", str(len(spec.weeks))),
        ]
    )
    groups = ", ".join(name for name, _cls in group_names(spec))
    summary = (
        f"<b>{len(spec.tutored)}</b> class(es) &rarr; <b>{len(group_names(spec))}</b> groups: {groups}. "
        f"<b>{len(spec.topics)}</b> topic(s): {', '.join(spec.topics)}. "
        f"<b>{len(spec.weeks)}</b> weeks: {', '.join('W%d' % w for w in spec.weeks)}."
    )
    return _page(
        "template.html",
        error=_error(error) if error else "",
        weeks="".join(labels),
        grid="\n".join(rows),
        fields=fields,
        summary=summary,
        blackouts="",
        week_list=", ".join(str(w) for w in spec.weeks[:4]) + ", ...",
    )


def _grid_classes(spec: Spec) -> list[tuple[str, str]]:
    tutored = [cls for cls, _splits in spec.tutored]
    return [(cls, "tutored") for cls in tutored] + [
        (cls, "peer") for cls in spec.peer_classes if cls not in tutored
    ]


def _tick(marked: bool) -> str:
    return " checked" if marked else ""


def _example(spec: Spec, cls: str) -> set[int]:
    """The pre-ticked marks, so the grid matches the workbook that gets written."""

    return set((spec.trips or example_trips(spec)).get(cls, ()))


def _monday(spec: Spec, index: int) -> str:
    """The weekday label under a week column, e.g. '26 Oct'."""

    if not spec.week_dates or index >= len(spec.week_dates):
        return ""
    return spec.week_dates[index].strftime("%d %b").lstrip("0")


def _page(name: str, **values) -> bytes:
    """A page shell from solver/static, with the {{placeholders}} filled in."""

    try:
        text = (resources.files("solver") / "static" / name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):  # a bundle built without --add-data
        text = "<!doctype html><meta charset=utf-8><title>Mentoring planner</title>" \
               "<p>The pages of the front end were not bundled with this executable.</p>"
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text.encode("utf-8")


def _error(message: str) -> str:
    return f'<div class="error">{_escape(message)}</div>'


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _multipart(body: bytes, content_type: str) -> dict[str, tuple[str, bytes]]:
    """Parse a form upload into {field: (filename, value)}."""

    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        return {}
    boundary = b"--" + match.group(1).encode()
    fields: dict[str, tuple[str, bytes]] = {}
    for chunk in body.split(boundary)[1:-1]:
        head, _, value = chunk.lstrip(b"\r\n").partition(b"\r\n\r\n")
        disposition = head.decode("utf-8", "replace")
        name = re.search(r'name="([^"]*)"', disposition)
        if not name:
            continue
        filename = re.search(r'filename="([^"]*)"', disposition)
        fields[name.group(1)] = (filename.group(1) if filename else "", value.rstrip(b"\r\n"))
    return fields


def _swap(filename: str, word: str) -> str:
    """input.xlsx -> input-planned.xlsx, so the download is recognisable."""

    stem = filename.rsplit(".", 1)[0] or "workbook"
    return f"{stem}-{word}.xlsx"
