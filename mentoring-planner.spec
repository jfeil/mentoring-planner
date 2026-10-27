# PyInstaller build for the planner, so a double-clickable exe can be released.
#
#   uv run pyinstaller mentoring-planner.spec
#
# The static pages are data files, and solver/static is loaded with
# importlib.resources, so they have to be collected next to the module.

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[("solver/static", "solver/static")],
    hiddenimports=["solver", "solver.app", "solver.report", "solver.scaffold", "solver.sample"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mentoring-planner",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # the shell messages are part of the tool; --app still opens a window
)
