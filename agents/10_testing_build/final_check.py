"""Phase 6-4 최종 재검증 스크립트"""
import ast, os, sys

INTEGRATED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integrated")
ROOT_EXE = r"c:\chemgrid\ChemGrid.exe"

print("=" * 60)
print("Phase 6-4 최종 재검증")
print("=" * 60)

# 1. AST
print("\n[1] AST 구문 검증")
py_files = sorted([f for f in os.listdir(INTEGRATED) if f.endswith('.py')])
ast_ok = ast_fail = 0
for f in py_files:
    try:
        with open(os.path.join(INTEGRATED, f), encoding='utf-8') as fh:
            ast.parse(fh.read())
        ast_ok += 1
    except SyntaxError as e:
        print(f"  FAIL: {f}: {e}")
        ast_fail += 1
print(f"  AST: {ast_ok}/{ast_ok+ast_fail} {'PASS' if ast_fail==0 else 'FAIL'}")

# 2. ChemDraw 잔존
print("\n[2] ChemDraw 잔존 확인")
cd_count = 0
for f in py_files:
    with open(os.path.join(INTEGRATED, f), encoding='utf-8') as fh:
        for i, line in enumerate(fh, 1):
            for kw in ['ChemDraw', 'chemdraw', 'CHEMDRAW']:
                if kw in line:
                    print(f"  FOUND: {f}:{i}: {line.strip()[:80]}")
                    cd_count += 1
print(f"  ChemDraw 잔존: {cd_count}건 {'CLEAN' if cd_count==0 else 'DIRTY'}")

# 3. exe 존재
print("\n[3] ChemGrid.exe 확인")
if os.path.exists(ROOT_EXE):
    sz = os.path.getsize(ROOT_EXE) / (1024*1024)
    print(f"  ChemGrid.exe: {sz:.1f} MB - OK")
else:
    print(f"  ChemGrid.exe: NOT FOUND")

# 4. v4 핵심 파일 존재 + 크기
print("\n[4] v4 핵심 파일 크기")
v4_files = ['draw.py','main_window.py','toolbar_setup.py','canvas.py','coord_utils.py','renderer.py','popup_3d.py']
for f in v4_files:
    p = os.path.join(INTEGRATED, f)
    if os.path.exists(p):
        sz = os.path.getsize(p)
        print(f"  {f:<25} {sz:>8} bytes")
    else:
        print(f"  {f:<25} MISSING!")

# 5. 총괄
print("\n" + "=" * 60)
all_ok = (ast_fail == 0) and (cd_count == 0) and os.path.exists(ROOT_EXE)
print(f"결과: {'ALL PASS' if all_ok else 'ISSUES FOUND'}")
print("=" * 60)
