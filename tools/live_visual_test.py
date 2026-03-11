"""
live_visual_test.py — ChemGrid 실제 화면 시각 검증 스크립트
사용자 환경 피드백 사이클: 앱 실행 → 분자 입력 → 스크린샷 → HTML 보고서

테스트 분자:
  1. benzene (방향족)
  2. naphthalene (다환 방향족)
  3. caffeine (복잡한 이중고리)
  4. aspirin (약물, 방향족+산기)
  5. biphenyl (수동 그리기 시뮬레이션 → c1ccc(-c2ccccc2)cc1 SMILES 직접)
  6. cp- (이온성 방향족)
  7. tropylium (이온성 방향족)
  8. cholesterol (대형 스테로이드)
  9. adenine (핵산 염기)
  10. hemoglobin (대형 단백질 → heme fallback)
"""
import time, os, sys
import pygetwindow as gw
import pyautogui
import pyautogui as pg
from PIL import ImageGrab

OUT = r"c:\chemgrid\docs\reports\live_test"
os.makedirs(OUT, exist_ok=True)

# ── 창 탐지 (VS Code, 탐색기 제외) ─────────────────────────────────────
def find_chemgrid():
    for t in gw.getAllTitles():
        if "Visual Studio Code" in t or "탐색기" in t or "cmd" in t.lower():
            continue
        if "ChemGrid" in t:
            wins = gw.getWindowsWithTitle(t)
            for w in wins:
                if w.width > 300:
                    return w
    return None

def activate_win(w, retries=3):
    for _ in range(retries):
        try:
            w.activate(); time.sleep(0.8)
            return True
        except Exception:
            time.sleep(0.5)
    return False

def screenshot(name):
    path = os.path.join(OUT, f"{name}.png")
    try:
        img = ImageGrab.grab()
        img.save(path)
        print(f"  [Screenshot] {path}")
    except Exception as e:
        print(f"  [Screenshot FAIL] {e}")
    return path

# ── 분자 입력 (텍스트 입력창으로) ────────────────────────────────────────
def type_molecule(w, name):
    """입력창을 클릭하고 분자명 입력 후 Enter"""
    # 입력창 위치: 창 하단 중앙
    win_cx = w.left + w.width // 2
    win_iy = w.top + w.height - 38 - 18  # resizeEvent 계산과 동일
    
    # 입력창 클릭
    pg.click(win_cx, win_iy + 10)
    time.sleep(0.3)
    
    # 기존 텍스트 지우기
    pg.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pg.hotkey('delete')
    time.sleep(0.1)
    
    # 분자명 입력
    pg.write(name, interval=0.05)
    time.sleep(0.3)
    pg.press('enter')
    time.sleep(1.5)  # 그리기 완료 대기

def click_theory_btn(w):
    """이론적 구조 버튼 클릭 (우하단 '이론적 구조' 버튼)"""
    # 이론적 구조 버튼 위치: 우하단 view_container 내
    # view_container: right-margin=25, bottom-margin=25, width=240, height=50
    # btn_theory는 view_container 내 두 번째 버튼 (110px × 2 + 간격)
    bx = w.left + w.width - 25 - 240 + 120 + 10  # 두번째 버튼 중앙
    by = w.top + w.height - 25 - 25  # 버튼 중앙
    pg.click(bx, by)
    time.sleep(1.5)

def click_back_btn(w):
    """그리기 화면으로 복귀 버튼"""
    # btn_back: right=25, bottom=25, size=200x50
    bx = w.left + w.width - 25 - 100  # 버튼 중앙
    by = w.top + w.height - 25 - 25
    pg.click(bx, by)
    time.sleep(0.8)

def drag_select_all(w):
    """캔버스 전체 드래그 선택 (이론 구조 탭에서)"""
    # 캔버스 좌상 → 우하 드래그
    x1 = w.left + 100
    y1 = w.top + 80
    x2 = w.left + w.width - 200  # 버튼 제외
    y2 = w.top + w.height - 100
    pg.moveTo(x1, y1)
    time.sleep(0.2)
    pg.mouseDown(button='left')
    pg.moveTo(x2, y2, duration=0.5)
    pg.mouseUp(button='left')
    time.sleep(0.5)

# ── 메인 테스트 ────────────────────────────────────────────────────────
def run_test():
    print("=== ChemGrid 시각 검증 시작 ===")
    
    w = find_chemgrid()
    if not w:
        print("[FAIL] ChemGrid V5 창을 찾을 수 없습니다.")
        return []
    
    print(f"[OK] 창 발견: '{w.title}' @ ({w.left},{w.top}) {w.width}x{w.height}")
    activate_win(w)
    time.sleep(0.5)
    
    results = []
    
    MOLECULES = [
        ("benzene",         "벤젠 (방향족)"),
        ("naphthalene",     "나프탈렌 (다환 방향족)"),
        ("caffeine",        "카페인 (이중고리 복합)"),
        ("aspirin",         "아스피린 (방향족+산기)"),
        ("c1ccc(-c2ccccc2)cc1", "바이페닐 (SMILES 직접입력)"),
        ("cp-",             "CP- (이온성 방향족)"),
        ("tropylium",       "트로필리움 (이온성 방향족)"),
        ("adenine",         "아데닌 (핵산 염기)"),
        ("cholesterol",     "콜레스테롤 (대형 스테로이드)"),
        ("hemoglobin",      "헤모글로빈 (→ heme fallback)"),
    ]
    
    for mol_id, (mol_name, desc) in enumerate(MOLECULES):
        print(f"\n[{mol_id+1}/{len(MOLECULES)}] {desc} ({mol_name})")
        
        # 그리기 모드 복귀 확인
        if mol_id > 0:
            activate_win(w)
            click_back_btn(w)
        
        activate_win(w)
        
        # S0: 분자 텍스트 입력
        type_molecule(w, mol_name)
        sc_draw = screenshot(f"{mol_id+1:02d}_{mol_id+1}_s0_draw_{mol_name[:20].replace('/','_')}")
        
        # S1: 이론적 구조 전환
        click_theory_btn(w)
        sc_theory = screenshot(f"{mol_id+1:02d}_{mol_id+1}_s1_theory_{mol_name[:20].replace('/','_')}")
        
        # S2: 전체 드래그 선택
        drag_select_all(w)
        sc_select = screenshot(f"{mol_id+1:02d}_{mol_id+1}_s2_select_{mol_name[:20].replace('/','_')}")
        
        results.append({
            "name": mol_name,
            "desc": desc,
            "s0": sc_draw,
            "s1": sc_theory,
            "s2": sc_select,
        })
    
    return results

def make_html(results):
    rows = ""
    for r in results:
        def img_tag(path):
            if os.path.exists(path):
                return f'<img src="{path}" style="max-width:320px;max-height:240px;border:1px solid #444">'
            return '<span style="color:red">이미지 없음</span>'
        rows += f"""
<tr>
  <td style="padding:8px;font-weight:bold;color:#64B5F6">{r['desc']}<br><small>{r['name']}</small></td>
  <td style="padding:4px">{img_tag(r['s0'])}<br><small>S0 그리기</small></td>
  <td style="padding:4px">{img_tag(r['s1'])}<br><small>S1 이론 구조</small></td>
  <td style="padding:4px">{img_tag(r['s2'])}<br><small>S2 드래그 선택</small></td>
</tr>"""
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>ChemGrid 시각 검증 보고서</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:sans-serif; margin:20px; }}
  h1 {{ color:#64B5F6; }}
  table {{ border-collapse:collapse; width:100%; }}
  th {{ background:#2196F3; color:white; padding:10px; }}
  tr:nth-child(even) {{ background:#1e1e30; }}
  tr:nth-child(odd) {{ background:#16213e; }}
</style>
</head><body>
<h1>🔬 ChemGrid 시각 검증 보고서</h1>
<p>생성 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
<table>
<tr>
  <th>분자</th>
  <th>S0: 그리기</th>
  <th>S1: 이론 구조</th>
  <th>S2: 드래그 선택</th>
</tr>
{rows}
</table>
</body></html>"""
    
    report_path = r"c:\chemgrid\docs\reports\live_visual_report.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n[Report] {report_path}")
    return report_path

if __name__ == "__main__":
    results = run_test()
    if results:
        make_html(results)
        print(f"\n=== 테스트 완료: {len(results)}개 분자 ===")
    else:
        print("[FAIL] 테스트 실패")
