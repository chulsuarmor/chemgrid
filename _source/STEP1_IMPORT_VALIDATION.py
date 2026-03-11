#!/usr/bin/env python3
"""
Step 1: 모든 파일 임포트 검증
ChemDraw Pro Final Validation Test
"""

import sys
import os
from datetime import datetime
import traceback

# 로깅 설정
LOG_FILE = "STEP1_IMPORT_LOG.txt"
START_TIME = datetime.now()

def log_message(msg, level="INFO"):
    """메시지 로깅"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {msg}"
    print(log_entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

def test_import(module_name, file_path):
    """모듈 임포트 테스트"""
    try:
        if os.path.exists(file_path):
            # 동적 임포트
            spec = __import__('importlib.util').util.spec_from_file_location(module_name, file_path)
            module = __import__('importlib.util').util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            log_message(f"✅ {module_name}: OK", "SUCCESS")
            return True
        else:
            log_message(f"❌ {module_name}: 파일을 찾을 수 없음 ({file_path})", "ERROR")
            return False
    except Exception as e:
        log_message(f"❌ {module_name}: {str(e)}", "ERROR")
        log_message(f"   Traceback: {traceback.format_exc()}", "ERROR")
        return False

# Step 1 시작
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(f"{'='*80}\n")
    f.write(f"ChemDraw Pro - STEP 1: 모든 파일 임포트 검증\n")
    f.write(f"시작 시간: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"{'='*80}\n\n")

log_message("=" * 80)
log_message("STEP 1: 모든 파일 임포트 검증 시작")
log_message("=" * 80)

# 테스트할 모듈 목록
modules_to_test = [
    # Core modules
    ("draw", "draw.py"),
    ("layer_logic", "layer_logic.py"),
    ("renderer", "renderer.py"),
    
    # 3D & Analysis
    ("popup_3d", "popup_3d.py"),
    ("iupac_analyzer", "iupac_analyzer.py"),
    ("orca_interface", "orca_interface.py"),
    
    # Spectrum
    ("spectrum_analyzer", "spectrum_analyzer.py"),
    ("popup_spectrum", "popup_spectrum.py"),
    ("popup_nmr", "popup_nmr.py"),
    
    # Additional popups
    ("popup_uvvis", "popup_uvvis.py"),
    ("popup_md", "popup_md.py"),
    ("popup_molorbital", "popup_molorbital.py"),
    
    # Utilities
    ("smiles_validator", "smiles_validator.py"),
    ("error_handler", "error_handler.py"),
    ("history_manager", "history_manager.py"),
    ("molecule_comparator", "molecule_comparator.py"),
    ("coord_utils", "coord_utils.py"),
    ("progress_tracker", "progress_tracker.py"),
]

log_message(f"총 {len(modules_to_test)}개 모듈 테스트 시작...\n", "INFO")

# 임포트 테스트
results = {}
success_count = 0
fail_count = 0

for module_name, file_path in modules_to_test:
    full_path = os.path.join(os.getcwd(), file_path)
    if test_import(module_name, full_path):
        success_count += 1
        results[module_name] = "✅ OK"
    else:
        fail_count += 1
        results[module_name] = "❌ FAILED"

# 통계
log_message("\n" + "=" * 80)
log_message("임포트 검증 결과", "INFO")
log_message("=" * 80)
log_message(f"성공: {success_count}/{len(modules_to_test)}")
log_message(f"실패: {fail_count}/{len(modules_to_test)}")

# 실패한 모듈 상세 목록
if fail_count > 0:
    log_message("\n⚠️  실패한 모듈:", "WARNING")
    for module_name, status in results.items():
        if "FAILED" in status:
            log_message(f"  - {module_name}", "WARNING")

# 완료 시간
end_time = datetime.now()
duration = (end_time - START_TIME).total_seconds()
log_message(f"\n종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
log_message(f"소요 시간: {duration:.2f}초")

if fail_count == 0:
    log_message("\n✅ STEP 1 완료: 모든 임포트 성공!", "SUCCESS")
else:
    log_message(f"\n⚠️  STEP 1 완료 (오류 {fail_count}개 발견)", "WARNING")

log_message("=" * 80)

# 요약
summary = {
    "step": 1,
    "total_modules": len(modules_to_test),
    "success": success_count,
    "failed": fail_count,
    "duration_seconds": duration,
    "timestamp": START_TIME.isoformat(),
}

print("\n" + "="*80)
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("="*80)

import json
with open("STEP1_SUMMARY.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

sys.exit(0 if fail_count == 0 else 1)
