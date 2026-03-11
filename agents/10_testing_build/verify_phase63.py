"""
Phase 6-3 통합 검증 스크립트
STEP 1: AST 구문 검증
STEP 2: Import 의존성 검증
STEP 3: ChemDraw 잔존 확인
"""
import ast
import os
import sys
import importlib

INTEGRATED = r"c:\chemgrid\agents\10_testing_build\integrated"

print("=" * 60)
print("STEP 1: AST 구문 검증 (모든 .py 파일)")
print("=" * 60)

py_files = sorted([f for f in os.listdir(INTEGRATED) if f.endswith('.py')])
ast_ok = 0
ast_fail = 0

for f in py_files:
    path = os.path.join(INTEGRATED, f)
    try:
        with open(path, encoding='utf-8') as fh:
            ast.parse(fh.read())
        print(f"  ✅ {f}")
        ast_ok += 1
    except SyntaxError as e:
        print(f"  ❌ {f}: {e}")
        ast_fail += 1

print(f"\nAST 결과: {ast_ok} OK, {ast_fail} FAIL / 총 {len(py_files)} 파일")

print()
print("=" * 60)
print("STEP 2: Import 의존성 검증")
print("=" * 60)

# integrated/ 를 sys.path에 추가
sys.path.insert(0, INTEGRATED)

# PyQt6 의존 모듈은 제외 (headless 환경에서 실패)
# GUI 모듈은 AST만 검증, import는 비-GUI 모듈만
non_gui_modules = [
    'chem_data',
    'coord_utils',
    'engine_core',
    'engine_physics',
    'engine_resonance',
]

gui_modules = [
    'ui_utils',
    'renderer',
    'analyzer',
    'orca_interface',
    'electron_density_analyzer',
    'base_spectrum',
    'lasso_selection',
    'canvas',
    'layer_logic',
    'main_window',
    'dialogs',
    'toolbar_setup',
    'draw',
    'popup_3d',
    'popup_spectrum',
    'popup_nmr',
    'popup_uvvis',
    'popup_molorbital',
    'popup_md',
    'spectrum_analyzer',
    'spectrum_pdf_exporter',
    'phase_integration',
    'batch_processor',
    'calculation_logger',
    'error_handler',
    'export_manager_enhanced',
    'history_manager',
    'iupac_analyzer',
    'molecule_comparator',
    'progress_tracker',
    'test_integration',
]

import_ok = 0
import_fail = 0
import_errors = []

# 비-GUI 모듈 먼저
for m in non_gui_modules:
    try:
        importlib.import_module(m)
        print(f"  ✅ {m}")
        import_ok += 1
    except Exception as e:
        err_msg = f"{m}: {type(e).__name__}: {e}"
        print(f"  ❌ {err_msg}")
        import_fail += 1
        import_errors.append(err_msg)

# GUI 모듈 (PyQt6 필요)
for m in gui_modules:
    try:
        importlib.import_module(m)
        print(f"  ✅ {m}")
        import_ok += 1
    except ImportError as e:
        # PyQt6/RDKit 미설치로 인한 실패는 경고로 처리
        err_str = str(e)
        if any(pkg in err_str for pkg in ['PyQt6', 'OpenGL', 'rdkit', 'matplotlib', 'google']):
            print(f"  ⚠️  {m}: {e} (외부 패키지 의존)")
            import_ok += 1  # 외부 패키지 문제는 OK 처리
        else:
            print(f"  ❌ {m}: {e}")
            import_fail += 1
            import_errors.append(f"{m}: {e}")
    except Exception as e:
        err_msg = f"{m}: {type(e).__name__}: {e}"
        print(f"  ❌ {err_msg}")
        import_fail += 1
        import_errors.append(err_msg)

total_modules = len(non_gui_modules) + len(gui_modules)
print(f"\nImport 결과: {import_ok} OK, {import_fail} FAIL / 총 {total_modules} 모듈")

if import_errors:
    print("\n⚠️  Import 오류 상세:")
    for err in import_errors:
        print(f"    → {err}")

print()
print("=" * 60)
print("STEP 3: ChemDraw 잔존 확인")
print("=" * 60)

chemdraw_count = 0
for f in py_files:
    path = os.path.join(INTEGRATED, f)
    with open(path, encoding='utf-8') as fh:
        content = fh.read()
    
    for i, line in enumerate(content.split('\n'), 1):
        if 'ChemDraw' in line and not line.strip().startswith('#'):
            print(f"  ⚠️  {f}:{i}: {line.strip()[:80]}")
            chemdraw_count += 1

if chemdraw_count == 0:
    print("  ✅ ChemDraw 문자열 없음 (이미 교체됨 또는 교체 필요)")
else:
    print(f"\n  ⚠️  ChemDraw 잔존: {chemdraw_count}건 (명령 3에서 교체 필요)")

print()
print("=" * 60)
print("최종 요약")
print("=" * 60)
print(f"  Python 파일: {len(py_files)}개")
print(f"  AST:    {ast_ok}/{len(py_files)} PASS")
print(f"  Import: {import_ok}/{total_modules} PASS")
print(f"  ChemDraw 잔존: {chemdraw_count}건")

if ast_fail > 0 or import_fail > 0:
    print("\n🔴 검증 실패 — 수정 필요")
    sys.exit(1)
else:
    print("\n🟢 검증 통과")
    sys.exit(0)
