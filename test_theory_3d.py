"""이론적 구조 → 입체 구조 3D 팝업 테스트"""
import time
import win32gui, win32con
import pyautogui
import PIL.ImageGrab

def find_chemgrid_hwnd():
    result = []
    def cb(hwnd, extra):
        title = win32gui.GetWindowText(hwnd)
        if 'ChemGrid' in title and win32gui.IsWindowVisible(hwnd):
            result.append((hwnd, title))
    win32gui.EnumWindows(cb, None)
    return result

hwnds = find_chemgrid_hwnd()
if not hwnds:
    print("ERROR: ChemGrid 없음"); exit(1)

hwnd, title = hwnds[0]
win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
win32gui.SetForegroundWindow(hwnd)
time.sleep(1)

rect = win32gui.GetWindowRect(hwnd)
left, top, right, bottom = rect
w = right - left
h = bottom - top
print(f"창: {rect}, {w}x{h}")

margin = 25

# "이론적 구조" 버튼 위치 계산
# view_container: width=240, height=50
# position: (right - 240 - margin, bottom - 50 - margin)
vc_left = right - 240 - margin
vc_top  = bottom - 50 - margin

# "이론적 구조" 버튼 = view_container 오른쪽 절반 중앙
theory_btn_x = vc_left + 240 - 55   # 오른쪽 버튼 중앙
theory_btn_y = vc_top + 25           # 버튼 중앙

print(f"이론적 구조 버튼 예상 좌표: ({theory_btn_x}, {theory_btn_y})")

# 이론적 구조 버튼 클릭
pyautogui.click(theory_btn_x, theory_btn_y)
time.sleep(2)

# 스크린샷 (이론적 구조 레이어)
img = PIL.ImageGrab.grab()
img.save('c:/chemgrid/test_theory.png')
print("이론적 구조 스크린샷 저장")

# "입체 구조" 버튼 위치 계산
# btn_3d position: (right - 200 - margin, bottom - 50 - margin - btn_back.height - 10)
# btn_back: height=50, btn_3d: height=50
btn_3d_x = right - 200 - margin + 100   # 중앙
btn_3d_y = bottom - 50 - margin - 50 - 10 + 25  # btn_3d 중앙
print(f"입체 구조(3D) 버튼 예상 좌표: ({btn_3d_x}, {btn_3d_y})")

pyautogui.click(btn_3d_x, btn_3d_y)
time.sleep(4)  # 3D 팝업 열릴 때까지 대기

# 스크린샷 (3D 팝업)
img2 = PIL.ImageGrab.grab()
img2.save('c:/chemgrid/test_3d_popup.png')
print("3D 팝업 스크린샷 저장")
print("=== 완료 ===")
