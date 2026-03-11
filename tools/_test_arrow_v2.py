"""Arrow 도구 정밀 테스트: 
1. ChemGrid 창 찾기
2. Arrow 버튼 정확한 위치 탐색 (Accessibility API)
3. Arrow 클릭 → 캔버스 드래그 → 스크린샷
4. 로그 확인
"""
import pyautogui, time, ctypes, ctypes.wintypes, subprocess, sys, os

user32 = ctypes.windll.user32

# 1. ChemGrid 찾기
hwnd = user32.FindWindowW(None, 'ChemGrid')
if hwnd == 0:
    print("ChemGrid not found!")
    sys.exit(1)

user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

rect = ctypes.wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
L, T, R, B = rect.left, rect.top, rect.right, rect.bottom
W, H = R - L, B - T
print(f"Window at: ({L},{T}) {W}x{H}")

# 2. 스크린샷으로 현재 상태 확인
img = pyautogui.screenshot(region=(max(0,L), max(0,T), W, H))
img.save(r'c:\chemgrid\_screenshot_before_arrow.png')
print("Before-arrow screenshot saved")

# 3. 툴바의 Arrow 버튼 위치 추정
# toolbar_setup.py의 순서: Select, Hand, Bond, **Arrow**, Pen, Text, Eraser
# 각 아이콘 약 38px 폭 (34px icon + 4px padding)
# tb 시작 X: 약 L + 8 (왼쪽 마진)
# tb Y: 타이틀바 약 32px + tb 중앙
TITLEBAR_H = 32
ICON_W = 38
TB_Y = T + TITLEBAR_H + 29  # tb 중앙 (높이 58, 중앙 29)

# Select=0, Hand=1, Bond=2, Arrow=3
ARROW_IDX = 3
ARROW_X = L + 8 + int(ICON_W * (ARROW_IDX + 0.5))

print(f"Calculated Arrow button at: ({ARROW_X}, {TB_Y})")
print(f"  (Index={ARROW_IDX}, each icon ~{ICON_W}px wide)")

# 4. Arrow 버튼 클릭
pyautogui.click(ARROW_X, TB_Y)
time.sleep(0.5)

# 5. 캔버스에 화살표 드래그 (좌→우, 캔버스 중앙)
# tb1 높이 58 + tb2 높이 36 = 94px below titlebar
CANVAS_TOP = T + TITLEBAR_H + 58 + 36 + 10
cx1 = L + 200
cy = T + (H // 2)  # 수직 중앙
cx2 = L + 600

print(f"Drawing: ({cx1},{cy}) -> ({cx2},{cy})")
pyautogui.moveTo(cx1, cy)
time.sleep(0.2)
pyautogui.mouseDown(button='left')
time.sleep(0.1)
# 중간 지점 (고스트 확인용)
for step in range(5):
    sx = cx1 + (cx2 - cx1) * (step + 1) // 5
    pyautogui.moveTo(sx, cy, duration=0.1)
time.sleep(0.1)
pyautogui.mouseUp(button='left')
time.sleep(0.5)

# 6. 결과 스크린샷
img2 = pyautogui.screenshot(region=(max(0,L), max(0,T), W, H))
img2.save(r'c:\chemgrid\_screenshot_after_arrow.png')
print("After-arrow screenshot saved")

# 7. 로그 확인
for logfile in [r'c:\chemgrid\_chemgrid_stdout.log', r'c:\chemgrid\_chemgrid_stderr.log']:
    if os.path.exists(logfile):
        content = open(logfile, encoding='utf-8', errors='replace').read()
        if content:
            tag = 'STDOUT' if 'stdout' in logfile else 'STDERR'
            # Arrow 관련 로그만 필터
            for line in content.split('\n'):
                if 'ARROW' in line or 'TOOLBAR' in line or 'Error' in line or 'Traceback' in line:
                    print(f"[{tag}] {line}")
print("DONE")
