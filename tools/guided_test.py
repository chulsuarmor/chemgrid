"""
guided_test.py — ChemGrid 안내형 반자동 테스터 v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[동작 방식]
 1. ChemGrid를 subprocess로 실행 (stdout 파이프 연결)
 2. 백그라운드 스레드가 앱 출력을 실시간으로 큐에 적재
 3. 각 단계마다:
    - 터미널에 "지금 XXX 해주세요" 안내 출력
    - 앱 로그에서 키워드 감지 or 타임아웃 대기
    - 스크린샷 캡처
    - 자동으로 다음 단계 진행

[실행 방법]
 conda activate chemgrid
 python c:\\chemgrid\\tools\\guided_test.py
"""
import subprocess
import threading
import time
import queue
import sys
import shutil
from pathlib import Path
from datetime import datetime

# ── pygetwindow / pyautogui (선택 사항) ─────────────────────────
try:
    import pygetwindow as gw
    import pyautogui
    pyautogui.FAILSAFE = False
    SCREEN_OK = True
except ImportError:
    SCREEN_OK = False
    print("[경고] pygetwindow/pyautogui 미설치 — 창 감지/스크린샷 없이 진행")
    print("       설치: pip install pygetwindow pyautogui\n")

# ── 로그 파일 설정 ──────────────────────────────────────────────
import io
_SESSION_START = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_DIR = Path(r"c:\chemgrid\tools\test_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = LOG_DIR / f"session_{_SESSION_START}.log"
_log_file = open(_LOG_PATH, 'w', encoding='utf-8', buffering=1)

def _tee(msg: str):
    """터미널 + 로그 파일 동시 출력"""
    print(msg)
    _log_file.write(msg + '\n')
    _log_file.flush()

# ══════════════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════════════
PYTHON_EXE  = r"C:\ProgramData\anaconda3\envs\chemgrid\python.exe"
APP_DIR     = r"c:\chemgrid\src\app"
AGENTS_DIR  = r"c:\chemgrid\agents\10_testing_build\integrated"
SHOT_DIR    = Path(r"c:\chemgrid\tools\test_screenshots")
SHOT_DIR.mkdir(parents=True, exist_ok=True)

# 동기화할 파일 목록
SYNC_FILES = [
    'popup_3d.py', 'main_window.py', 'canvas.py', 'draw.py',
    'toolbar_setup.py', 'renderer.py', 'dialogs.py', 'ui_utils.py',
    'engine_core.py', 'engine_resonance.py', 'engine_physics.py',
    'analyzer.py', 'iupac_analyzer.py', 'layer_logic.py',
    'chem_data.py', 'coord_utils.py',
]

# ══════════════════════════════════════════════════════
#  유틸리티 함수
# ══════════════════════════════════════════════════════
_proc = None
_log_queue = queue.Queue()

def banner(step: int, title: str):
    """단계 헤더 출력"""
    line = "═" * 70
    _tee(f"\n{line}")
    _tee(f"  STEP {step}: {title}")
    _tee(f"{line}")

def guide(msg: str):
    """사용자에게 해야 할 행동을 안내 (굵은 화살표)"""
    _tee("")
    for line in msg.strip().split('\n'):
        _tee(f"  👉  {line.strip()}")
    _tee("")

def ok(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    _tee(f"  ✅  [{ts}] {msg}")

def warn(msg: str):
    _tee(f"  ⚠️   {msg}")

def note(msg: str):
    _tee(f"  ℹ️   {msg}")

def shot(label: str):
    """화면 전체 스크린샷 캡처"""
    if not SCREEN_OK:
        return
    path = SHOT_DIR / f"{label}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        pyautogui.screenshot(str(path))
        ok(f"스크린샷: {path.name}")
    except Exception as e:
        warn(f"스크린샷 실패: {e}")

def shot_window(label: str, win_title_substr: str):
    """특정 창만 잘라서 캡처"""
    if not SCREEN_OK:
        return
    wins = gw.getWindowsWithTitle(win_title_substr)
    if not wins:
        shot(label)  # 전체 화면으로 폴백
        return
    w = wins[0]
    path = SHOT_DIR / f"{label}_{datetime.now().strftime('%H%M%S')}.png"
    try:
        region = (w.left, w.top, w.width, w.height)
        pyautogui.screenshot(str(path), region=region)
        ok(f"창 캡처: {path.name}  ({w.width}×{w.height})")
    except Exception as e:
        warn(f"창 캡처 실패: {e}")

# ── 앱 로그 읽기 (백그라운드 스레드) ──────────────────────
def _stdout_reader(proc, q: queue.Queue):
    """subprocess stdout을 줄 단위로 읽어 큐에 넣기 + 파일 기록"""
    try:
        for raw in iter(proc.stdout.readline, ''):
            line = raw.strip()
            if line:
                q.put(line)
                # 파일에 항상 기록
                ts = datetime.now().strftime("%H:%M:%S")
                _log_file.write(f"  [앱][{ts}] {line}\n")
                _log_file.flush()
                # 주요 키워드는 즉시 터미널 출력
                highlight_kws = [
                    'MolDraw', 'ERROR', 'Error', '오류', 'Traceback',
                    'benzene', 'atoms,', '3D', 'Lewis', 'Theory',
                    'popup', 'SMILES', 'warning', 'Warning', 'selected_keys',
                ]
                if any(kw.lower() in line.lower() for kw in highlight_kws):
                    print(f"\n  [앱] {line}")
    except Exception:
        pass

def wait_for_log(keywords: list, timeout: int = 35, show_dots: bool = True) -> str | None:
    """
    앱 로그에서 keywords 중 하나가 나타날 때까지 대기.
    감지된 줄 반환, 타임아웃이면 None 반환.
    ★ 핵심: 프로세스가 종료되면 즉시 감지하고 None 반환
    """
    deadline = time.time() + timeout
    dot_count = 0
    while time.time() < deadline:
        # ★ 프로세스 조기 종료 감지 (기존 방식의 핵심 결함 수정)
        if _proc and _proc.poll() is not None:
            if show_dots:
                print()
            exit_code = _proc.poll()
            print(f"\n  ⚡  ChemGrid 프로세스가 종료됨 (종료코드: {exit_code})")
            if exit_code != 0:
                warn("  앱 크래시 발생 — 터미널의 Traceback을 확인하세요")
            else:
                warn("  앱이 정상 종료됨 (사용자가 창을 닫은 경우)")
            return None

        remaining = int(deadline - time.time())
        try:
            line = _log_queue.get(timeout=1.0)
            for kw in keywords:
                if kw.lower() in line.lower():
                    if show_dots:
                        print()  # 도트 줄 정리
                    return line
        except queue.Empty:
            pass
        if show_dots:
            dot_count += 1
            dots = '.' * (dot_count % 5)
            print(f"  ⏳ 앱 로그 감지 대기 중{dots:<5}  ({remaining}초 남음)   ", end='\r')

    if show_dots:
        print()
    return None

def wait_for_window(title_substr: str, timeout: int = 25) -> object | None:
    """
    제목에 title_substr이 포함된 창이 열릴 때까지 대기.
    ★ 핵심: 프로세스 종료 시 즉시 반환 (무한 대기 방지)
    """
    if not SCREEN_OK:
        # SCREEN_OK 없을 때도 프로세스 종료 감지
        deadline = time.time() + min(timeout // 2, 8)
        while time.time() < deadline:
            if _proc and _proc.poll() is not None:
                warn(f"  ChemGrid 프로세스 종료됨 (코드: {_proc.poll()})")
                return None
            time.sleep(1.0)
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        # ★ 프로세스 종료 감지
        if _proc and _proc.poll() is not None:
            warn(f"\n  ⚡  ChemGrid 프로세스가 종료됨 (코드: {_proc.poll()})")
            return None
        wins = gw.getWindowsWithTitle(title_substr)
        if wins:
            return wins[0]
        time.sleep(1.2)
    return None

def drain_log(seconds: float = 2.0):
    """큐에 남은 로그를 seconds 동안 비우기"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            line = _log_queue.get_nowait()
            print(f"  [앱] {line}")
        except queue.Empty:
            time.sleep(0.2)

# ══════════════════════════════════════════════════════
#  STEP 0: 파일 동기화 + ChemGrid 실행
# ══════════════════════════════════════════════════════
banner(0, "초기화 — 파일 동기화 & ChemGrid 실행")

# 파일 동기화 (agents/integrated → src/app)
synced, skipped = [], []
for fname in SYNC_FILES:
    src = Path(AGENTS_DIR) / fname
    dst = Path(APP_DIR) / fname
    if src.exists():
        shutil.copy2(src, dst)
        synced.append(fname)
    else:
        skipped.append(fname)

ok(f"파일 동기화 완료: {len(synced)}개")
if skipped:
    note(f"없음(건너뜀): {', '.join(skipped[:5])}")

# ChemGrid 실행 (stdout 파이프 연결)
note(f"ChemGrid 실행: {PYTHON_EXE} draw.py")
note(f"작업 디렉터리: {APP_DIR}")
print()

_proc = subprocess.Popen(
    [PYTHON_EXE, 'draw.py'],
    cwd=APP_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding='utf-8',
    errors='replace',
    bufsize=1,
)

# 백그라운드 로그 리더 시작
_reader = threading.Thread(target=_stdout_reader, args=(_proc, _log_queue), daemon=True)
_reader.start()

ok("프로세스 시작됨 (PID: " + str(_proc.pid) + ")")

# 창이 뜰 때까지 대기
note("ChemGrid 창 로딩 대기 중 (최대 25초)...")
_win = wait_for_window("ChemGrid", timeout=25)
if _win:
    ok(f"창 감지: '{_win.title}'  ({_win.width}×{_win.height})")
    shot("00_app_launched")
else:
    warn("창 자동 감지 실패 — ChemGrid 창이 열렸는지 직접 확인하세요")
    note("계속 진행합니다 (Ctrl+C로 중단 가능)...")

# PyQt 초기화 로그 잠깐 흘려보내기
drain_log(2.5)

# ══════════════════════════════════════════════════════
#  STEP 1: 벤젠 그리기 (AI 텍스트 입력창)
# ══════════════════════════════════════════════════════
banner(1, "AI 텍스트 입력창으로 벤젠 그리기")
guide(
    "ChemGrid 하단 중앙의 어두운 텍스트 입력창을 클릭하세요.\n"
    "  플레이스홀더 텍스트:  '🤖 분자명 입력 (예: hemoglobin, benzene...)'\n"
    "\n"
    "  'benzene' 을 입력한 뒤 Enter 키를 누르세요.\n"
    "  (또는 ⚗ 버튼 클릭)"
)

note("앱 로그에서 그리기 완료 신호를 최대 35초간 감지합니다...")
_result = wait_for_log(
    keywords=['MolDraw', 'benzene', 'selected_keys', 'atoms,', '✅', 'drawn', '[MolDraw]'],
    timeout=35,
)
if _result:
    ok(f"벤젠 그리기 감지: {_result}")
    shot("01_benzene_drawn")
else:
    warn("35초 내 자동 감지 실패.")
    warn("→ 입력창에 'benzene' 입력 후 Enter를 눌렀나요?")
    warn("→ Drawing 레이어(기본 화면)인지 확인하세요")
    shot("01_benzene_timeout")

# ══════════════════════════════════════════════════════
#  STEP 2: 이론적 구조 레이어 전환
# ══════════════════════════════════════════════════════
banner(2, "이론적 구조 레이어 전환")
guide(
    "ChemGrid 우하단의 파란색 '이론적 구조' 버튼을 클릭하세요.\n"
    "  (루이스 구조 계산 후 이론적 구조 레이어로 이동합니다)\n"
    "\n"
    "  이동 후 오른쪽에 파란 '입체 구조' 버튼이 나타나야 합니다."
)

note("레이어 전환 신호 최대 30초 대기...")
_result = wait_for_log(
    keywords=['theory', 'lewis', 'switch', 'view', 'Layer', '레이어'],
    timeout=30,
)
if _result:
    ok(f"레이어 전환 감지: {_result}")
else:
    warn("전환 로그 미감지 — 30초 타임아웃으로 진행")

time.sleep(1.2)  # 애니메이션 완료 대기
shot("02_theory_mode")

# ══════════════════════════════════════════════════════
#  STEP 3: 입체 구조 (3D) 팝업
# ══════════════════════════════════════════════════════
banner(3, "입체 구조 3D 팝업 열기")
guide(
    "이론적 구조 레이어 우측의 파란색 '입체 구조' 버튼을 클릭하세요.\n"
    "\n"
    "  [버튼이 회색(비활성)이면 → B1 버그]\n"
    "    agents/06_3d_structure/activation_handler.py 수정 필요\n"
    "    이 경우: 스크린샷만 찍고 다음 단계로 넘어갑니다."
)

note("'3D 분자 분석' 팝업 창이 열릴 때까지 최대 40초 대기...")
_popup_win = wait_for_window("3D", timeout=40)

if _popup_win:
    ok(f"3D 팝업 감지: '{_popup_win.title}'")
    time.sleep(0.8)  # 렌더링 완료 대기
    shot_window("03_3d_popup", "3D")
    shot("03_3d_popup_full")
else:
    # 앱 로그에서 팝업 관련 메시지 확인
    _result = wait_for_log(['popup', '3D', 'OpenGL', 'RDKit', 'MMFF'], timeout=5)
    warn("3D 팝업 창 미감지")
    if _result:
        note(f"관련 로그: {_result}")
    warn("가능한 원인:")
    warn("  • B1: '입체 구조' 버튼이 비활성화 상태")
    warn("  • B2: popup_3d.py 임포트 오류 (PyOpenGL 미설치)")
    warn("  • B3: SMILES 변환 실패 (canvas → RDKit)")
    shot("03_no_3d_popup")

# ══════════════════════════════════════════════════════
#  STEP 4: 잔여 로그 수집 & 최종 보고
# ══════════════════════════════════════════════════════
banner(4, "최종 상태 캡처 & 결과 보고")
time.sleep(1.5)
shot("99_final_state")
drain_log(3.0)

# 촬영된 스크린샷 목록
shots = sorted(SHOT_DIR.glob("*.png"))

sep = "━" * 70
_tee(f"\n{sep}")
_tee("  📊 테스트 결과 요약")
_tee(f"{sep}")
_tee(f"  • 스크린샷 저장 위치 : {SHOT_DIR}")
_tee(f"  • 세션 로그 파일    : {_LOG_PATH}")
_tee(f"  • 캡처된 파일 수    : {len(shots)}개")
_tee(f"  • ChemGrid 프로세스 : {'실행 중 (PID ' + str(_proc.pid) + ')' if _proc.poll() is None else '종료됨 (종료코드 ' + str(_proc.poll()) + ')'}")
_tee("")
_tee("  수정 필요 항목 (master_plan.md 기준):")
_tee("  🔴 B1: '이론적 구조'에서 '입체 구조' 버튼 비활성 → activation_handler.py")
_tee("  🔴 B2: 3D 팝업 미실행 → popup_3d.py 임포트/경로 오류")
_tee("  🔴 B4: 벤젠 전자구름 비균등 → engine_resonance.py ConjugationEngine")
_tee("")
_tee("  최근 캡처된 스크린샷:")
for s in shots[-6:]:
    _tee(f"    {s.name}")
_tee("")
_tee(f"  ★ AI 피드백용 로그: {_LOG_PATH}")
_tee(f"{sep}")

# 프로세스 종료 여부 확인
print("  ChemGrid를 종료하려면 Enter, 계속 실행하려면 Ctrl+C:")
try:
    input()
    _proc.terminate()
    ok("ChemGrid 프로세스 종료 완료")
except KeyboardInterrupt:
    note("프로세스를 그대로 유지합니다.")
finally:
    _log_file.close()
    print(f"\n  📄 세션 로그 저장 완료: {_LOG_PATH}")
