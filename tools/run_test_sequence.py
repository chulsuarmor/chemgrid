"""ChemGrid 시각 검증 시퀀스 — pyautogui 테스트"""
import time
import pyautogui
import pygetwindow as gw
from pathlib import Path
from datetime import datetime

SHOT_DIR = Path(r"c:\chemgrid\tools\test_screenshots")
SHOT_DIR.mkdir(parents=True, exist_ok=True)

def shot(name):
    p = SHOT_DIR / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
    pyautogui.screenshot(str(p))
    print(f"[SHOT] {p.name}")
    return p

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ── 창 찾기 ─────────────────────────────────────────────────────────
wins = gw.getWindowsWithTitle("ChemGrid V5")
if not wins:
    log("ChemGrid 창 없음!")
    exit(1)

w = wins[0]
WX, WY, WW, WH = w.left, w.top, w.width, w.height
log(f"창 위치: ({WX},{WY}) 크기: {WW}x{WH}")

# 창 활성화
try:
    w.activate()
except Exception:
    pass
time.sleep(0.8)
shot("00_start")

# ── [Step 1] AI 입력창에 benzene 입력 ────────────────────────────────
# AI 입력창 좌표 (main_window.py resizeEvent 기준)
input_w = min(580, WW - 160)
gap = 8
btn_w = 38
total_w = input_w + gap + btn_w
ix = WX + (WW - total_w) // 2 + input_w // 2   # 입력창 중앙 X
iy = WY + WH - 38 - 18 + 19                      # 입력창 중앙 Y

log(f"AI 입력창 클릭: ({ix},{iy})")
pyautogui.click(ix, iy)
time.sleep(0.3)
pyautogui.hotkey("ctrl", "a")
pyautogui.write("benzene", interval=0.06)
shot("01_typing_benzene")

pyautogui.press("enter")
time.sleep(2.5)  # RDKit 그리기 완료 대기
shot("02_benzene_drawn")
log("benzene 그리기 완료 (또는 시도)")

# ── [Step 2] Theory 모드 전환 ────────────────────────────────────────
# view_container 위치: (WX + WW - 240 - 25 + 120, WY + WH - 50 - 25 + 25)
# '이론적 구조' 버튼은 두 번째 버튼 (110px 더 오른쪽)
theory_x = WX + WW - 25 - 120 + 55  # 오른쪽 버튼 중앙
theory_y = WY + WH - 25 - 25         # 버튼 Y 중앙

log(f"이론적 구조 버튼 클릭: ({theory_x},{theory_y})")
pyautogui.click(theory_x, theory_y)
time.sleep(1.8)  # 애니메이션 완료 대기
shot("03_theory_mode")
log("Theory 모드 전환")

# ── [Step 3] 입체 구조(3D) 버튼 클릭 ────────────────────────────────
# btn_3d 위치: btn_back보다 60px 위 = (WX + WW - 25 - 100, WY + WH - 25 - 50 - 60)
btn3d_x = WX + WW - 25 - 100
btn3d_y = WY + WH - 25 - 50 - 10 - 25   # 돌아가기 버튼 위

log(f"입체 구조 버튼 클릭: ({btn3d_x},{btn3d_y})")
pyautogui.click(btn3d_x, btn3d_y)
time.sleep(4.0)  # 3D 팝업 로딩 대기 (RDKit 3D 계산)
shot("04_3d_popup")
log("3D 팝업 클릭 완료")

# ── [Step 4] 3D 팝업 창 확인 ─────────────────────────────────────────
wins_3d = gw.getWindowsWithTitle("ChemGrid — 통합 3D 분자 분석")
if wins_3d:
    popup = wins_3d[0]
    log(f"3D 팝업 확인됨: pos=({popup.left},{popup.top}) size={popup.width}x{popup.height}")
    # 팝업만 캡처
    region = (popup.left, popup.top, popup.width, popup.height)
    p = SHOT_DIR / f"05_3d_popup_only_{datetime.now().strftime('%H%M%S')}.png"
    pyautogui.screenshot(str(p), region=region)
    log(f"3D 팝업 단독 캡처: {p.name}")
else:
    log("3D 팝업이 열리지 않음 — 버튼 좌표 재시도")
    # 대안: 화면 전체 스캔 후 보고
    shot("05_no_popup_fallback")

# ── 최종 스크린샷 ─────────────────────────────────────────────────────
time.sleep(1.0)
shot("99_final")
log("테스트 완료! 스크린샷 디렉토리: " + str(SHOT_DIR))
log("모든 스크린샷을 tools/test_screenshots/ 에서 확인하세요.")
