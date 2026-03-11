"""ChemGrid Arrow 도구 자동 테스트"""
import pyautogui, time, ctypes, ctypes.wintypes

user32 = ctypes.windll.user32
hwnd = user32.FindWindowW(None, 'ChemGrid')
if hwnd == 0:
    print("FAIL: ChemGrid not found"); exit(1)

user32.SetForegroundWindow(hwnd)
user32.ShowWindow(hwnd, 9)
time.sleep(0.5)

rect = ctypes.wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
L, T, R, B = rect.left, rect.top, rect.right, rect.bottom
W, H = R - L, B - T
print(f"Window: {L},{T} {W}x{H}")

# 1. Arrow 버튼 클릭 (하단 툴바 3번째 아이콘 - → 화살표)
# 하단 툴바(row 2)의 → 아이콘 위치 추정 (Bond=1, Pen=2, Arrow=3)
# Row 2 Y좌표: T + 약 75px (두번째 툴바 행)
# Arrow 아이콘 X좌표: L + 약 110px (3번째 아이콘)
arrow_x = L + 110
arrow_y = T + 77
print(f"Clicking Arrow tool at ({arrow_x}, {arrow_y})")
pyautogui.click(arrow_x, arrow_y)
time.sleep(0.5)

# 2. 캔버스에서 화살표 드래그 (왼쪽→오른쪽)
canvas_x1 = L + 200
canvas_y1 = T + 350  # 캔버스 중앙
canvas_x2 = L + 500
canvas_y2 = T + 350
print(f"Drawing arrow: ({canvas_x1},{canvas_y1}) -> ({canvas_x2},{canvas_y2})")
pyautogui.moveTo(canvas_x1, canvas_y1)
time.sleep(0.2)
pyautogui.mouseDown()
time.sleep(0.1)
pyautogui.moveTo(canvas_x2, canvas_y2, duration=0.5)
time.sleep(0.1)
pyautogui.mouseUp()
time.sleep(0.5)

# 3. 스크린샷
img = pyautogui.screenshot(region=(max(0,L), max(0,T), W, H))
img.save(r'c:\chemgrid\_screenshot_arrow_test.png')
print("Arrow test screenshot saved")
