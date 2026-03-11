"""ISSUE-1, ISSUE-3 시각 테스트"""
import time
import win32gui, win32con
import pyautogui
import PIL.ImageGrab

def find_chemgrid():
    result = []
    def cb(hwnd, extra):
        t = win32gui.GetWindowText(hwnd)
        if 'ChemGrid' in t and win32gui.IsWindowVisible(hwnd):
            result.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return result[0] if result else None

hwnd = find_chemgrid()
if not hwnd:
    print("ChemGrid not found"); exit(1)

win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
win32gui.SetForegroundWindow(hwnd)
time.sleep(1)

rect = win32gui.GetWindowRect(hwnd)
L, T, R, B = rect
W = R - L
print(f"창: {rect}")

# 1. 현재 3D popup이 열려있으면 닫기 (Escape)
pyautogui.press('escape')
time.sleep(0.5)

# 2. "그리기 화면으로 복귀" 클릭 (녹색 버튼)
back_x = R - 200 - 25 + 100  # btn_back 중앙 x
back_y = B - 50 - 25 + 25    # btn_back 중앙 y
print(f"그리기 복귀 버튼: ({back_x}, {back_y})")
pyautogui.click(back_x, back_y)
time.sleep(1)

# 3. 캔버스 전체 지우기 (Ctrl+A → Delete, 또는 "전체 지우기" 버튼)
# 전체 지우기 버튼은 toolbar의 "전체 지우기" 텍스트 위치 
# 대략 x=200, y=103 위치 (상단 2번째 줄 버튼)
pyautogui.click(L + 200, T + 48)  # "전체 지우기" 버튼 클릭
time.sleep(0.5)
# 확인 다이얼로그 "예" 클릭
pyautogui.press('enter')
time.sleep(0.5)

# 4. 입력창에 "cyclopentadienyl anion" 입력
input_x = L + W // 2
input_y = B - 28
pyautogui.click(input_x, input_y)
time.sleep(0.3)
pyautogui.hotkey('ctrl', 'a')
pyautogui.typewrite('cp-', interval=0.05)
pyautogui.press('enter')
time.sleep(3)

# 스크린샷 (Cp- 전자구름 확인)
img1 = PIL.ImageGrab.grab()
img1.save('c:/chemgrid/test_cp_anion.png')
print("Cp- 스크린샷 저장")

# 5. 이론적 구조로 전환 → 전자구름 확인
# "이론적 구조" 버튼 클릭
vc_left = R - 240 - 25
theory_x = vc_left + 240 - 55
theory_y = B - 50 - 25 + 25
print(f"이론적 구조 버튼: ({theory_x}, {theory_y})")
pyautogui.click(theory_x, theory_y)
time.sleep(2)

img2 = PIL.ImageGrab.grab()
img2.save('c:/chemgrid/test_cp_theory.png')
print("Cp- 이론적 구조 스크린샷 저장")

# 6. 캔버스 지우기 후 ethanol 테스트 (ISSUE-3)
pyautogui.click(L + 200, T + 48)
time.sleep(0.3)
pyautogui.press('enter')
time.sleep(0.3)

# 그리기 화면으로 돌아가기
back_x2 = R - 200 - 25 + 100
back_y2 = B - 50 - 25 + 25
pyautogui.click(back_x2, back_y2)
time.sleep(1)

# CCO (에탄올) 입력
pyautogui.click(input_x, input_y)
time.sleep(0.3)
pyautogui.hotkey('ctrl', 'a')
pyautogui.typewrite('CCO', interval=0.05)
pyautogui.press('enter')
time.sleep(3)

img3 = PIL.ImageGrab.grab()
img3.save('c:/chemgrid/test_ethanol.png')
print("에탄올 스크린샷 저장")

# 이론적 구조 → 입체 구조 (SMILES 인식 테스트)
pyautogui.click(theory_x, theory_y)
time.sleep(2)
# 입체 구조 버튼
btn_3d_x = R - 200 - 25 + 100
btn_3d_y = B - 50 - 25 - 50 - 10 + 25
pyautogui.click(btn_3d_x, btn_3d_y)
time.sleep(4)

img4 = PIL.ImageGrab.grab()
img4.save('c:/chemgrid/test_ethanol_3d.png')
print("에탄올 3D 스크린샷 저장")
print("=== 완료 ===")
