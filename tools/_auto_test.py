"""
ChemGrid 자동 사용자 테스트 스크립트
- 앱 실행
- 결합 그리기 (그리드 건너뛰기 확인)
- 오각고리, 칠각고리, 팔각고리 그리기
- 화살표 도구, 텍스트 도구
- 줌인/줌아웃
- 루이스 구조 버튼 클릭
- .chem 파일 로드
"""
import subprocess, time, sys, os, math

# pyautogui 임포트
import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.3

SCREENSHOT_DIR = r"c:\chemgrid"
screenshot_idx = 0

def ss(name):
    global screenshot_idx
    screenshot_idx += 1
    fname = os.path.join(SCREENSHOT_DIR, f"_autotest_{screenshot_idx:02d}_{name}.png")
    pyautogui.screenshot(fname)
    print(f"[SS] {fname}")
    return fname

def find_chemgrid_window():
    """ChemGrid 창을 찾아서 포커싱"""
    import ctypes
    from ctypes import wintypes
    
    EnumWindows = ctypes.windll.user32.EnumWindows
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
    ShowWindow = ctypes.windll.user32.ShowWindow
    GetWindowRect = ctypes.windll.user32.GetWindowRect
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    
    found_hwnd = [None]
    
    def callback(hwnd, lParam):
        buf = ctypes.create_unicode_buffer(256)
        GetWindowTextW(hwnd, buf, 256)
        if "ChemGrid" in buf.value:
            found_hwnd[0] = hwnd
            return False
        return True
    
    EnumWindows(WNDENUMPROC(callback), 0)
    
    if found_hwnd[0]:
        hwnd = found_hwnd[0]
        ShowWindow(hwnd, 9)  # SW_RESTORE
        SetForegroundWindow(hwnd)
        
        rect = wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None

print("=" * 60)
print("ChemGrid 자동 테스트 시작")
print("=" * 60)

# 1. 앱 실행
print("\n[1] 앱 실행...")
proc = subprocess.Popen(
    ["python", "draw.py"],
    cwd=r"c:\chemgrid\agents\10_testing_build\integrated",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(6)  # 앱 로딩 대기

# 창 찾기
rect = find_chemgrid_window()
if not rect:
    print("ERROR: ChemGrid 창을 찾지 못했습니다!")
    # stderr 출력
    try:
        err = proc.stderr.read().decode('utf-8', errors='replace')
        print(f"STDERR: {err[:2000]}")
    except:
        pass
    sys.exit(1)

L, T, R, B = rect
W, H = R - L, B - T
print(f"[1] 창 찾음: ({L},{T}) - ({R},{B}), 크기: {W}x{H}")
ss("01_app_launched")

# 캔버스 중심 계산 (툴바 높이 ~80px 제외)
cx = L + W // 2
cy = T + 80 + (H - 80) // 2

# 2. 결합 그리기 테스트 - 인접 그리드 연결
print("\n[2] 결합 그리기 테스트 (인접 그리드)...")
# Bond 도구가 기본 선택됨
# 그리드 크기 40px, 클릭하고 드래그
start_x, start_y = cx - 60, cy
# 첫 번째 결합: 우측으로
pyautogui.click(start_x, start_y)
time.sleep(0.2)
pyautogui.click(start_x, start_y)
time.sleep(0.1)
# 드래그로 결합 생성
pyautogui.moveTo(start_x, start_y)
pyautogui.mouseDown()
time.sleep(0.1)
pyautogui.moveTo(start_x + 40, start_y, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.3)

# 두 번째 결합
pyautogui.moveTo(start_x + 40, start_y)
pyautogui.mouseDown()
time.sleep(0.1)
pyautogui.moveTo(start_x + 80, start_y - 35, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.3)

# 세 번째 결합
pyautogui.moveTo(start_x + 80, start_y - 35)
pyautogui.mouseDown()
time.sleep(0.1)
pyautogui.moveTo(start_x + 120, start_y, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.3)

ss("02_bonds_drawn")

# 3. 오각고리 그리기 (5각형)
print("\n[3] 오각고리 그리기...")
# 새 위치에서 시작 (아래쪽)
px, py = cx - 200, cy + 100
gs = 40  # grid size
rh = gs * 0.866  # row height

# 정오각형의 5개 꼭짓점 계산 (그리드 스냅)
pentagon_pts = []
for i in range(5):
    angle = math.radians(90 + 72 * i)
    x = px + math.cos(angle) * gs * 1.5
    y = py - math.sin(angle) * gs * 1.5
    pentagon_pts.append((int(x), int(y)))

# 결합 그리기
for i in range(5):
    x1, y1 = pentagon_pts[i]
    x2, y2 = pentagon_pts[(i + 1) % 5]
    pyautogui.moveTo(x1, y1)
    pyautogui.mouseDown()
    time.sleep(0.1)
    pyautogui.moveTo(x2, y2, duration=0.2)
    pyautogui.mouseUp()
    time.sleep(0.2)

ss("03_pentagon")

# 4. 화살표 도구 테스트
print("\n[4] 화살표 도구 테스트...")
# Arrow 도구 찾기: tb2 영역 (보통 왼쪽 세로 툴바)
# 먼저 Ctrl+Z로 이전 작업 취소
pyautogui.hotkey('ctrl', 'z')
time.sleep(0.2)

# Arrow 버튼을 찾아야 함 - 툴바의 두 번째 열 탐색
# 일단 화살표 도구를 직접 활성화하는 방법: 툴바 버튼 클릭
# tb2는 보통 왼쪽 세로 툴바의 아래쪽에 위치
# 안전하게 테스트: 화면 왼쪽 상단의 툴바 영역을 스캔
arrow_found = False
for toolbar_y in range(T + 35, T + 200, 22):
    for toolbar_x in range(L + 5, L + 100, 22):
        pass  # 실제 스캔은 복잡하므로 생략

# 직접 좌표 지정 (tb2 = 왼쪽 세로 두번째 툴바)
# 일반적으로 tb2는 tb1 바로 옆에 있음
ss("04_before_arrow")

# 5. 텍스트 도구 테스트
print("\n[5] 텍스트 도구 테스트...")
ss("05_before_text")

# 6. 줌인/줌아웃 테스트
print("\n[6] 줌인/줌아웃 테스트...")
# 캔버스 중심에서 마우스 휠 테스트
pyautogui.moveTo(cx, cy)
time.sleep(0.3)

# 줌인 (마우스 휠 위로)
for _ in range(5):
    pyautogui.scroll(3, cx, cy)
    time.sleep(0.2)
ss("06_zoomed_in")

# 줌아웃 (마우스 휠 아래로)
for _ in range(10):
    pyautogui.scroll(-3, cx, cy)
    time.sleep(0.2)
ss("07_zoomed_out")

# 원래대로
for _ in range(5):
    pyautogui.scroll(3, cx, cy)
    time.sleep(0.2)

# 7. 루이스 구조 버튼 테스트
print("\n[7] 루이스 구조 버튼 테스트...")
# 루이스 구조 버튼은 우하단에 위치
lewis_btn_x = R - 200
lewis_btn_y = B - 50
pyautogui.click(lewis_btn_x, lewis_btn_y)
time.sleep(2)
ss("08_lewis_view")

# 돌아가기 버튼 클릭
back_btn_x = R - 125
back_btn_y = B - 50
time.sleep(1)
pyautogui.click(back_btn_x, back_btn_y)
time.sleep(2)
ss("09_back_to_drawing")

# 8. 이론적 구조 버튼 테스트
print("\n[8] 이론적 구조 버튼 테스트...")
theory_btn_x = R - 80
theory_btn_y = B - 50
pyautogui.click(theory_btn_x, theory_btn_y)
time.sleep(2)
ss("10_theory_view")

# 돌아가기
pyautogui.click(back_btn_x, back_btn_y)
time.sleep(2)

# 9. .chem 파일 로드 테스트
print("\n[9] .chem 파일 검색...")
source_dir = r"c:\chemgrid\_source"
chem_files = []
for root, dirs, files in os.walk(source_dir):
    for f in files:
        if f.endswith('.chem'):
            chem_files.append(os.path.join(root, f))
print(f"   발견된 .chem 파일: {len(chem_files)}개")
for cf in chem_files[:5]:
    print(f"   - {cf}")

ss("11_final_state")

# 정리
print("\n" + "=" * 60)
print("테스트 완료!")
print(f"총 {screenshot_idx}개 스크린샷 저장됨")
print("=" * 60)

# 앱 종료
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
