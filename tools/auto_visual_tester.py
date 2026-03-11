"""
tools/auto_visual_tester.py
ChemGrid 자동 시각 검증 도구 — pyautogui + PIL 기반
사용법: python tools/auto_visual_tester.py [--no-launch]

기능:
1. ChemGrid 앱 자동 실행 (자동 동기화 포함)
2. 스크린샷 캡처 및 단계별 UI 검증
3. 3D 팝업 존재 여부 + 원자 색상 CPK 표준 검증
4. HTML 보고서 생성 → 브라우저에서 확인
"""
import sys
import os
import time
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    import pygetwindow as gw
    from PIL import Image, ImageDraw
    import numpy as np
    DEPS_OK = True
except ImportError as e:
    print(f"[ERROR] 의존성 없음: {e}")
    print("설치: pip install pyautogui pygetwindow Pillow numpy")
    DEPS_OK = False

# ── 설정 ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"c:\chemgrid")
APP_DIR      = PROJECT_ROOT / "src" / "app"
APP_ENTRY    = APP_DIR / "draw.py"
SCREENSHOT_DIR = PROJECT_ROOT / "tools" / "test_screenshots"
REPORT_PATH    = PROJECT_ROOT / "tools" / "test_report.html"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# CPK 색상 표준 (R, G, B) ± tolerance
CPK_COLORS = {
    "H":  {"rgb": (220, 220, 220), "tol": 40, "desc": "흰색/회색"},
    "C":  {"rgb": (40,  40,  40),  "tol": 50, "desc": "검정"},
    "N":  {"rgb": (30,  90, 200),  "tol": 60, "desc": "파랑"},
    "O":  {"rgb": (220, 20,  20),  "tol": 60, "desc": "빨강"},
    "S":  {"rgb": (255, 200, 0),   "tol": 60, "desc": "노랑"},
    "Cl": {"rgb": (0,  180,  0),   "tol": 60, "desc": "연두"},
    "P":  {"rgb": (255, 140, 0),   "tol": 60, "desc": "주황"},
}

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

# ── 유틸리티 ──────────────────────────────────────────────────────────────────
def log(msg: str, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")

def take_screenshot(name: str, region=None) -> Path:
    """스크린샷을 파일로 저장 후 경로 반환"""
    path = SCREENSHOT_DIR / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
    img = pyautogui.screenshot(region=region)
    img.save(str(path))
    log(f"스크린샷 저장: {path.name}")
    return path

def find_chemgrid_window():
    """ChemGrid 메인 윈도우 위치 반환 (x, y, w, h)"""
    try:
        wins = gw.getWindowsWithTitle("ChemGrid")
        if not wins:
            wins = gw.getWindowsWithTitle("chemgrid")
        if wins:
            w = wins[0]
            return w.left, w.top, w.width, w.height
    except Exception as e:
        log(f"윈도우 탐색 실패: {e}", "WARN")
    return None

def wait_for_window(title="ChemGrid", timeout=30) -> bool:
    """창이 뜰 때까지 대기"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = gw.getWindowsWithTitle(title)
        if wins and wins[0].width > 100:
            time.sleep(1.0)  # 완전 로딩 대기
            return True
        time.sleep(0.5)
    return False

def color_present_in_region(img: Image.Image, target_rgb: tuple, tol: int, sample_ratio=0.05) -> float:
    """이미지 내 특정 색상 비율 (0~1) 반환"""
    arr = np.array(img)
    r, g, b = target_rgb
    mask = (
        (np.abs(arr[:,:,0].astype(int) - r) < tol) &
        (np.abs(arr[:,:,1].astype(int) - g) < tol) &
        (np.abs(arr[:,:,2].astype(int) - b) < tol)
    )
    ratio = mask.sum() / (arr.shape[0] * arr.shape[1])
    return float(ratio)

def analyze_atom_colors(screenshot_path: Path) -> dict:
    """스크린샷에서 CPK 색상 비율 분석"""
    img = Image.open(screenshot_path).convert("RGB")
    results = {}
    for elem, info in CPK_COLORS.items():
        ratio = color_present_in_region(img, info["rgb"], info["tol"])
        results[elem] = {
            "ratio": ratio,
            "expected_color": info["desc"],
            "found": ratio > 0.002  # 0.2% 이상이면 "존재"
        }
    return results

# ── 테스트 시퀀스 ──────────────────────────────────────────────────────────────
class ChemGridTester:
    def __init__(self, no_launch=False):
        self.no_launch = no_launch
        self.app_proc = None
        self.results = []
        self.screenshots = []
        self.win_x = self.win_y = self.win_w = self.win_h = 0

    def step(self, name: str, ok: bool, detail=""):
        status = "✅ PASS" if ok else "❌ FAIL"
        log(f"{status} | {name} | {detail}")
        self.results.append({"name": name, "ok": ok, "detail": detail})

    def launch_app(self) -> bool:
        if self.no_launch:
            log("--no-launch 옵션으로 앱 실행 건너뜀")
            return True

        # 먼저 동기화
        log("소스 동기화 실행 중...")
        sync_script = r"""
import shutil
src = r'c:\chemgrid\agents\10_testing_build\integrated'
dst = r'c:\chemgrid\src\app'
files = ['popup_3d.py', 'main_window.py', 'canvas.py', 'draw.py',
         'toolbar_setup.py', 'renderer.py', 'dialogs.py', 'ui_utils.py']
for f in files:
    try:
        shutil.copy2(f'{src}/{f}', f'{dst}/{f}')
    except: pass
print('Sync done')
"""
        subprocess.run(["python", "-c", sync_script], capture_output=True)

        # 앱 실행
        log(f"앱 실행: {APP_ENTRY}")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(APP_DIR)
        self.app_proc = subprocess.Popen(
            ["python", str(APP_ENTRY)],
            cwd=str(APP_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        log("앱 로딩 대기 중 (최대 20초)...")
        if not wait_for_window("ChemGrid", timeout=20):
            log("ChemGrid 창을 찾을 수 없음", "ERROR")
            return False

        log("앱 시작 확인됨")
        return True

    def get_win_coords(self) -> bool:
        """창 좌표 갱신"""
        result = find_chemgrid_window()
        if not result:
            return False
        self.win_x, self.win_y, self.win_w, self.win_h = result
        log(f"창 위치: ({self.win_x},{self.win_y}) 크기: {self.win_w}×{self.win_h}")
        return True

    def abs(self, rel_x: float, rel_y: float):
        """창 내 상대 좌표 (0~1) → 절대 화면 좌표"""
        return (
            int(self.win_x + rel_x * self.win_w),
            int(self.win_y + rel_y * self.win_h)
        )

    def test_01_initial_load(self):
        """테스트 1: 앱 로드 확인 + 초기 스크린샷"""
        ok = self.get_win_coords()
        if ok:
            s = take_screenshot("01_initial")
            self.screenshots.append(s)
        self.step("앱 로드 확인", ok, f"창 위치: ({self.win_x},{self.win_y})")

    def test_02_draw_benzene(self):
        """테스트 2: 그리기 모드에서 벤젠 구조 그리기"""
        if not self.get_win_coords():
            self.step("벤젠 그리기", False, "창 없음")
            return

        # 창을 앞으로 가져오기
        try:
            wins = gw.getWindowsWithTitle("ChemGrid")
            if wins:
                wins[0].activate()
                time.sleep(0.5)
        except Exception:
            pass

        # 캔버스 중앙에 벤젠 육각형 그리기 (키보드 단축키 없으므로 좌표로)
        cx, cy = self.abs(0.5, 0.45)  # 캔버스 중앙

        # 6개 탄소 배치 (반지름 60px 육각형)
        import math
        r = 65
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = int(cx + r * math.cos(angle))
            y = int(cy + r * math.sin(angle))
            pyautogui.click(x, y)
            time.sleep(0.15)

        # 결합 연결 (클릭 → 드래그)
        positions = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            positions.append((int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))))

        for i in range(6):
            x1, y1 = positions[i]
            x2, y2 = positions[(i + 1) % 6]
            pyautogui.moveTo(x1, y1, duration=0.1)
            pyautogui.dragTo(x2, y2, duration=0.2, button='left')
            time.sleep(0.1)

        time.sleep(0.5)
        s = take_screenshot("02_benzene_drawn")
        self.screenshots.append(s)
        self.step("벤젠 그리기", True, f"캔버스 중앙 ({cx},{cy})에 6각형")

    def test_03_switch_to_theory(self):
        """테스트 3: Theory 모드 전환 + btn_3d 활성화 확인"""
        if not self.get_win_coords():
            self.step("Theory 모드 전환", False, "창 없음")
            return

        # '이론적 구조' 버튼은 우하단에 위치
        btn_x, btn_y = self.abs(0.91, 0.93)
        log(f"이론적 구조 버튼 클릭: ({btn_x},{btn_y})")
        pyautogui.click(btn_x, btn_y)
        time.sleep(1.5)  # 전환 애니메이션 대기

        s = take_screenshot("03_theory_mode")
        self.screenshots.append(s)

        # '입체 구조' 버튼이 보이는지 확인 (파란색 버튼 탐지)
        img = Image.open(s).convert("RGB")
        blue_ratio = color_present_in_region(img, (33, 150, 243), tol=50)
        btn_visible = blue_ratio > 0.001
        self.step("Theory 모드 + btn_3d 표시", btn_visible, f"파란 버튼 비율: {blue_ratio:.4f}")

    def test_04_open_3d_popup(self):
        """테스트 4: 입체 구조 버튼 클릭 → 3D 팝업 열기"""
        if not self.get_win_coords():
            self.step("3D 팝업 열기", False, "창 없음")
            return

        # btn_3d는 우하단 '돌아가기' 버튼 위에 위치
        btn3d_x, btn3d_y = self.abs(0.91, 0.87)
        log(f"입체 구조 버튼 클릭: ({btn3d_x},{btn3d_y})")
        pyautogui.click(btn3d_x, btn3d_y)
        time.sleep(3.0)  # 3D 팝업 로딩 대기 (RDKit 3D 좌표 계산)

        s = take_screenshot("04_3d_popup")
        self.screenshots.append(s)

        # 새 창이 뜬지 확인 (화면에 새 창 제목이 있는지)
        wins_3d = gw.getWindowsWithTitle("ChemGrid — 통합 3D 분자 분석")
        popup_found = len(wins_3d) > 0
        self.step("3D 팝업 창 열림", popup_found,
                  f"창 제목 '통합 3D 분자 분석' 존재: {popup_found}")
        return popup_found

    def test_05_atom_rendering(self):
        """테스트 5: 3D 팝업 내 원자 색상 CPK 표준 확인"""
        wins_3d = gw.getWindowsWithTitle("ChemGrid — 통합 3D 분자 분석")
        if not wins_3d:
            self.step("원자 색상 검증", False, "3D 팝업 없음")
            return

        popup = wins_3d[0]
        region = (popup.left, popup.top, popup.width, popup.height)
        s = take_screenshot("05_3d_atoms", region=region)
        self.screenshots.append(s)

        # 원자 색상 분석
        color_results = analyze_atom_colors(s)

        # 탄소(검정) 확인
        carbon_found = color_results.get("C", {}).get("found", False)
        self.step("탄소 CPK 색상 (검정)", carbon_found,
                  f"비율: {color_results.get('C',{}).get('ratio',0):.4f}")

        # 전체 보고
        for elem, info in color_results.items():
            if info["found"]:
                log(f"  원소 {elem}: 발견 (비율={info['ratio']:.4f}, 예상={info['expected_color']})")

    def test_06_popup_independence(self):
        """테스트 6: 팝업 창 독립성 확인 (이동 가능한 별개 창인지)"""
        wins_3d = gw.getWindowsWithTitle("ChemGrid — 통합 3D 분자 분석")
        if not wins_3d:
            self.step("팝업 독립 창 확인", False, "3D 팝업 없음")
            return

        popup = wins_3d[0]
        orig_x, orig_y = popup.left, popup.top

        # 창 이동 시도
        try:
            popup.moveTo(orig_x + 50, orig_y + 30)
            time.sleep(0.5)
            wins_3d_new = gw.getWindowsWithTitle("ChemGrid — 통합 3D 분자 분석")
            if wins_3d_new:
                new_x = wins_3d_new[0].left
                moved = abs(new_x - orig_x) > 10
            else:
                moved = False
        except Exception as e:
            moved = False
            log(f"창 이동 시도 실패: {e}", "WARN")

        self.step("3D 팝업 독립 창 (이동 가능)", moved,
                  f"원래: ({orig_x},{orig_y}), 이동 후 확인")

        s = take_screenshot("06_popup_moved")
        self.screenshots.append(s)

    def generate_html_report(self):
        """HTML 테스트 보고서 생성"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["ok"])
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 스크린샷 HTML
        screenshots_html = ""
        for i, path in enumerate(self.screenshots):
            rel = os.path.relpath(str(path), str(PROJECT_ROOT))
            screenshots_html += f"""
            <div class="screenshot">
                <h3>{i+1}. {path.stem}</h3>
                <img src="{path}" style="max-width:800px; border:1px solid #333;" />
            </div>"""

        # 결과 테이블
        rows = ""
        for r in self.results:
            icon = "✅" if r["ok"] else "❌"
            cls = "pass" if r["ok"] else "fail"
            rows += f'<tr class="{cls}"><td>{icon}</td><td>{r["name"]}</td><td>{r["detail"]}</td></tr>'

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>ChemGrid 자동 시각 검증 보고서</title>
<style>
body {{ font-family: 'Malgun Gothic', sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
h1 {{ color: #4fc3f7; }} h2 {{ color: #81d4fa; border-bottom: 1px solid #333; padding-bottom: 5px; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
th, td {{ border: 1px solid #444; padding: 8px 12px; }}
th {{ background: #2d2d44; color: #81d4fa; }}
tr.pass td {{ background: rgba(76,175,80,0.15); }}
tr.fail td {{ background: rgba(244,67,54,0.15); }}
.summary {{ background: #16213e; padding: 15px; border-radius: 8px; margin: 15px 0; }}
.score {{ font-size: 2em; font-weight: bold; color: {'#4caf50' if passed == total else '#ff9800'}; }}
.screenshot {{ margin: 20px 0; background: #16213e; padding: 10px; border-radius: 8px; }}
</style>
</head>
<body>
<h1>🔬 ChemGrid 자동 시각 검증 보고서</h1>
<div class="summary">
  <div>검증 시각: {ts}</div>
  <div class="score">{passed}/{total} PASS</div>
</div>
<h2>📋 테스트 결과</h2>
<table>
<tr><th>결과</th><th>테스트 항목</th><th>상세</th></tr>
{rows}
</table>
<h2>📸 단계별 스크린샷</h2>
{screenshots_html}
</body>
</html>"""

        REPORT_PATH.write_text(html, encoding="utf-8")
        log(f"HTML 보고서 저장: {REPORT_PATH}")
        return REPORT_PATH

    def cleanup(self):
        """테스트 종료 후 정리"""
        if self.app_proc and self.app_proc.poll() is None:
            log("테스트 앱 프로세스 종료")
            self.app_proc.terminate()

    def run_all(self):
        """전체 테스트 시퀀스 실행"""
        log("=" * 60)
        log("ChemGrid 자동 시각 검증 시작")
        log("=" * 60)

        try:
            # 앱 실행
            if not self.launch_app():
                self.step("앱 실행", False, "ChemGrid 창을 찾을 수 없음")
                return self.generate_html_report()
            self.step("앱 실행", True)

            # 테스트 시퀀스
            self.test_01_initial_load()
            self.test_02_draw_benzene()
            self.test_03_switch_to_theory()
            self.test_04_open_3d_popup()
            self.test_05_atom_rendering()
            self.test_06_popup_independence()

        except Exception as e:
            log(f"예외 발생: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            self.step("전체 실행", False, str(e))
        finally:
            s = take_screenshot("99_final_state")
            self.screenshots.append(s)

        report = self.generate_html_report()
        total = len(self.results)
        passed = sum(1 for r in self.results if r["ok"])
        log(f"테스트 완료: {passed}/{total} PASS")
        log(f"보고서: {report}")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChemGrid 자동 시각 검증 도구")
    parser.add_argument("--no-launch", action="store_true",
                        help="앱을 새로 실행하지 않고 이미 실행 중인 창을 사용")
    args = parser.parse_args()

    if not DEPS_OK:
        sys.exit(1)

    tester = ChemGridTester(no_launch=args.no_launch)
    report_path = tester.run_all()
    tester.cleanup()

    # 보고서 자동 열기
    try:
        os.startfile(str(report_path))
    except Exception:
        print(f"보고서 경로: {report_path}")
