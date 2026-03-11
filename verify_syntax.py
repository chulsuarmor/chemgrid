import py_compile, os
files = [
    'c:/chemgrid/src/app/renderer.py',
    'c:/chemgrid/src/app/canvas.py',
    'c:/chemgrid/src/app/main_window.py',
    'c:/chemgrid/src/app/analyzer.py',
    'c:/chemgrid/src/app/spectrum_pdf_exporter.py',
]
for f in files:
    name = os.path.basename(f)
    try:
        py_compile.compile(f, doraise=True)
        print(f"[OK] {name}")
    except py_compile.PyCompileError as e:
        print(f"[ERR] {name}: {e}")
