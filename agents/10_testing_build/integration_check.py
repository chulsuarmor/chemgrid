"""통합 전 에이전트 산출물 라인 수 확인 및 AST 구문 검증"""
import os
import ast

files = [
    r"c:\chemgrid\agents\02_canvas_interaction\draw.py",
    r"c:\chemgrid\agents\02_canvas_interaction\canvas.py",
    r"c:\chemgrid\agents\02_canvas_interaction\coord_utils.py",
    r"c:\chemgrid\agents\02_canvas_interaction\chem_data.py",
    r"c:\chemgrid\agents\07_orca_dft\orca_interface.py",
    r"c:\chemgrid\agents\07_orca_dft\electron_density_analyzer.py",
    r"c:\chemgrid\agents\05_rendering_engine\renderer.py",
    r"c:\chemgrid\agents\05_rendering_engine\coord_utils.py",
    r"c:\chemgrid\agents\05_rendering_engine\layer_logic.py",
    r"c:\chemgrid\agents\03_lewis_structure\layer_logic.py",
    r"c:\chemgrid\agents\03_lewis_structure\lasso_selection.py",
    r"c:\chemgrid\agents\03_lewis_structure\analyzer.py",
    r"c:\chemgrid\agents\04_analysis_engine\analyzer.py",
    r"c:\chemgrid\agents\04_analysis_engine\engine_core.py",
    r"c:\chemgrid\agents\04_analysis_engine\engine_physics.py",
    r"c:\chemgrid\agents\04_analysis_engine\engine_resonance.py",
]

print("=" * 70)
print("에이전트 산출물 라인 수 및 AST 검증")
print("=" * 70)

for f in files:
    if not os.path.exists(f):
        print(f"  MISSING  {f}")
        continue
    
    with open(f, encoding="utf-8") as fh:
        content = fh.read()
    lines = content.count("\n") + 1
    
    try:
        ast.parse(content)
        status = "OK"
    except SyntaxError as e:
        status = f"SYNTAX ERROR: {e}"
    
    agent = os.path.basename(os.path.dirname(f))
    fname = os.path.basename(f)
    print(f"  {status:8s}  {lines:5d} lines  {agent}/{fname}")

print("=" * 70)

# 원본 소스와 비교 (라인 수만)
print("\n원본 _source 파일 라인 수:")
source_files = [
    "draw.py", "orca_interface.py", "renderer.py", "layer_logic.py",
    "analyzer.py", "engine_core.py", "engine_physics.py", "engine_resonance.py",
    "coord_utils.py", "chem_data.py", "electron_density_analyzer.py",
]
for fname in source_files:
    fpath = os.path.join(r"c:\chemgrid\_source", fname)
    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as fh:
            lines = fh.read().count("\n") + 1
        print(f"  {lines:5d} lines  _source/{fname}")
