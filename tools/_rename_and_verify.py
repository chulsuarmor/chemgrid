"""ChemDraw→ChemGrid 교체 + AST 검증 스크립트"""
import os, ast

folder = r'c:\chemgrid\agents\10_testing_build\integrated'

# Step 1: ChemDraw → ChemGrid 교체
print("=== ChemDraw → ChemGrid 교체 ===")
changed = []
for f in sorted(os.listdir(folder)):
    if not f.endswith('.py'):
        continue
    path = os.path.join(folder, f)
    content = open(path, encoding='utf-8').read()
    new = content.replace('ChemDraw Pro', 'ChemGrid').replace('ChemDraw', 'ChemGrid').replace('chemdraw', 'chemgrid').replace('chemDraw', 'chemGrid').replace('CHEMDRAW', 'CHEMGRID')
    if content != new:
        open(path, 'w', encoding='utf-8').write(new)
        changed.append(f)
        print(f"  V {f}")

if not changed:
    print("  (이미 교체 완료)")
else:
    print(f"  총 {len(changed)}개 파일 교체")

# Step 2: 잔존 확인
print("\n=== ChemDraw 잔존 확인 ===")
remain = []
for f in sorted(os.listdir(folder)):
    if not f.endswith('.py'):
        continue
    c = open(os.path.join(folder, f), encoding='utf-8').read()
    if 'ChemDraw' in c or 'chemdraw' in c or 'chemDraw' in c:
        remain.append(f)
if remain:
    for r in remain:
        print(f"  X {r}")
else:
    print("  OK - 잔존 없음")

# Step 3: AST 검증
print("\n=== AST 구문 검증 ===")
ok = fail = 0
for f in sorted(os.listdir(folder)):
    if not f.endswith('.py'):
        continue
    try:
        ast.parse(open(os.path.join(folder, f), encoding='utf-8').read())
        ok += 1
    except SyntaxError as e:
        print(f"  X {f}: {e}")
        fail += 1
print(f"  AST: {ok} OK, {fail} FAIL")

# Step 4: 누락 파일 확인
print("\n=== 핵심 파일 존재 확인 ===")
essential = ['draw.py', 'canvas.py', 'renderer.py', 'analyzer.py', 'popup_3d.py',
             'layer_logic.py', 'coord_utils.py', 'chem_data.py', 'orca_interface.py']
for e in essential:
    exists = os.path.exists(os.path.join(folder, e))
    print(f"  {'V' if exists else 'X'} {e}")
