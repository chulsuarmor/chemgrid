#!/usr/bin/env python3
"""
apply_critical_fixes.py — Phase 6-1A Critical + Major Bug Fixes
================================================================
이 스크립트는 _source/ 원본 파일들을 읽고 모든 Critical/Major 수정을 적용하여
fixed_* 파일을 생성합니다.

적용되는 수정:
  C1: orca_interface.py — ORCA 경로 하드코딩 → 포터블 (별도 파일로 이미 생성됨)
  C2: popup_3d.py — from PyQt6.QtOpenGL import GL 제거 (별도 파일로 이미 생성됨)
  C3: draw.py — self.canvas.repaint() → self.update()
  C4: draw.py — verification_report except 블록의 잘못된 Orbital 메시지 제거
  C5: draw.py — _analyze_dft_electron_density() 하드코딩 절대경로 → 포터블 경로
  M1: draw.py — 조준선 3중 렌더링 → 1회만 (최상위 Z-INDEX 블록)
  M2: draw.py + renderer.py — 디버그 print 제거/logging 교체
  M5: draw.py — progress_tracker Discord 보고 비활성화

사용법:
  py apply_critical_fixes.py
"""

import os
import re
import sys
import shutil
from pathlib import Path

# 경로 설정
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_SOURCE_DIR = _SCRIPT_DIR.parent.parent / "_source"
_OUTPUT_DIR = _SCRIPT_DIR  # 수정본은 이 에이전트 폴더에 저장

def read_source(filename):
    """원본 소스 파일 읽기"""
    src = _SOURCE_DIR / filename
    if not src.exists():
        print(f"[ERROR] 원본 파일 없음: {src}")
        sys.exit(1)
    return src.read_text(encoding="utf-8")


def apply_draw_fixes(content: str) -> str:
    """draw.py에 C3, C4, C5, M1, M2, M5 수정 적용"""
    changes = []
    
    # ═══════════════════════════════════════════════════════════════
    # C3 FIX: self.canvas.repaint() → self.update()
    # MoleculeCanvas 자체가 self이므로 self.canvas는 존재하지 않음
    # ═══════════════════════════════════════════════════════════════
    old_c3 = "self.canvas.repaint()"
    new_c3 = "self.update()  # ✅ C3 FIX: self 자체가 canvas이므로 self.update() 사용"
    if old_c3 in content:
        content = content.replace(old_c3, new_c3)
        changes.append("C3: self.canvas.repaint() → self.update()")
    
    # ═══════════════════════════════════════════════════════════════
    # C4 FIX: verification_report except 블록의 잘못된 Orbital 메시지 제거
    # ═══════════════════════════════════════════════════════════════
    old_c4 = '''except ImportError:
    VERIFICATION_REPORT_AVAILABLE = False
    print("[draw.py] Verification report module not available")
    print("[draw.py] Molecular Orbital module not available")'''
    
    new_c4 = '''except ImportError:
    VERIFICATION_REPORT_AVAILABLE = False
    print("[draw.py] Verification report module not available")
    # ✅ C4 FIX: Orbital 메시지 제거 (이 except는 verification_report 전용)'''
    
    if old_c4 in content:
        content = content.replace(old_c4, new_c4)
        changes.append("C4: verification_report except 블록에서 잘못 배치된 Orbital 메시지 제거")
    
    # ═══════════════════════════════════════════════════════════════
    # C5 FIX: _analyze_dft_electron_density() 하드코딩 경로 → 포터블 경로
    # ═══════════════════════════════════════════════════════════════
    old_c5 = '''            orca_out_candidates = [
                Path.cwd() / "orca_calcs" / "input.out",
                Path.cwd() / "input.out",
                Path(r"C:\\Users\\김남헌\\Desktop\\organicdraw\\orca_calcs\\input.out"),
            ]'''
    
    new_c5 = '''            # ✅ C5 FIX: 포터블 경로 시스템 — 하드코딩 절대 경로 제거
            _draw_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            orca_out_candidates = [
                _draw_dir / "orca_calcs" / "input.out",
                Path.cwd() / "orca_calcs" / "input.out",
                Path.cwd() / "input.out",
            ]'''
    
    if old_c5 in content:
        content = content.replace(old_c5, new_c5)
        changes.append("C5: _analyze_dft_electron_density()에서 하드코딩 절대 경로 제거")
    else:
        # raw string 버전도 시도
        old_c5_raw = 'Path(r"C:\\Users\\'
        if old_c5_raw in content:
            # 해당 줄 전체를 찾아서 교체
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if 'Path(r"C:\\Users\\' in line or "Path(r\"C:\\Users\\" in line:
                    new_lines.append("                # ✅ C5 FIX: 하드코딩 절대 경로 제거됨")
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)
            changes.append("C5: 하드코딩 절대 경로 줄 제거 (대체 패턴)")
    
    # ═══════════════════════════════════════════════════════════════
    # M1 FIX: 조준선 3중 렌더링 → 최상위 Z-INDEX 1회만
    # LAYER 3과 LAYER 4에서 draw_crosshairs_v32() 호출 제거
    # ═══════════════════════════════════════════════════════════════
    
    # LAYER 3 (Lewis/Theory)에서의 조준선 호출 제거
    old_m1_layer3 = '''            # ========== [v3.2 CRITICAL] Lewis/Theory 레이어 조준선 ==========
            # ✅ Lewis/Theory 뷰에서도 조준선 표시
            # ✅ 클리핑 해제: 원형 마스크에도 가려지지 않게
            if self.analysis_results and self.view_state in ["Lewis", "Theory"]:
                p.setClipping(False)  # 클리핑 해제
                print(f"\\n[draw.py Lewis/Theory] Rendering crosshairs in {self.view_state} layer (clipping OFF)")
                CloudRenderer.draw_crosshairs_v32(p, self.analysis_results)'''
    
    new_m1_layer3 = '''            # ✅ M1 FIX: 조준선은 최상위 Z-INDEX 블록에서만 1회 렌더링
            # (이전: Lewis/Theory 레이어에서 중복 호출 — 제거됨)'''
    
    if old_m1_layer3 in content:
        content = content.replace(old_m1_layer3, new_m1_layer3)
        changes.append("M1: LAYER 3(Lewis/Theory)에서 조준선 중복 호출 제거")
    
    # LAYER 4 (Drawing)에서의 조준선 호출 제거
    old_m1_layer4 = '''            # ========== [v3.2 CRITICAL] Drawing 레이어 조준선 ==========
            # ✅ 조준선을 원소 기호보다 위에 렌더링
            # ✅ 클리핑 해제: 모든 마스크 무시
            if hasattr(self, 'analysis_results') and self.analysis_results:
                p.setClipping(False)  # 클리핑 해제
                print(f"\\n[draw.py Drawing] Rendering crosshairs in Drawing layer (clipping OFF)")
                CloudRenderer.draw_crosshairs_v32(p, self.analysis_results)'''
    
    new_m1_layer4 = '''            # ✅ M1 FIX: 조준선은 최상위 Z-INDEX 블록에서만 1회 렌더링
            # (이전: Drawing 레이어에서 중복 호출 — 제거됨)'''
    
    if old_m1_layer4 in content:
        content = content.replace(old_m1_layer4, new_m1_layer4)
        changes.append("M1: LAYER 4(Drawing)에서 조준선 중복 호출 제거")
    
    # ═══════════════════════════════════════════════════════════════
    # M2 FIX: paintEvent 디버그 print 제거
    # ═══════════════════════════════════════════════════════════════
    
    # 최상위 Z-INDEX 블록의 print 제거 (조준선은 유지)
    old_m2_zindex = '''            print("\\n" + "="*70)
            print("[draw.py Z-INDEX] Rendering crosshairs at TOP LAYER")
            print(f"  pan_offset: ({self.pan_offset.x():.1f}, {self.pan_offset.y():.1f})")
            print(f"  scale_factor: {self.scale_factor:.2f}")
            print(f"  clipping: DISABLED (forced visible)")
            print("="*70)'''
    
    new_m2_zindex = '''            # ✅ M2 FIX: 디버그 print 제거 (매 프레임 출력 방지)'''
    
    if old_m2_zindex in content:
        content = content.replace(old_m2_zindex, new_m2_zindex)
        changes.append("M2: paintEvent 최상위 Z-INDEX print 제거")
    
    # ═══════════════════════════════════════════════════════════════
    # M5 FIX: progress_tracker Discord 보고 비활성화
    # ═══════════════════════════════════════════════════════════════
    old_m5 = '''        try:
            from progress_tracker import get_tracker, start_periodic_reporting
            self.progress_tracker = get_tracker()
            # 30분마다 자동 Discord 보고 시작
            self.reporter_thread = start_periodic_reporting()
            print("[MainWindow] Progress tracking and Discord reporting activated")
        except Exception as e:
            print(f"[MainWindow] Progress tracking initialization failed: {e}")'''
    
    new_m5 = '''        # ✅ M5 FIX: Discord 보고 비활성화 (개발 단계에서 불필요)
        try:
            from progress_tracker import get_tracker
            self.progress_tracker = get_tracker()
            # start_periodic_reporting() 주석 처리 — 배포 시 활성화
            # self.reporter_thread = start_periodic_reporting()
            self.reporter_thread = None
        except Exception as e:
            self.progress_tracker = None
            self.reporter_thread = None'''
    
    if old_m5 in content:
        content = content.replace(old_m5, new_m5)
        changes.append("M5: progress_tracker Discord 보고 비활성화")
    
    return content, changes


def apply_renderer_fixes(content: str) -> str:
    """renderer.py에 M2 (디버그 print 제거) 수정 적용"""
    changes = []
    
    # ═══════════════════════════════════════════════════════════════
    # M2 FIX: draw_clouds 내 디버그 print 제거
    # ═══════════════════════════════════════════════════════════════
    
    # 1. draw_clouds 시작 부분 print 블록
    old_r1 = '''        # ✅ DEBUG: v3.2 렌더링 시작 확인
        print(f"\\n{'='*70}")
        print(f"[v3.2 Renderer] draw_clouds called")
        print(f"  Total atoms: {len(charges)}")
        print(f"  use_theory_coords: {use_theory_coords}")
        print(f"{'='*70}")'''
    
    new_r1 = '''        # ✅ M2 FIX: 디버그 print 제거 (매 프레임 성능 영향)'''
    
    if old_r1 in content:
        content = content.replace(old_r1, new_r1)
        changes.append("M2: draw_clouds 시작 print 블록 제거")
    
    # 2. LOCAL CONTRAST print 블록
    old_r2 = '''                print(f"\\n[v3.2 LOCAL CONTRAST]")
                print(f"  전체 분자: min={global_min:+.3f}, max={global_max:+.3f}")
                print(f"  고리 탄소: min={ring_min:+.3f}, max={ring_max:+.3f}, avg={ring_avg_charge:+.3f}")
                print(f"  → 색상 범위: {charge_range:.3f} (고리 기준)")'''
    
    if old_r2 in content:
        content = content.replace(old_r2, "")
        changes.append("M2: LOCAL CONTRAST print 블록 제거")
    
    # 3. 고리 탄소 반지름 print
    old_r3 = '''            # ✅ DEBUG: 고리 탄소 반지름 출력
            if is_ring_carbon and at_main == "C":
                status = "DEACTIVATED" if deactivation_applied else "ACTIVATED"
                print(f"  Carbon at {pt_key}: charge={charge:+.3f}, avg={ring_avg_charge:+.3f}, "
                      f"radius={radius:.1f}px, weight={reactivity_weight:.2f}x [{status}]")'''
    
    if old_r3 in content:
        content = content.replace(old_r3, "")
        changes.append("M2: 고리 탄소 반지름 디버그 print 제거")
    
    # 4. 조준선 데이터 저장 print
    old_r4 = '''            # ✅ DEBUG: 조준선 좌표 출력
            print(f"\\n[v3.2 Crosshairs] Storing {len(top_sites)} markers:")
            for pt_key, charge_val, pos in top_sites:
                print(f"  ⊕ pt_key: {pt_key}, charge: {charge_val:.4f}")
                print(f"     → QPointF: ({pos.x():.1f}, {pos.y():.1f})")'''
    
    if old_r4 in content:
        content = content.replace(old_r4, "")
        changes.append("M2: 조준선 데이터 저장 디버그 print 제거")
    
    # 5. draw_crosshairs_v32 내부 print
    old_r5 = '''        print(f"\\n[v3.2 TOP LAYER] Rendering {len(crosshair_data)} crosshairs:")'''
    if old_r5 in content:
        content = content.replace(old_r5, "")
        changes.append("M2: draw_crosshairs_v32 TOP LAYER print 제거")
    
    old_r6 = '''            print(f"  ⊕ Drawing at QPointF({pos.x():.1f}, {pos.y():.1f}), charge={charge_val:.4f}")'''
    if old_r6 in content:
        content = content.replace(old_r6, "")
        changes.append("M2: draw_crosshairs_v32 Drawing print 제거")
    
    return content, changes


def main():
    print("=" * 70)
    print("Phase 6-1A: Critical + Major Bug Fixes")
    print("=" * 70)
    
    all_changes = []
    
    # ── draw.py 수정 ──
    print("\n[1/2] draw.py 수정 중...")
    draw_content = read_source("draw.py")
    draw_fixed, draw_changes = apply_draw_fixes(draw_content)
    all_changes.extend(draw_changes)
    
    output_draw = _OUTPUT_DIR / "fixed_draw.py"
    output_draw.write_text(draw_fixed, encoding="utf-8")
    print(f"  → {output_draw}")
    for c in draw_changes:
        print(f"    ✅ {c}")
    
    # ── renderer.py 수정 ──
    print("\n[2/2] renderer.py 수정 중...")
    renderer_content = read_source("renderer.py")
    renderer_fixed, renderer_changes = apply_renderer_fixes(renderer_content)
    all_changes.extend(renderer_changes)
    
    output_renderer = _OUTPUT_DIR / "fixed_renderer.py"
    output_renderer.write_text(renderer_fixed, encoding="utf-8")
    print(f"  → {output_renderer}")
    for c in renderer_changes:
        print(f"    ✅ {c}")
    
    # ── 요약 ──
    print(f"\n{'=' * 70}")
    print(f"완료: 총 {len(all_changes)}개 수정 적용")
    print(f"{'=' * 70}")
    
    if not all_changes:
        print("\n⚠️ 경고: 적용된 수정이 없습니다! 원본 파일 형식이 변경되었을 수 있습니다.")
        return 1
    
    for i, c in enumerate(all_changes, 1):
        print(f"  {i}. {c}")
    
    print(f"\n생성된 파일:")
    print(f"  • {_OUTPUT_DIR / 'fixed_orca_interface.py'}  (C1)")
    print(f"  • {_OUTPUT_DIR / 'fixed_popup_3d.py'}        (C2)")
    print(f"  • {_OUTPUT_DIR / 'fixed_draw.py'}            (C3, C4, C5, M1, M2, M5)")
    print(f"  • {_OUTPUT_DIR / 'fixed_renderer.py'}        (M2)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
