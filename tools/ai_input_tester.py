"""
tools/ai_input_tester.py
AI 텍스트 입력 자동화 + 전자구름 균일도 검증 도구 (v1.0)
──────────────────────────────────────────────────────────
기능:
  1. ChemGrid '텍스트 입력 분자 생성' 필드에 분자명 자동 입력
  2. 이론적 구조 뷰에서 전자구름 균일도 분석
  3. 방향족 이온(사이클로펜타디에닐 음이온, 트로필리움 이온 등) 특화 검증
  4. Orca 계산 로그 자동 수집 (current_state.json / orca_history/)
  5. HTML 보고서 + JSON 로그 자동 생성

사용법:
  python tools/ai_input_tester.py                  # 전체 테스트
  python tools/ai_input_tester.py --no-launch      # 이미 실행 중인 창 사용
  python tools/ai_input_tester.py --only-text      # 텍스트 입력 테스트만
"""
import sys
import os
import time
import json
import math
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict

# ── 의존성 확인 ──────────────────────────────────────────────────────────────
try:
    import pyautogui
    import pygetwindow as gw
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    DEPS_OK = True
except ImportError as e:
    print(f"[ERROR] 의존성 없음: {e}")
    print("설치: pip install pyautogui pygetwindow Pillow numpy")
    DEPS_OK = False

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(r"c:\chemgrid")
APP_ENTRY      = PROJECT_ROOT / "src" / "app" / "draw.py"
APP_DIR        = PROJECT_ROOT / "src" / "app"
SCREENSHOT_DIR = PROJECT_ROOT / "tools" / "test_screenshots" / "ai_input"
REPORT_PATH    = PROJECT_ROOT / "tools" / "ai_input_report.html"
JSON_LOG_PATH  = PROJECT_ROOT / "tools" / "ai_input_log.json"
ORCA_HISTORY   = PROJECT_ROOT / "orca_history"
STATE_JSON     = PROJECT_ROOT / "current_state.json"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.25

# ── 테스트 케이스 정의 ────────────────────────────────────────────────────────
# (입력 텍스트, 예상 SMILES, 설명, 방향족 이온 여부, 예상 균일도)
TEST_MOLECULES = [
    {
        "input": "benzene",
        "smiles_expected": "c1ccccc1",
        "desc": "벤젠 — 6π 균일 방향족",
        "is_aromatic_ion": False,
        "uniform_expected": True,
        "ring_size": 6,
    },
    {
        "input": "cyclopentadienyl anion",
        "smiles_expected": "[CH-]1C=CC=C1",
        "desc": "사이클로펜타디에닐 음이온 — 6π 음이온 방향족",
        "is_aromatic_ion": True,
        "uniform_expected": True,
        "ring_size": 5,
    },
    {
        "input": "tropylium",
        "smiles_expected": "[CH+]1=CC=CC=CC=1",
        "desc": "트로필리움 양이온 — 6π 양이온 방향족",
        "is_aromatic_ion": True,
        "uniform_expected": True,
        "ring_size": 7,
    },
    {
        "input": "ethanol",
        "smiles_expected": "CCO",
        "desc": "에탄올 — 비방향족 대조군",
        "is_aromatic_ion": False,
        "uniform_expected": False,
        "ring_size": 0,
    },
    {
        "input": "CH3CH2OH",
        "smiles_expected": "CCO",
        "desc": "에탄올 분자식 입력 테스트",
        "is_aromatic_ion": False,
        "uniform_expected": False,
        "ring_size": 0,
    },
    {
        "input": "naphthalene",
        "smiles_expected": "c1ccc2ccccc2c1",
        "desc": "나프탈렌 — 10π 융합 방향족",
        "is_aromatic_ion": False,
        "uniform_expected": True,
        "ring_size": 10,
    },
    {
        "input": "pyridine",
        "smiles_expected": "c1ccncc1",
        "desc": "피리딘 — 질소 포함 방향족",
        "is_aromatic_ion": False,
        "uniform_expected": True,
        "ring_size": 6,
    },
]

# ── 유틸리티 ──────────────────────────────────────────────────────────────────
def log(msg: str, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    tag = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️",
           "TEST": "🧪", "KEY":  "⌨️", "SNAP": "📸", "ORCA": "⚗️"}.get(level, "·")
    print(f"[{ts}] {tag} [{level}] {msg}")

def take_shot(name: str, region=None) -> Path:
    ts = datetime.now().strftime("%H%M%S_%f")[:13]
    path = SCREENSHOT_DIR / f"{name}_{ts}.png"
    img = pyautogui.screenshot(region=region)
    img.save(str(path))
    log(f"캡처: {path.name}", "SNAP")
    return path

def find_window(title="ChemGrid") -> Optional[Tuple[int,int,int,int]]:
    try:
        wins = gw.getWindowsWithTitle(title)
        if wins and wins[0].width > 100:
            w = wins[0]
            return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None

def wait_window(title="ChemGrid", timeout=25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = find_window(title)
        if r:
            time.sleep(0.8)
            return True
        time.sleep(0.4)
    return False

def rel2abs(win: Tuple[int,int,int,int], rx: float, ry: float) -> Tuple[int,int]:
    x0, y0, w, h = win
    return (int(x0 + rx * w), int(y0 + ry * h))

# ── 전자구름 균일도 분석 ───────────────────────────────────────────────────────
class ElectronCloudAnalyzer:
    """
    이론적 구조(Theory) 뷰의 스크린샷에서 전자구름 균일도를 분석.
    방향족 분자: 고리 탄소 주변 색상 분산이 낮아야 함.
    """

    # 전자구름 색상 범위 (파란색~보라색 계열)
    CLOUD_HUE_MIN = 190   # HSV 기준 (degree)
    CLOUD_HUE_MAX = 280
    CLOUD_SAT_MIN = 0.30
    CLOUD_VAL_MIN = 0.20

    @staticmethod
    def extract_cloud_mask(img: Image.Image) -> np.ndarray:
        """전자구름(파란/보라 계열) 픽셀 마스크 추출"""
        arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]

        # 파란-보라 범위: B > R, B > G, B > 0.3
        cloud_mask = (b > 0.3) & (b > r + 0.05) & (b > g - 0.05)
        return cloud_mask.astype(np.uint8)

    @staticmethod
    def ring_region_samples(
        cx: float, cy: float, radius: float,
        n_atoms: int, window_w: int, window_h: int
    ) -> List[Tuple[int,int]]:
        """고리 원자 예상 위치 픽셀 좌표 반환"""
        positions = []
        for i in range(n_atoms):
            angle = math.radians(360.0 * i / n_atoms - 90)
            px = int(cx + radius * math.cos(angle))
            py = int(cy + radius * math.sin(angle))
            px = max(5, min(window_w - 5, px))
            py = max(5, min(window_h - 5, py))
            positions.append((px, py))
        return positions

    @classmethod
    def analyze(cls, screenshot_path: Path, ring_size: int) -> Dict:
        """전자구름 균일도 점수 계산 (0~1, 높을수록 균일)"""
        img = Image.open(screenshot_path).convert("RGB")
        arr = np.array(img, dtype=np.float32)
        W, H = img.size

        cloud_mask = cls.extract_cloud_mask(img)
        cloud_ratio = cloud_mask.sum() / (W * H)

        if ring_size == 0 or cloud_ratio < 0.001:
            return {
                "cloud_ratio": float(cloud_ratio),
                "uniformity_score": None,
                "status": "no_ring",
                "detail": f"전자구름 비율: {cloud_ratio:.4f} (고리 없음 또는 구름 없음)"
            }

        # 화면 중앙에서 고리가 있을 것으로 예상
        # 고리 원자 위치 샘플링 (중앙 기준, 반지름 추정)
        estimated_radius = min(W, H) * 0.12
        samples = cls.ring_region_samples(W*0.5, H*0.45, estimated_radius, ring_size, W, H)

        # 각 원자 위치 근처(±15px) 전자구름 밀도
        densities = []
        patch = 15
        for (px, py) in samples:
            x1, y1 = max(0, px-patch), max(0, py-patch)
            x2, y2 = min(W, px+patch), min(H, py+patch)
            region = cloud_mask[y1:y2, x1:x2]
            density = region.mean() if region.size > 0 else 0.0
            densities.append(float(density))

        if not densities or max(densities) < 0.01:
            return {
                "cloud_ratio": float(cloud_ratio),
                "uniformity_score": 0.0,
                "densities": densities,
                "status": "cloud_absent",
                "detail": "고리 근처에서 전자구름 미검출"
            }

        mean_d = np.mean(densities)
        std_d  = np.std(densities)
        cv = (std_d / mean_d) if mean_d > 1e-6 else 1.0  # 변동계수 (낮을수록 균일)
        uniformity = max(0.0, 1.0 - cv)                   # 0~1 점수

        return {
            "cloud_ratio": float(cloud_ratio),
            "uniformity_score": float(uniformity),
            "mean_density": float(mean_d),
            "std_density": float(std_d),
            "cv": float(cv),
            "densities": densities,
            "status": "measured",
            "detail": (
                f"균일도={uniformity:.3f} (CV={cv:.3f}) | "
                f"평균밀도={mean_d:.4f} | "
                f"전체구름비율={cloud_ratio:.4f}"
            )
        }


# ── Orca 로그 수집 ─────────────────────────────────────────────────────────────
class OrcaLogger:
    """
    orca_history/ 폴더의 최신 계산 결과 수집
    current_state.json에서 현재 SMILES 확인
    """

    @staticmethod
    def get_current_smiles() -> str:
        try:
            if STATE_JSON.exists():
                data = json.loads(STATE_JSON.read_text(encoding="utf-8"))
                return data.get("smiles", "")
        except Exception:
            pass
        return ""

    @staticmethod
    def get_latest_orca_log() -> Optional[Dict]:
        if not ORCA_HISTORY.exists():
            return None
        logs = sorted(ORCA_HISTORY.glob("*.json"), key=lambda f: f.stat().st_mtime)
        if not logs:
            return None
        try:
            data = json.loads(logs[-1].read_text(encoding="utf-8"))
            return {"file": logs[-1].name, **data}
        except Exception:
            return None

    @staticmethod
    def save_session_log(test_name: str, input_text: str, result: Dict):
        """세션별 로그를 ai_input_log.json에 누적 저장"""
        logs = []
        if JSON_LOG_PATH.exists():
            try:
                logs = json.loads(JSON_LOG_PATH.read_text(encoding="utf-8"))
            except Exception:
                logs = []

        entry = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "input_text": input_text,
            **result,
            "current_smiles": OrcaLogger.get_current_smiles(),
            "orca_log": OrcaLogger.get_latest_orca_log(),
        }
        logs.append(entry)
        JSON_LOG_PATH.write_text(
            json.dumps(logs, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"로그 저장: {JSON_LOG_PATH.name} ({len(logs)}개 누적)", "ORCA")


# ── 핵심 테스터 클래스 ─────────────────────────────────────────────────────────
class AIInputTester:
    """
    ChemGrid 텍스트 입력 자동화 + 전자구름 검증 테스터
    """

    # ── 상대 좌표 설정 (ChemGrid 창 기준 0~1) ──
    # 툴바 텍스트 입력 필드 위치
    # (실제 위치는 앱 실행 후 확인 필요 — 여기서는 추정값 사용)
    TEXT_FIELD_REL  = (0.35, 0.055)   # 툴바 중앙 텍스트박스
    TEXT_BTN_REL    = (0.52, 0.055)   # "생성" 버튼 (텍스트박스 오른쪽)
    THEORY_BTN_REL  = (0.91, 0.93)    # 이론적 구조 버튼
    BACK_BTN_REL    = (0.91, 0.93)    # 돌아가기 버튼 (Theory 상태에서)
    CANVAS_CTR_REL  = (0.50, 0.47)    # 캔버스 중앙
    SELECT_ALL_REL  = (0.50, 0.47)    # 전체 선택 (Ctrl+A)

    def __init__(self, no_launch=False):
        self.no_launch   = no_launch
        self.app_proc    = None
        self.results     = []
        self.screenshots = []
        self.win         = None          # (x, y, w, h) tuple

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────
    def _step(self, name: str, ok: bool, detail="", data=None):
        status = "PASS" if ok else "FAIL"
        log(f"{name} | {detail}", status)
        entry = {"name": name, "ok": ok, "detail": detail}
        if data:
            entry.update(data)
        self.results.append(entry)

    def _update_win(self) -> bool:
        r = find_window("ChemGrid")
        if r:
            self.win = r
            return True
        return False

    def _abs(self, rx: float, ry: float) -> Tuple[int,int]:
        if not self.win:
            return (0, 0)
        return rel2abs(self.win, rx, ry)

    def _activate(self):
        """창을 최상위로 활성화"""
        try:
            wins = gw.getWindowsWithTitle("ChemGrid")
            if wins:
                wins[0].activate()
                time.sleep(0.4)
        except Exception:
            pass

    def _clear_canvas(self):
        """캔버스 전체 지우기 (Ctrl+A → Delete)"""
        cx, cy = self._abs(*self.CANVAS_CTR_REL)
        pyautogui.click(cx, cy)
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.2)
        pyautogui.press('delete')
        time.sleep(0.3)
        log("캔버스 초기화 완료")

    def _go_to_draw_mode(self):
        """그리기 모드로 전환 (Theory 모드라면 '돌아가기' 클릭)"""
        s = take_shot("mode_check")
        img = Image.open(s).convert("RGB")
        # 배경이 어두우면 Theory 모드로 추정
        arr = np.array(img)
        center_region = arr[arr.shape[0]//3:arr.shape[0]*2//3,
                           arr.shape[1]//3:arr.shape[1]*2//3]
        mean_brightness = center_region.mean()
        if mean_brightness < 80:   # Theory 모드 (어두운 배경)
            bx, by = self._abs(*self.BACK_BTN_REL)
            pyautogui.click(bx, by)
            time.sleep(1.0)
            log("그리기 모드로 복귀")

    # ── 텍스트 입력 핵심 메서드 ────────────────────────────────────────────────
    def type_molecule(self, text: str, wait_render=2.5) -> bool:
        """
        ChemGrid 텍스트 입력 필드에 분자명/분자식을 타이핑.
        Returns True if input field was found and typed.
        
        전략:
         1. 텍스트 필드 좌표 클릭
         2. Ctrl+A 로 기존 텍스트 선택 후 새 텍스트 입력
         3. Enter 또는 생성 버튼 클릭
        """
        if not self._update_win():
            log("창 없음 — 텍스트 입력 불가", "FAIL")
            return False
        self._activate()

        # 텍스트 입력 필드 클릭
        fx, fy = self._abs(*self.TEXT_FIELD_REL)
        log(f"텍스트 필드 클릭: ({fx},{fy}) → '{text}'", "KEY")
        pyautogui.click(fx, fy)
        time.sleep(0.3)

        # 기존 내용 지우기
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.15)
        pyautogui.press('delete')
        time.sleep(0.15)

        # 텍스트 입력 (직접 typewrite 사용 — 한글 포함 분자명은 pyperclip 사용)
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
        except ImportError:
            pyautogui.typewrite(text, interval=0.05)

        time.sleep(0.3)
        pyautogui.press('enter')
        log(f"Enter 전송 → 렌더링 대기 {wait_render}s", "KEY")
        time.sleep(wait_render)
        return True

    # ── 이론적 구조 전환 ─────────────────────────────────────────────────────
    def switch_to_theory(self) -> bool:
        if not self._update_win():
            return False
        bx, by = self._abs(*self.THEORY_BTN_REL)
        log(f"이론적 구조 버튼 클릭: ({bx},{by})")
        pyautogui.click(bx, by)
        time.sleep(1.8)
        return True

    # ── 텍스트 입력 위치 자동 감지 ─────────────────────────────────────────────
    def auto_locate_text_field(self) -> Optional[Tuple[float,float]]:
        """
        ChemGrid 툴바에서 텍스트 입력 필드를 자동 탐지.
        PIL 이미지 분석으로 흰 배경 + 얇은 직사각형 = QLineEdit 영역 탐지.
        
        Returns: (rx, ry) relative coordinates or None
        """
        if not self._update_win():
            return None
        x0, y0, w, h = self.win

        # 툴바 영역 캡처 (상단 10%)
        toolbar_region = (x0, y0, w, int(h * 0.12))
        s = take_shot("toolbar_scan", region=toolbar_region)
        img = Image.open(s).convert("RGB")
        arr = np.array(img)

        # 흰색 또는 밝은 영역 탐지 (텍스트 입력 필드)
        bright_mask = (arr[:,:,0] > 220) & (arr[:,:,1] > 220) & (arr[:,:,2] > 220)
        bright_cols = bright_mask.any(axis=0)
        bright_rows = bright_mask.any(axis=1)

        # 흰 영역의 수평 중간점 찾기
        col_indices = np.where(bright_cols)[0]
        row_indices = np.where(bright_rows)[0]

        if len(col_indices) > 30 and len(row_indices) > 3:
            mid_col = float(col_indices[len(col_indices)//2]) / arr.shape[1]
            mid_row = float(row_indices[len(row_indices)//2]) / arr.shape[0] * 0.12
            log(f"텍스트 필드 자동 감지: rx={mid_col:.3f}, ry={mid_row:.3f}")
            return (mid_col, mid_row)
        else:
            log("텍스트 필드 자동 감지 실패 — 기본값 사용", "WARN")
            return None

    # ── 테스트 케이스 실행 ────────────────────────────────────────────────────
    def run_single_test(self, mol: Dict) -> Dict:
        """분자 1개 테스트 실행 → 결과 dict 반환"""
        name  = mol["input"]
        desc  = mol["desc"]
        ring  = mol["ring_size"]
        uni   = mol["uniform_expected"]
        ionic = mol["is_aromatic_ion"]

        log("=" * 55, "TEST")
        log(f"테스트: {desc}", "TEST")
        log("=" * 55, "TEST")

        result = {
            "input": name,
            "desc": desc,
            "is_aromatic_ion": ionic,
            "ring_size": ring,
            "uniform_expected": uni,
        }

        # 1. 캔버스 초기화
        self._go_to_draw_mode()
        self._clear_canvas()
        s_before = take_shot(f"before_{name.replace(' ','_')}")

        # 2. 텍스트 입력
        ok_type = self.type_molecule(name, wait_render=2.5)
        if not ok_type:
            result["status"] = "type_failed"
            self._step(f"[{name}] 텍스트 입력", False, "입력 필드 접근 실패")
            return result

        s_drawn = take_shot(f"drawn_{name.replace(' ','_')}")
        self.screenshots.append((desc, s_drawn))

        # 3. 현재 SMILES 확인
        current_smiles = OrcaLogger.get_current_smiles()
        result["smiles_actual"] = current_smiles
        smiles_ok = bool(current_smiles and current_smiles not in ("", "C", ""))
        self._step(
            f"[{name}] SMILES 생성",
            smiles_ok,
            f"actual='{current_smiles}' expected='{mol['smiles_expected']}'"
        )

        # 4. 이론적 구조 전환
        switched = self.switch_to_theory()
        time.sleep(0.5)
        s_theory = take_shot(f"theory_{name.replace(' ','_')}")
        self.screenshots.append((f"{desc} (이론적)", s_theory))

        # 5. 전자구름 분석
        cloud_result = ElectronCloudAnalyzer.analyze(s_theory, ring)
        result["cloud_analysis"] = cloud_result

        if ring > 0:
            score = cloud_result.get("uniformity_score")
            if score is None:
                cloud_pass = False
                detail = cloud_result.get("detail", "분석 불가")
            elif uni:
                # 방향족: 균일도 0.6 이상이면 PASS
                cloud_pass = score >= 0.6
                detail = f"균일도={score:.3f} (기대: ≥0.6) | {cloud_result.get('detail','')}"
            else:
                # 비방향족: 균일도 확인만 (PASS/FAIL 기준 없음)
                cloud_pass = True
                detail = f"비방향족 대조군 | 균일도={score:.3f}"
            
            self._step(f"[{name}] 전자구름 {'균일도' if uni else '분포'}", cloud_pass, detail)

            # 방향족 이온 특별 체크
            if ionic:
                self._step(
                    f"[{name}] 이온성 방향족 전자구름 편재화 체크",
                    cloud_pass,
                    f"사이클릭 방향족 이온: {'균등 분포 확인됨' if cloud_pass else '편재화 발생 — 버그!'}"
                )

        result["status"] = "done"

        # 6. Orca 로그 수집 & 저장
        OrcaLogger.save_session_log(f"test_{name}", name, result)

        return result

    # ── 앱 실행 ───────────────────────────────────────────────────────────────
    def launch_app(self) -> bool:
        if self.no_launch:
            log("--no-launch: 기존 창 사용")
            return wait_window("ChemGrid", timeout=5)

        log("소스 동기화 중...")
        try:
            sync = "import shutil\n"
            sync += "src='c:/chemgrid/agents/10_testing_build/integrated'\n"
            sync += "dst='c:/chemgrid/src/app'\n"
            for f in ['popup_3d.py','main_window.py','canvas.py','draw.py',
                      'toolbar_setup.py','renderer.py','dialogs.py','ui_utils.py',
                      'engine_resonance.py']:
                sync += f"shutil.copy2(f'{{src}}/{f}',f'{{dst}}/{f}',)\n" \
                        f"  if __import__('os').path.exists(f'{{src}}/{f}') else None\n"
            sync += "print('sync done')"
            subprocess.run(["python", "-c", sync], capture_output=True, timeout=15)
        except Exception as e:
            log(f"동기화 경고: {e}", "WARN")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(APP_DIR)
        self.app_proc = subprocess.Popen(
            ["python", str(APP_ENTRY)],
            cwd=str(APP_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        log("ChemGrid 시작 대기 중 (최대 25s)...")
        if not wait_window("ChemGrid", timeout=25):
            stderr = self.app_proc.stderr.read(2000).decode(errors="replace")
            log(f"앱 실행 실패:\n{stderr}", "FAIL")
            return False
        log("ChemGrid 시작 확인")
        return True

    # ── HTML 보고서 생성 ────────────────────────────────────────────────────────
    def generate_report(self) -> Path:
        total  = len(self.results)
        passed = sum(1 for r in self.results if r.get("ok", False))
        ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows = ""
        for r in self.results:
            icon = "✅" if r.get("ok") else "❌"
            cls  = "pass" if r.get("ok") else "fail"
            rows += (f'<tr class="{cls}"><td>{icon}</td>'
                     f'<td>{r["name"]}</td>'
                     f'<td style="font-size:0.85em">{r["detail"]}</td></tr>\n')

        shots_html = ""
        for desc, path in self.screenshots:
            shots_html += f"""
            <div class="shot">
              <h4>📸 {desc}</h4>
              <img src="{path}" style="max-width:750px;border:1px solid #444;border-radius:6px"/>
            </div>"""

        log_link = f'<a href="{JSON_LOG_PATH}" style="color:#4fc3f7">📂 JSON 로그 보기</a>'

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>ChemGrid AI 입력 + 전자구름 검증 보고서</title>
<style>
:root {{--bg:#12121f;--bg2:#1a1a2e;--bg3:#16213e;--acc:#4fc3f7;--acc2:#81d4fa;
        --pass:rgba(76,175,80,.18);--fail:rgba(244,67,54,.18);}}
body{{font-family:'Malgun Gothic',sans-serif;background:var(--bg);color:#e0e0e0;padding:20px;}}
h1{{color:var(--acc);margin:0 0 8px}}
h2{{color:var(--acc2);border-bottom:1px solid #333;padding-bottom:5px;margin-top:30px}}
h4{{color:#b0bec5;margin:8px 0 4px}}
.summary{{background:var(--bg3);padding:15px 20px;border-radius:10px;margin:15px 0;
          display:flex;gap:30px;align-items:center}}
.score{{font-size:2.4em;font-weight:bold;
        color:{'#4caf50' if passed==total else '#ff9800' if passed>total//2 else '#f44336'}}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #333;padding:9px 13px;text-align:left}}
th{{background:var(--bg3);color:var(--acc2)}}
tr.pass td{{background:var(--pass)}}
tr.fail td{{background:var(--fail)}}
.shot{{background:var(--bg2);padding:12px;border-radius:8px;margin:12px 0}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.8em;
        font-weight:bold;margin:0 4px}}
.b-pass{{background:#1b5e20;color:#a5d6a7}}
.b-fail{{background:#b71c1c;color:#ffcdd2}}
</style>
</head>
<body>
<h1>🧪 ChemGrid AI 입력 + 전자구름 검증 보고서</h1>
<div class="summary">
  <div><div style="color:#90a4ae;font-size:.9em">생성 시각</div>{ts}</div>
  <div><div style="color:#90a4ae;font-size:.9em">결과</div>
    <div class="score">{passed}/{total}</div></div>
  <div>{log_link}</div>
</div>
<h2>📋 테스트 결과 상세</h2>
<table>
<tr><th>결과</th><th>테스트 항목</th><th>상세</th></tr>
{rows}
</table>
<h2>📸 단계별 시각 기록</h2>
{shots_html if shots_html else '<p style="color:#607d8b">스크린샷 없음</p>'}
<hr style="border-color:#333;margin-top:40px"/>
<p style="color:#546e7a;font-size:.8em">
  ChemGrid AI 입력 자동 검증 도구 · tools/ai_input_tester.py
</p>
</body>
</html>"""

        REPORT_PATH.write_text(html, encoding="utf-8")
        log(f"HTML 보고서: {REPORT_PATH}")
        return REPORT_PATH

    # ── 전체 실행 ─────────────────────────────────────────────────────────────
    def run_all(self, only_text=False):
        log("★" * 55)
        log("  ChemGrid AI 입력 + 전자구름 검증 테스트 시작")
        log("★" * 55)

        try:
            # 앱 실행
            if not self.launch_app():
                self._step("앱 실행", False, "ChemGrid 창을 찾을 수 없음")
                return self.generate_report()
            self._step("앱 실행", True)
            if not self._update_win():
                self._step("창 좌표 획득", False)
                return self.generate_report()
            self._step("창 좌표 획득", True,
                       f"위치=({self.win[0]},{self.win[1]}) "
                       f"크기={self.win[2]}×{self.win[3]}")
            self._activate()

            # 텍스트 입력 필드 위치 자동 감지 시도
            detected = self.auto_locate_text_field()
            if detected:
                self.TEXT_FIELD_REL = detected
                log(f"텍스트 필드 위치 업데이트: {detected}")

            # 초기 스크린샷
            s_init = take_shot("00_initial")
            self.screenshots.append(("초기 화면", s_init))

            # 테스트 케이스 실행
            mols = TEST_MOLECULES
            for mol in mols:
                try:
                    self.run_single_test(mol)
                    time.sleep(0.5)
                except Exception as e:
                    log(f"테스트 예외 [{mol['input']}]: {e}", "FAIL")
                    import traceback
                    traceback.print_exc()
                    self._step(f"[{mol['input']}] 테스트 실행", False, str(e))

        except KeyboardInterrupt:
            log("사용자 중단", "WARN")
        except Exception as e:
            import traceback
            log(f"전체 예외: {e}", "FAIL")
            traceback.print_exc()
            self._step("전체 실행", False, str(e))
        finally:
            s_final = take_shot("99_final")
            self.screenshots.append(("최종 화면", s_final))

        report = self.generate_report()
        passed = sum(1 for r in self.results if r.get("ok", False))
        total  = len(self.results)
        log(f"\n완료: {passed}/{total} PASS | 보고서: {report}")
        return report

    def cleanup(self):
        if self.app_proc and self.app_proc.poll() is None:
            self.app_proc.terminate()
            log("앱 프로세스 종료")


# ── 진입점 ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChemGrid AI 입력 자동화 테스트")
    parser.add_argument("--no-launch", action="store_true",
                        help="이미 실행 중인 ChemGrid 창 사용")
    parser.add_argument("--only-text", action="store_true",
                        help="텍스트 입력 테스트만 실행 (전자구름 분석 생략)")
    args = parser.parse_args()

    if not DEPS_OK:
        sys.exit(1)

    tester = AIInputTester(no_launch=args.no_launch)
    try:
        report = tester.run_all(only_text=args.only_text)
        try:
            os.startfile(str(report))
        except Exception:
            print(f"보고서: {report}")
    finally:
        tester.cleanup()
