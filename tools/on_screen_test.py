"""
on_screen_test.py — ChemGrid 실제 화면 온그라운드 검증 스크립트
실제 앱 창을 조작하며 스크린샷 수집 → HTML 리포트 생성
"""
import pygetwindow as gw
import pyautogui
import time
import os
import json
import datetime
from pathlib import Path

pyautogui.FAILSAFE = True
OUTDIR = Path("c:/chemgrid/docs/reports/visual_feedback")
OUTDIR.mkdir(parents=True, exist_ok=True)

MOLECULES = [
    "benzene",
    "aspirin",
    "tropylium",
    "cyclopentadienyl anion",
    "caffeine",
    "ibuprofen",
    "naphthalene",
    "glucose",
    "adenine",
    "cholesterol",
    "paracetamol",
    "tryptophan",
    "anthracene",
    "quercetin",
    "phenylalanine",
]

def find_chemgrid():
    wins = [w for w in gw.getAllWindows()
            if 'ChemGrid' in w.title and 'Visual Studio' not in w.title and w.width > 100]
    if not wins:
        raise RuntimeError("ChemGrid 창을 찾을 수 없음")
    return wins[0]

def ss(name):
    path = str(OUTDIR / f"{name}.png")
    pyautogui.screenshot(path)
    print(f"  📸 {name}.png")
    return path

def click_input_and_type(w, text):
    # 입력창: 창 하단 중앙 (~30px from bottom)
    ix = w.left + w.width // 2
    iy = w.top + w.height - 28
    pyautogui.click(ix, iy)
    time.sleep(0.3)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.typewrite(text, interval=0.05)
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(2.5)  # 분자 생성 대기

def click_btn(w, label_x_frac, label_y_frac):
    """창 내 상대 좌표로 버튼 클릭"""
    x = w.left + int(w.width * label_x_frac)
    y = w.top + int(w.height * label_y_frac)
    pyautogui.click(x, y)
    time.sleep(1.0)

def close_popup():
    """ESC로 팝업 닫기"""
    pyautogui.press('escape')
    time.sleep(0.5)

def run_test():
    w = find_chemgrid()
    w.activate()
    time.sleep(0.5)

    results = []

    for i, mol in enumerate(MOLECULES, 1):
        print(f"\n[{i:02d}/{len(MOLECULES)}] {mol}")
        molkey = mol.replace(" ", "_")
        rec = {"mol": mol, "shots": {}, "issues": []}

        # ── S0: 분자 입력 (AI 입력창)
        click_input_and_type(w, mol)
        w.activate()
        rec["shots"]["s0_draw"] = ss(f"{i:02d}_{molkey}_s0_draw")

        # ── S1: 루이스 구조 버튼 (하단 좌측)
        # 루이스 구조 버튼: 창 하단 우측에 "루이스 구조" 버튼
        bx = w.left + w.width - 220
        by = w.top + w.height - 28
        pyautogui.click(bx, by)
        time.sleep(1.5)
        rec["shots"]["s1_lewis"] = ss(f"{i:02d}_{molkey}_s1_lewis")

        # ── S2: 이론적 구조 버튼
        bx2 = w.left + w.width - 100
        by2 = w.top + w.height - 28
        pyautogui.click(bx2, by2)
        time.sleep(1.5)
        rec["shots"]["s2_theory"] = ss(f"{i:02d}_{molkey}_s2_theory")

        # ── S3: 이론적 구조 선택 도구 (전체 드래그)
        # 캔버스 영역 드래그 (전체 선택 시도)
        cx1 = w.left + 60
        cy1 = w.top + 130
        cx2 = w.left + w.width - 60
        cy2 = w.top + w.height - 80
        pyautogui.moveTo(cx1, cy1)
        time.sleep(0.2)
        pyautogui.dragTo(cx2, cy2, duration=0.5, button='left')
        time.sleep(1.0)
        rec["shots"]["s3_select"] = ss(f"{i:02d}_{molkey}_s3_select")

        # 선택 해제
        pyautogui.click(w.left + w.width//2, w.top + w.height//2)
        time.sleep(0.3)

        # ── S4: 3D 팝업 버튼 (좌측 사이드바 3D 아이콘)
        # 3D 버튼은 좌측 사이드바 약 y=160 위치
        btn3d_x = w.left + 14
        btn3d_y = w.top + 160
        pyautogui.click(btn3d_x, btn3d_y)
        time.sleep(2.0)
        rec["shots"]["s4_3d"] = ss(f"{i:02d}_{molkey}_s4_3d")
        close_popup()
        time.sleep(0.5)

        # ── S5: 분광 버튼 (좌측 사이드바 분광 아이콘 ~y=215)
        btnsp_x = w.left + 14
        btnsp_y = w.top + 215
        pyautogui.click(btnsp_x, btnsp_y)
        time.sleep(1.5)
        rec["shots"]["s5_spectrum"] = ss(f"{i:02d}_{molkey}_s5_spectrum")
        close_popup()
        time.sleep(0.5)

        # 다음 분자 전 캔버스 초기화 (Ctrl+N 또는 지우기)
        pyautogui.hotkey('ctrl', 'z')
        time.sleep(0.2)
        # 지우기 버튼 클릭 (툴바 X 버튼 ~x=200, y=79)
        pyautogui.click(w.left + 200, w.top + 50)
        time.sleep(0.5)

        results.append(rec)
        print(f"  ✅ {mol} 완료")

    return results

def build_report(results):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mol_sections = ""
    for r in results:
        mol = r["mol"]
        shots_html = ""
        for stage, path in r["shots"].items():
            fname = Path(path).name if path else ""
            shots_html += f"""
            <div class="shot">
              <div class="stage-label">{stage}</div>
              <img src="{fname}" alt="{stage}" onerror="this.style.display='none'">
            </div>"""
        mol_sections += f"""
        <div class="mol-block">
          <h3>🧪 {mol}</h3>
          <div class="shots-row">{shots_html}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>ChemGrid 온그라운드 시각 검증 리포트</title>
<style>
  body {{ font-family:'Segoe UI',sans-serif; background:#111; color:#e0e0e0; margin:0; padding:20px; }}
  h1 {{ color:#64B5F6; border-bottom:2px solid #333; padding-bottom:10px; }}
  .meta {{ color:#90A4AE; font-size:13px; margin-bottom:20px; }}
  .mol-block {{ background:#1a1a2e; border:1px solid #333; border-radius:8px; padding:15px; margin-bottom:20px; }}
  .mol-block h3 {{ color:#90CAF9; margin-top:0; }}
  .shots-row {{ display:flex; flex-wrap:wrap; gap:10px; }}
  .shot {{ text-align:center; }}
  .stage-label {{ font-size:11px; color:#546E7A; margin-bottom:4px; font-weight:bold; }}
  .shot img {{ width:260px; border:1px solid #333; border-radius:4px; }}
</style>
</head>
<body>
<h1>⚗️ ChemGrid 온그라운드 시각 검증 리포트</h1>
<div class="meta">생성: {ts} | 실제 앱 직접 조작 스크린샷</div>
{mol_sections}
</body>
</html>"""

    report_path = OUTDIR / "report_onground.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n📄 리포트: {report_path}")
    return str(report_path)

if __name__ == "__main__":
    print("=== ChemGrid 온그라운드 시각 검증 시작 ===")
    results = run_test()
    build_report(results)
    print("=== 완료 ===")
