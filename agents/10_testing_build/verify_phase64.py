"""
Phase 6-4 검증 스크립트
STEP 1: AST 구문 검증
STEP 2: ChemDraw 잔존 확인
STEP 3: Import 의존성 검증
"""
import ast
import os
import sys
import importlib

INTEGRATED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integrated")

print("=" * 60)
print("STEP 1: AST 구문 검증")
print("=" * 60)

ok = 0
fail = 0
py_files = sorted([f for f in os.listdir(INTEGRATED) if f.endswith('.py')])
for f in py_files:
    path = os.path.join(INTEGRATED, f)
    try:
        with open(path, encoding='utf-8') as fh:
            ast.parse(fh.read())
        print(f"  ✅ {f}")
        ok += 1
    except SyntaxError as e:
        print(f"  ❌ {f}: {e}")
        fail += 1

print(f"\nAST: {ok} OK, {fail} FAIL")
ast_pass = (fail == 0)

print()
print("=" * 60)
print("STEP 2: ChemDraw 잔존 확인")
print("=" * 60)

chemdraw_found = 0
for f in py_files:
    path = os.path.join(INTEGRATED, f)
    with open(path, encoding='utf-8') as fh:
        content = fh.read()
    for i, line in enumerate(content.split('\n'), 1):
        if 'ChemDraw' in line or 'chemdraw' in line or 'CHEMDRAW' in line:
            # 주석이나 문자열 내 히스토리 참조는 제외
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            print(f"  ⚠️ {f}:{i}: {stripped[:80]}")
            chemdraw_found += 1

if chemdraw_found == 0:
    print("  ✅ ChemDraw 잔존 0건")
else:
    print(f"\n  ⚠️ ChemDraw 잔존 {chemdraw_found}건 — 교체 필요")

print()
print("=" * 60)
print("STEP 3: Import 의존성 검증")
print("=" * 60)

# integrated 디렉토리를 sys.path에 추가
sys.path.insert(0, INTEGRATED)

# PyQt6 필요 없는 순수 Python 모듈만 테스트
pure_modules = [
    'chem_data', 'coord_utils', 'engine_core', 'engine_physics', 'engine_resonance',
]

# PyQt6 필요한 모듈
qt_modules = [
    'ui_utils', 'renderer', 'analyzer', 'orca_interface',
    'electron_density_analyzer', 'base_spectrum', 'lasso_selection',
    'error_handler', 'calculation_logger', 'history_manager',
    'batch_processor', 'molecule_comparator', 'iupac_analyzer',
    'export_manager_enhanced', 'progress_tracker',
]

import_ok = 0
import_fail = 0

for m in pure_modules + qt_modules:
    try:
        mod = importlib.import_module(m)
        print(f"  ✅ {m}")
        import_ok += 1
    except Exception as e:
        err_msg = str(e)[:60]
        print(f"  ❌ {m}: {err_msg}")
        import_fail += 1

print(f"\nImport: {import_ok} OK, {import_fail} FAIL")

print()
print("=" * 60)
print("최종 결과")
print("=" * 60)
print(f"  AST: {ok}/{ok+fail} ({'✅ PASS' if ast_pass else '❌ FAIL'})")
print(f"  ChemDraw 잔존: {chemdraw_found}건 ({'✅ CLEAN' if chemdraw_found == 0 else '⚠️ 교체 필요'})")
print(f"  Import: {import_ok}/{import_ok+import_fail}")

if not ast_pass:
    sys.exit(1)
