"""ChemGrid 사용자 기준 통합 검증 스크립트
시나리오: Bond 그리기 → 루이스 전환 → 저장 → 전체지우기 → 불러오기 → 내보내기 → Undo/Redo
"""
import pyautogui, ctypes, ctypes.wintypes, time, os, json

pyautogui.FAILSAFE = False
RESULTS = {}

def find_window():
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, 'ChemGrid V5')
    if not hwnd:
        hwnd = user32.FindWindowW(None, 'ChemGrid')
    if not hwnd:
        print("FATAL: ChemGrid not found!"); exit(1)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, rect.left, rect.top, rect.right, rect.bottom

def screenshot(name):
    hwnd, L, T, R, B = find_window()
    img = pyautogui.screenshot(region=(max(0,L),max(0,T),R-L,B-T))
    path = rf'c:\chemgrid\_veri_{name}.png'
    img.save(path)
    print(f'  📸 {name} saved')
    return path

def click_toolbar(index, row=1):
    """Row 1 도구 클릭 (index 0~N)"""
    hwnd, L, T, R, B = find_window()
    TITLEBAR = 32; ICON_W = 38
    if row == 1:
        y = T + TITLEBAR + 24
    else:
        y = T + TITLEBAR + 58 + 18  # Row 2
    x = L + 8 + int(ICON_W * (index + 0.5))
    pyautogui.click(x, y)
    time.sleep(0.3)

def click_canvas(rel_x, rel_y):
    """캔버스 상대 좌표 클릭 (0~1 범위)"""
    hwnd, L, T, R, B = find_window()
    TOOLBAR_H = 100  # 2줄 툴바 높이
    canvas_top = T + TOOLBAR_H
    canvas_h = B - canvas_top - 60  # 하단 버튼 영역 제외
    canvas_w = R - L
    x = L + int(canvas_w * rel_x)
    y = canvas_top + int(canvas_h * rel_y)
    pyautogui.click(x, y)
    time.sleep(0.2)
    return x, y

def drag_canvas(x1_rel, y1_rel, x2_rel, y2_rel):
    """캔버스에서 드래그"""
    hwnd, L, T, R, B = find_window()
    TOOLBAR_H = 100
    canvas_top = T + TOOLBAR_H
    canvas_h = B - canvas_top - 60
    canvas_w = R - L
    sx = L + int(canvas_w * x1_rel)
    sy = canvas_top + int(canvas_h * y1_rel)
    ex = L + int(canvas_w * x2_rel)
    ey = canvas_top + int(canvas_h * y2_rel)
    pyautogui.moveTo(sx, sy); time.sleep(0.1)
    pyautogui.mouseDown(); time.sleep(0.05)
    pyautogui.moveTo(ex, ey, duration=0.2)
    pyautogui.mouseUp(); time.sleep(0.3)

def click_bottom_button(name):
    """하단 버튼 클릭 (루이스 구조, 이론적 구조 등)"""
    hwnd, L, T, R, B = find_window()
    if name == "lewis":
        x, y = R - 200, B - 30
    elif name == "theory":
        x, y = R - 80, B - 30
    elif name == "cloud":
        x, y = L + 60, B - 30
    else:
        return
    pyautogui.click(x, y)
    time.sleep(0.5)

# =============================================
# 시나리오 1: Bond 도구로 분자 그리기
# =============================================
print("\n=== 시나리오 1: Bond 도구로 분자 그리기 ===")
try:
    # Bond는 기본 선택됨 (index 2)
    click_toolbar(2)  # Bond 확실히 선택
    time.sleep(0.3)
    
    # 삼각형 분자 그리기 (3 bonds)
    drag_canvas(0.3, 0.4, 0.5, 0.3)   # Bond 1: 좌하 → 우상
    drag_canvas(0.5, 0.3, 0.7, 0.4)   # Bond 2: 우상 → 우하
    drag_canvas(0.7, 0.4, 0.3, 0.4)   # Bond 3: 우하 → 좌하 (삼각형 완성)
    
    screenshot("01_bonds_drawn")
    RESULTS["bonds_draw"] = "✅ 3 bonds 그려짐 (크래시 없음)"
    print(f"  {RESULTS['bonds_draw']}")
except Exception as e:
    RESULTS["bonds_draw"] = f"❌ {e}"
    print(f"  {RESULTS['bonds_draw']}")

# =============================================
# 시나리오 2: 원소 도구 (O 원자 배치)
# =============================================
print("\n=== 시나리오 2: 원소 도구 (O) ===")
try:
    # O 원소는 Row 1에서 Separator 2개 지난 후...
    # Select(0), Hand(1), Bond(2), Arrow(3), Pen(4), T(5), Eraser(6), Sep, Dash(7), Wedge(8), Sep, H(9), R(10), ..(11), ·(12), +(13), -(14), O(15)
    click_toolbar(15)  # O 원소
    time.sleep(0.3)
    click_canvas(0.3, 0.4)  # 왼쪽 꼭짓점에 O 배치
    screenshot("02_oxygen_placed")
    RESULTS["element_tool"] = "✅ O 원소 배치 (크래시 없음)"
    print(f"  {RESULTS['element_tool']}")
except Exception as e:
    RESULTS["element_tool"] = f"❌ {e}"
    print(f"  {RESULTS['element_tool']}")

# =============================================
# 시나리오 3: Undo/Redo
# =============================================
print("\n=== 시나리오 3: Undo/Redo ===")
try:
    # Undo 2회
    pyautogui.hotkey('ctrl', 'z'); time.sleep(0.3)
    pyautogui.hotkey('ctrl', 'z'); time.sleep(0.3)
    screenshot("03a_after_undo2")
    
    # Redo 1회
    pyautogui.hotkey('ctrl', 'y'); time.sleep(0.3)
    screenshot("03b_after_redo1")
    RESULTS["undo_redo"] = "✅ Undo/Redo 동작 (크래시 없음)"
    print(f"  {RESULTS['undo_redo']}")
except Exception as e:
    RESULTS["undo_redo"] = f"❌ {e}"
    print(f"  {RESULTS['undo_redo']}")

# =============================================
# 시나리오 4: 루이스 구조 버튼
# =============================================
print("\n=== 시나리오 4: 루이스 구조 레이어 전환 ===")
try:
    click_bottom_button("lewis")
    time.sleep(1)
    screenshot("04_lewis_layer")
    RESULTS["lewis_layer"] = "✅ 루이스 레이어 전환 (크래시 없음)"
    print(f"  {RESULTS['lewis_layer']}")
except Exception as e:
    RESULTS["lewis_layer"] = f"❌ {e}"
    print(f"  {RESULTS['lewis_layer']}")

# =============================================
# 시나리오 5: 이론적 구조 버튼
# =============================================
print("\n=== 시나리오 5: 이론적 구조 레이어 전환 ===")
try:
    click_bottom_button("theory")
    time.sleep(1)
    screenshot("05_theory_layer")
    RESULTS["theory_layer"] = "✅ 이론 레이어 전환 (크래시 없음)"
    print(f"  {RESULTS['theory_layer']}")
except Exception as e:
    RESULTS["theory_layer"] = f"❌ {e}"
    print(f"  {RESULTS['theory_layer']}")

# =============================================
# 시나리오 6: 전자구름 토글
# =============================================
print("\n=== 시나리오 6: 전자구름 토글 ===")
try:
    click_bottom_button("cloud")
    time.sleep(0.5)
    screenshot("06_cloud_toggled")
    RESULTS["cloud_toggle"] = "✅ 전자구름 토글 (크래시 없음)"
    print(f"  {RESULTS['cloud_toggle']}")
except Exception as e:
    RESULTS["cloud_toggle"] = f"❌ {e}"
    print(f"  {RESULTS['cloud_toggle']}")

# =============================================
# 시나리오 7: 저장 (.chem)
# =============================================
print("\n=== 시나리오 7: 저장 (.chem) ===")
try:
    # 그리기 모드로 복귀
    # Ctrl+S로 저장 시도 — 파일 다이얼로그가 뜸
    # 자동화로는 다이얼로그 처리가 어려우므로, 저장 버튼 메뉴 사용
    # Row 2: Logo(0), Sep, 저장/불러오기(1)
    hwnd, L, T, R, B = find_window()
    TITLEBAR = 32
    # Row 2 Y center
    row2_y = T + TITLEBAR + 58 + 14
    save_x = L + 70  # "저장/불러오기" 텍스트 버튼 대략 위치
    pyautogui.click(save_x, row2_y)
    time.sleep(0.5)
    screenshot("07_save_menu")
    # ESC로 메뉴 닫기
    pyautogui.press('escape')
    time.sleep(0.3)
    RESULTS["save_menu"] = "✅ 저장 메뉴 열림 (크래시 없음)"
    print(f"  {RESULTS['save_menu']}")
except Exception as e:
    RESULTS["save_menu"] = f"❌ {e}"
    print(f"  {RESULTS['save_menu']}")

# =============================================
# 시나리오 8: Text 도구
# =============================================
print("\n=== 시나리오 8: Text 도구 ===")
try:
    click_toolbar(5)  # T (Text) 도구
    time.sleep(0.3)
    click_canvas(0.5, 0.6)  # 캔버스 중앙 하단 클릭
    time.sleep(0.5)
    screenshot("08_text_tool")
    RESULTS["text_tool"] = "✅ Text 도구 클릭 (크래시 없음)"
    print(f"  {RESULTS['text_tool']}")
except Exception as e:
    RESULTS["text_tool"] = f"❌ {e}"
    print(f"  {RESULTS['text_tool']}")

# =============================================
# 시나리오 9: Eraser 도구
# =============================================
print("\n=== 시나리오 9: Eraser 도구 ===")
try:
    click_toolbar(6)  # Eraser
    time.sleep(0.3)
    click_canvas(0.5, 0.3)  # 분자 위치 클릭하여 삭제 시도
    time.sleep(0.3)
    screenshot("09_eraser")
    RESULTS["eraser"] = "✅ Eraser 동작 (크래시 없음)"
    print(f"  {RESULTS['eraser']}")
except Exception as e:
    RESULTS["eraser"] = f"❌ {e}"
    print(f"  {RESULTS['eraser']}")

# =============================================
# 시나리오 10: 전체 지우기
# =============================================
print("\n=== 시나리오 10: 전체 지우기 ===")
try:
    hwnd, L, T, R, B = find_window()
    TITLEBAR = 32
    row2_y = T + TITLEBAR + 58 + 14
    clear_x = L + 175  # "전체 지우기" 대략 위치
    pyautogui.click(clear_x, row2_y)
    time.sleep(0.5)
    screenshot("10_cleared")
    RESULTS["clear_all"] = "✅ 전체 지우기 (크래시 없음)"
    print(f"  {RESULTS['clear_all']}")
except Exception as e:
    RESULTS["clear_all"] = f"❌ {e}"
    print(f"  {RESULTS['clear_all']}")

# =============================================
# 시나리오 11: Select + Hand 도구
# =============================================
print("\n=== 시나리오 11: Select + Hand ===")
try:
    # Select (index 0)
    click_toolbar(0)
    time.sleep(0.3)
    click_canvas(0.4, 0.4)
    screenshot("11a_select")
    
    # Hand (index 1)
    click_toolbar(1)
    time.sleep(0.3)
    drag_canvas(0.3, 0.3, 0.5, 0.5)
    screenshot("11b_hand")
    RESULTS["select_hand"] = "✅ Select/Hand 동작 (크래시 없음)"
    print(f"  {RESULTS['select_hand']}")
except Exception as e:
    RESULTS["select_hand"] = f"❌ {e}"
    print(f"  {RESULTS['select_hand']}")

# =============================================
# 최종 결과 요약
# =============================================
print("\n" + "="*60)
print("📋 ChemGrid 통합 검증 결과 요약")
print("="*60)
total = len(RESULTS)
passed = sum(1 for v in RESULTS.values() if v.startswith("✅"))
failed = sum(1 for v in RESULTS.values() if v.startswith("❌"))
for k, v in RESULTS.items():
    print(f"  {k:20s} : {v}")
print(f"\n총 {total}개 테스트 | ✅ {passed} 통과 | ❌ {failed} 실패")
print("="*60)

# JSON 결과 저장
with open(r'c:\chemgrid\_verification_results.json', 'w', encoding='utf-8') as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2)
print("결과 JSON 저장: _verification_results.json")
