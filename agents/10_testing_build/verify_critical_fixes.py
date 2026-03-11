#!/usr/bin/env python3
"""
verify_critical_fixes.py — Phase 6-1A 수정 검증 스크립트
==========================================================
원본(_source/)과 수정본(fixed_*)을 비교하여 모든 Critical/Major 수정이
올바르게 적용되었는지 검증합니다.

사용법:
  py verify_critical_fixes.py
"""

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_SOURCE_DIR = _SCRIPT_DIR.parent.parent / "_source"

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results = []


def check(test_id, description, condition):
    status = PASS if condition else FAIL
    results.append((test_id, description, condition))
    print(f"  {status} {test_id}: {description}")
    return condition


def read_file(path):
    return Path(path).read_text(encoding="utf-8")


def main():
    print("=" * 70)
    print("Phase 6-1A Critical + Major Bug Fix Verification")
    print("=" * 70)

    # ── 파일 존재 확인 ──
    print("\n[0] 파일 존재 확인")
    fixed_files = [
        "fixed_orca_interface.py",
        "fixed_popup_3d.py",
        "fixed_draw.py",
        "fixed_renderer.py",
    ]
    for f in fixed_files:
        check(f"FILE_{f}", f"{f} 존재", (_SCRIPT_DIR / f).exists())

    # ── C1: ORCA 경로 포터블화 ──
    print("\n[C1] ORCA 경로 하드코딩 수정")
    orca_src = read_file(_SOURCE_DIR / "orca_interface.py")
    orca_fix = read_file(_SCRIPT_DIR / "fixed_orca_interface.py")

    check("C1-1", "원본에 하드코딩 경로 존재",
          r'C:\Users' in orca_src or "C:\\Users" in orca_src)
    # 활성 코드(주석 아닌 줄)에서만 하드코딩 경로 확인
    active_hardcoded = [line for line in orca_fix.split('\n')
                        if ('C:\\Users' in line or r'C:\Users' in line)
                        and not line.strip().startswith('#')]
    check("C1-2", "수정본 활성 코드에 하드코딩 경로 없음",
          len(active_hardcoded) == 0)
    check("C1-3", "수정본에 __file__ 기반 경로 존재",
          "os.path.abspath(__file__)" in orca_fix)
    check("C1-4", '수정본에 _SCRIPT_DIR / "Orca.6.1.1" 존재',
          '_SCRIPT_DIR / "Orca.6.1.1"' in orca_fix)

    # ── C2: popup_3d.py import 수정 ──
    print("\n[C2] popup_3d.py 임포트 오류 수정")
    popup_src = read_file(_SOURCE_DIR / "popup_3d.py")
    popup_fix = read_file(_SCRIPT_DIR / "fixed_popup_3d.py")

    check("C2-1", "원본에 잘못된 import 존재",
          "from PyQt6.QtOpenGL import GL" in popup_src)
    # 수정본에서는 주석/docstring이 아닌 실제 import문만 확인
    active_imports = [line for line in popup_fix.split('\n')
                      if line.strip().startswith("from PyQt6.QtOpenGL import")]
    check("C2-2", "수정본에 활성 import문 없음", len(active_imports) == 0)

    # ── C3: self.canvas.repaint() → self.update() ──
    print("\n[C3] self.canvas.repaint() 수정")
    draw_src = read_file(_SOURCE_DIR / "draw.py")
    draw_fix = read_file(_SCRIPT_DIR / "fixed_draw.py")

    check("C3-1", "원본에 self.canvas.repaint() 존재",
          "self.canvas.repaint()" in draw_src)
    check("C3-2", "수정본에 self.canvas.repaint() 없음",
          "self.canvas.repaint()" not in draw_fix)
    check("C3-3", "수정본에 self.update() 대체",
          "self.update()  # " in draw_fix or "self.update()" in draw_fix)

    # ── C4: verification_report except 메시지 수정 ──
    print("\n[C4] verification_report except 메시지 수정")
    check("C4-1", "원본에 잘못된 Orbital 메시지 존재",
          'print("[draw.py] Molecular Orbital module not available")' in draw_src)
    # 수정본에서는 verification_report except 블록에서 Orbital 메시지가 제거됨
    # except 블록 내부의 Orbital 메시지만 확인 (다른 위치의 Orbital은 무관)
    lines_fix = draw_fix.split('\n')
    in_verification_except = False
    orbital_in_verification = False
    for line in lines_fix:
        if "VERIFICATION_REPORT_AVAILABLE = False" in line:
            in_verification_except = True
        if in_verification_except and "Molecular Orbital" in line and not line.strip().startswith("#"):
            orbital_in_verification = True
        if in_verification_except and line.strip() and not line.startswith(" ") and "except" not in line and "VERIFICATION" not in line and "print" not in line:
            in_verification_except = False
    check("C4-2", "수정본에서 verification except 내 Orbital 메시지 없음",
          not orbital_in_verification)

    # ── C5: 포터블 경로 시스템 ──
    print("\n[C5] 포터블 경로 시스템")
    check("C5-1", "원본에 하드코딩 경로 존재 (draw.py)",
          'organicdraw' in draw_src or r"C:\Users" in draw_src)
    check("C5-2", "수정본에 하드코딩 경로 없음 (draw.py)",
          'organicdraw' not in draw_fix)

    # ── M1: 조준선 3중 렌더링 수정 ──
    print("\n[M1] 조준선 3중 렌더링 → 1회")
    crosshair_calls_src = draw_src.count("CloudRenderer.draw_crosshairs_v32(")
    crosshair_calls_fix = draw_fix.count("CloudRenderer.draw_crosshairs_v32(")
    check("M1-1", f"원본: draw_crosshairs_v32 호출 {crosshair_calls_src}회",
          crosshair_calls_src == 3)
    check("M1-2", f"수정본: draw_crosshairs_v32 호출 {crosshair_calls_fix}회 (1회만)",
          crosshair_calls_fix == 1)

    # ── M2: 디버그 print 제거 ──
    print("\n[M2] 디버그 print 제거")
    renderer_src = read_file(_SOURCE_DIR / "renderer.py")
    renderer_fix = read_file(_SCRIPT_DIR / "fixed_renderer.py")

    debug_prints_src = renderer_src.count("print(f")
    debug_prints_fix = renderer_fix.count("print(f")
    check("M2-1", f"renderer.py print(f 감소: {debug_prints_src} → {debug_prints_fix}",
          debug_prints_fix < debug_prints_src)

    # draw.py paintEvent 내 Z-INDEX print
    check("M2-2", "수정본에 Z-INDEX 디버그 print 없음",
          "[draw.py Z-INDEX]" not in draw_fix)

    # ── M5: Discord 보고 비활성화 ──
    print("\n[M5] Discord 보고 비활성화")
    check("M5-1", "원본에 start_periodic_reporting() 활성",
          "self.reporter_thread = start_periodic_reporting()" in draw_src)
    check("M5-2", "수정본에 start_periodic_reporting() 비활성 (주석)",
          "# self.reporter_thread = start_periodic_reporting()" in draw_fix)

    # ── 구문 검증 ──
    print("\n[SYN] 구문 검증")
    import ast
    for f in fixed_files:
        try:
            ast.parse(read_file(_SCRIPT_DIR / f))
            check(f"SYN_{f}", f"{f} 구문 정상", True)
        except SyntaxError as e:
            check(f"SYN_{f}", f"{f} 구문 오류: {e}", False)

    # ── 최종 결과 ──
    total = len(results)
    passed = sum(1 for _, _, ok in results if ok)
    failed = total - passed

    print(f"\n{'=' * 70}")
    print(f"검증 결과: {passed}/{total} PASS ({failed} FAIL)")
    print(f"{'=' * 70}")

    if failed > 0:
        print("\n실패한 항목:")
        for tid, desc, ok in results:
            if not ok:
                print(f"  ❌ {tid}: {desc}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
