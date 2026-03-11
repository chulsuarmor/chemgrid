#!/usr/bin/env python3
"""
Step 1: Python 문법 검증
모든 .py 파일의 기본 문법 검증
"""

import os
import py_compile
import sys
from datetime import datetime
import json

LOG_FILE = "STEP1_SYNTAX_LOG.txt"
START_TIME = datetime.now()

def log_message(msg):
    """메시지 로깅"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    print(log_entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

# Step 1 시작
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(f"{'='*80}\n")
    f.write(f"ChemDraw Pro - STEP 1: Python 문법 검증\n")
    f.write(f"시작 시간: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"{'='*80}\n\n")

log_message("=" * 80)
log_message("STEP 1: Python 문법 검증 시작")
log_message("=" * 80)

# 테스트할 파일 목록
critical_files = [
    "draw.py",
    "layer_logic.py",
    "renderer.py",
    "popup_3d.py",
    "iupac_analyzer.py",
    "orca_interface.py",
    "spectrum_analyzer.py",
    "popup_spectrum.py",
    "popup_nmr.py",
    "popup_uvvis.py",
    "popup_md.py",
    "popup_molorbital.py",
    "smiles_validator.py",
    "error_handler.py",
    "history_manager.py",
    "molecule_comparator.py",
    "coord_utils.py",
    "progress_tracker.py",
]

log_message(f"총 {len(critical_files)}개 파일 검증 시작...\n")

results = {}
success_count = 0
fail_count = 0

for file_name in critical_files:
    file_path = os.path.join(os.getcwd(), file_name)
    try:
        if os.path.exists(file_path):
            py_compile.compile(file_path, doraise=True)
            log_message(f"✅ {file_name}: 문법 OK")
            results[file_name] = "OK"
            success_count += 1
        else:
            log_message(f"❌ {file_name}: 파일 없음")
            results[file_name] = "FILE_NOT_FOUND"
            fail_count += 1
    except py_compile.PyCompileError as e:
        log_message(f"❌ {file_name}: 문법 오류")
        log_message(f"   {str(e)}")
        results[file_name] = f"SYNTAX_ERROR: {str(e)}"
        fail_count += 1

# 통계
log_message("\n" + "=" * 80)
log_message("검증 결과 요약")
log_message("=" * 80)
log_message(f"성공: {success_count}/{len(critical_files)}")
log_message(f"실패: {fail_count}/{len(critical_files)}")

# 완료
end_time = datetime.now()
duration = (end_time - START_TIME).total_seconds()
log_message(f"\n종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
log_message(f"소요 시간: {duration:.2f}초")

if fail_count == 0:
    log_message("\n✅ STEP 1 완료: 모든 파일 문법 정상!")
    status = "PASS"
else:
    log_message(f"\n⚠️  STEP 1 완료 (오류 {fail_count}개)")
    status = "FAIL"

log_message("=" * 80)

# 요약 JSON
summary = {
    "step": 1,
    "type": "SYNTAX_CHECK",
    "total_files": len(critical_files),
    "success": success_count,
    "failed": fail_count,
    "status": status,
    "duration_seconds": duration,
    "timestamp": START_TIME.isoformat(),
}

print("\n" + "="*80)
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("="*80)

with open("STEP1_SUMMARY.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
