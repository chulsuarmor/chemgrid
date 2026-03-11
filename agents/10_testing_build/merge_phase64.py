"""
Phase 6-4 병합 스크립트
Agent 01, 02, 05, 06의 v4 산출물을 integrated/에 병합
"""
import shutil
import os
import sys

INTEGRATED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integrated")

# Phase 6-4에서 변경된 파일만 병합
# Agent 03, 04, 07, 08은 Phase 6-3에서 이미 병합 완료 (v4 변경 없음)
copies = [
    # Agent 01 (UI/디자인) — v4: 툴바 2줄, Theory→3D 자동오픈 제거, 반응화살표+텍스트
    (r"c:\chemgrid\agents\01_ui_design\draw.py", os.path.join(INTEGRATED, "draw.py")),
    (r"c:\chemgrid\agents\01_ui_design\main_window.py", os.path.join(INTEGRATED, "main_window.py")),
    (r"c:\chemgrid\agents\01_ui_design\toolbar_setup.py", os.path.join(INTEGRATED, "toolbar_setup.py")),
    (r"c:\chemgrid\agents\01_ui_design\dialogs.py", os.path.join(INTEGRATED, "dialogs.py")),
    (r"c:\chemgrid\agents\01_ui_design\ui_utils.py", os.path.join(INTEGRATED, "ui_utils.py")),

    # Agent 02 (캔버스/그리기) — v4: +/- charge, 반응화살표, 텍스트, user_lp
    (r"c:\chemgrid\agents\02_canvas_interaction\canvas.py", os.path.join(INTEGRATED, "canvas.py")),
    (r"c:\chemgrid\agents\02_canvas_interaction\coord_utils.py", os.path.join(INTEGRATED, "coord_utils.py")),

    # Agent 05 (렌더링) — Phase 6-3: 공명 균등화, user_lp 제외
    (r"c:\chemgrid\agents\05_rendering_engine\renderer.py", os.path.join(INTEGRATED, "renderer.py")),

    # Agent 06 (3D) — v4: 원자크기/CPK, 다중결합, PropertiesPanel, AI오버레이
    (r"c:\chemgrid\agents\06_3d_structure\popup_3d.py", os.path.join(INTEGRATED, "popup_3d.py")),
]

print("=" * 60)
print("Phase 6-4 병합: 에이전트 산출물 → integrated/")
print("=" * 60)

ok = 0
fail = 0
for src, dst in copies:
    basename = os.path.basename(src)
    if os.path.exists(src):
        # 기존 파일 크기 비교
        old_size = os.path.getsize(dst) if os.path.exists(dst) else 0
        shutil.copy2(src, dst)
        new_size = os.path.getsize(dst)
        delta = new_size - old_size
        sign = "+" if delta > 0 else ""
        print(f"  ✅ {basename:<30} {old_size:>8} → {new_size:>8} ({sign}{delta})")
        ok += 1
    else:
        print(f"  ❌ MISSING: {src}")
        fail += 1

print(f"\n결과: {ok} 복사 완료, {fail} 실패")
if fail:
    sys.exit(1)
else:
    print("✅ Phase 6-4 병합 완료!")
