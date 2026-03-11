"""ChemGrid 시각 테스트 — benzene 입력 후 스크린샷"""
import time
import subprocess
import sys

try:
    import pyautogui
    import win32gui
    import win32con
    import PIL.ImageGrab
except ImportError as e:
    print(f"필요 패키지 없음: {e}")
    sys.exit(1)

def find_chemgrid_hwnd():
    """ChemGrid 윈도우 핸들 찾기"""
    result = []
    def cb(hwnd, extra):
        title = win32gui.GetWindowText(hwnd)
        if 'ChemGrid' in title and win32gui.IsWindowVisible(hwnd):
            result.append((hwnd, title))
    win32gui.EnumWindows(cb, None)
    return result

# 1. ChemGrid 창 찾기
hwnds = find_chemgrid_hwnd()
if not hwnds:
    print("ERROR: ChemGrid 창을 찾을 수 없습니다!")
    sys.exit(1)

hwnd, title = hwnds[0]
print(f"ChemGrid 찾음: hwnd={hwnd}, title='{title}'")

# 2. 창 최대화 + 포커스
win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
win32gui.SetForegroundWindow(hwnd)
time.sleep(1.5)

# 3. 창 위치/크기 확인
rect = win32gui.GetWindowRect(hwnd)
left, top, right, bottom = rect
w = right - left
h = bottom - top
print(f"창 위치: {rect}, 크기: {w}x{h}")

# 4. 하단 AI 입력창 위치 계산 (하단 중앙, bottom-18px 위치)
input_x = left + w // 2
input_y = bottom - 28  # 하단에서 28px 위
print(f"입력창 예상 좌표: ({input_x}, {input_y})")

# 5. 스크린샷 (before)
img_before = PIL.ImageGrab.grab()
img_before.save('c:/chemgrid/test_before.png')
print("Before 스크린샷 저장")

# 6. 입력창 클릭
pyautogui.click(input_x, input_y)
time.sleep(0.5)
pyautogui.hotkey('ctrl', 'a')  # 기존 텍스트 전체 선택
pyautogui.typewrite('benzene', interval=0.05)
time.sleep(0.3)
pyautogui.press('enter')
print("'benzene' 입력 후 Enter")

# 7. 결과 대기 (benzene 그리기 완료까지)
time.sleep(3)

# 8. 스크린샷 (after - benzene 그려진 후)
img_after = PIL.ImageGrab.grab()
img_after.save('c:/chemgrid/test_after_benzene.png')
print("After 스크린샷 저장: test_after_benzene.png")

print("=== 완료 ===")
