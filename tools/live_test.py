"""
tools/live_test.py
ChemGrid 실제 사용자 환경 라이브 테스트
──────────────────────────────────────────
- Anaconda chemgrid 환경으로 앱 직접 실행
- 텍스트 입력창(하단 중앙) 위치 자동 계산
- benzene / cyclopentadienyl anion 입력 후 스크린샷
- current_state.json SMILES 확인
- 스크린샷 HTML로 결과 보고
"""
import sys, os, time, json, subprocess
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    import pygetwindow as gw
    from PIL import Image
    import numpy as np
except ImportError as e:
    print(f"의존성 없음: {e}. pip install pyautogui pygetwindow Pillow numpy")
    sys.exit(1)

CONDA_PY  = r"C:\ProgramData\anaconda3\envs\chemgrid\python.exe"
APP_DIR   = r"c:\chemgrid\src\app"
APP_ENTRY = r"c:\chemgrid\src\app\draw.py"
OUT_DIR   = Path(r"c:\chemgrid\tools\test_screenshots\live")
STATE_JSON= Path(r"c:\chemgrid\current_state.json")
REPORT    = Path(r"c:\chemgrid\tools\live_test_report.html")
OUT_DIR.mkdir(parents=True, exist_ok=True)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.3

def ts():
    return datetime.now().strftime("%H%M%S")

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def shot(name, region=None):
    p = OUT_DIR / f"{name}_{ts()}.png"
    pyautogui.screenshot(region=region).save(str(p))
    log(f"📸 {p.name}")
    return p

def find_win(title_sub="ChemGrid V5"):
    """
    ChemGrid V5 창 탐색.
    - "Visual Studio Code" 포함 창 제외
    - "ChemGrid" 포함 + "Visual Studio Code" 미포함 창 반환
    """
    for w in gw.getAllWindows():
        t = w.title
        if not t:
            continue
        # VS Code, 탐색기 등 제외
        if "Visual Studio Code" in t or "탐색기" in t or "Discord" in t:
            continue
        if title_sub.lower() in t.lower() and w.width > 200:
            return w
    return None

def wait_win(title_sub="ChemGrid V5", timeout=40):
    """ChemGrid V5 창이 뜰 때까지 최대 40초 대기"""
    t0 = time.time()
    log(f"ChemGrid V5 창 대기 중 (최대 {timeout}s)...")
    while time.time()-t0 < timeout:
        w = find_win(title_sub)
        if w:
            # 실제 ChemGrid 앱인지 추가 검증
            if "Visual Studio Code" not in w.title:
                log(f"창 발견: '{w.title}' ({w.width}×{w.height})")
                return w
        # 현재 창 목록 주기적 출력 (디버깅)
        elapsed = int(time.time()-t0)
        if elapsed % 5 == 0:
            all_titles = [w.title for w in gw.getAllWindows() if w.width > 200 and w.title]
            log(f"  [{elapsed}s] 현재 창 목록: {all_titles[:5]}")
        time.sleep(0.5)
    return None

def get_smiles():
    try:
        if STATE_JSON.exists():
            return json.loads(STATE_JSON.read_text(encoding="utf-8")).get("smiles","")
    except:
        pass
    return "(파일 없음)"

def get_input_pos(win):
    """mol_name_input 위치 계산.
    PyQt6: iy = self.height() - input_h - 18
    pygetwindow: win.height = OS 전체 창 높이 (title bar 포함)
    → 절대 좌표: win.top + win.height - INPUT_H - 18
    """
    INPUT_H = 38
    input_w = min(580, win.width - 160)
    # 수평 중앙
    ix = win.left + (win.width - input_w) // 2
    # 수직: 창 하단에서 (INPUT_H + 18)px 위
    iy = win.top + win.height - INPUT_H - 18
    cx = ix + input_w // 2
    cy = iy + INPUT_H // 2
    log(f"  입력창 계산: win=({win.left},{win.top},{win.width},{win.height}) → ({cx},{cy})")
    return cx, cy, ix, iy, input_w

# ── 결과 저장용 ────────────────────────────────────────────────
steps = []
shots = []

def step(name, ok, detail=""):
    icon = "✅" if ok else "❌"
    log(f"{icon} {name}: {detail}")
    steps.append({"name": name, "ok": ok, "detail": detail})

# ════════════════════════════════════════════════════════════════
#  메인 테스트 실행
# ════════════════════════════════════════════════════════════════
log("=" * 60)
log("ChemGrid 라이브 테스트 시작")
log("=" * 60)

# 1. 앱 실행
log(f"앱 실행: {CONDA_PY} {APP_ENTRY}")
proc = subprocess.Popen(
    [CONDA_PY, APP_ENTRY],
    cwd=APP_DIR,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE
)
step("앱 프로세스 시작", proc.poll() is None, f"PID={proc.pid}")

# 2. 창 대기
log("창 대기 중 (최대 30s)...")
win = wait_win("ChemGrid", timeout=30)
if not win:
    log("❌ ChemGrid 창을 찾지 못함. 에러 로그:")
    try:
        err = proc.stderr.read(3000).decode(errors="replace")
        log(err)
    except:
        pass
    step("창 뜨기", False, "타임아웃")
    sys.exit(1)

step("창 뜨기", True, f"{win.title} | {win.width}×{win.height}")
time.sleep(1.5)

# 3. 초기 스크린샷
try: win.activate()
except: pass
time.sleep(0.3)
s0 = shot("01_initial")
shots.append(("초기 화면", s0))
step("초기 스크린샷", True, s0.name)

# 4. 텍스트 입력창 위치 계산 및 클릭
cx, cy, ix, iy, iw = get_input_pos(win)
log(f"입력창 예상 위치: ({cx},{cy}) | 실제 창: ({win.left},{win.top}) {win.width}×{win.height}")
s_toolbar = shot("02_before_input")
shots.append(("입력 전 화면", s_toolbar))

# ── 테스트 케이스 ──────────────────────────────────────────────
test_cases = [
    ("benzene",                "6π 방향족 (기본 테스트)"),
    ("cyclopentadienyl anion", "Cp- 이온성 방향족 (핵심 버그 테스트)"),
    ("tropylium",              "트로필리움 C7H7+ (이온성 방향족)"),
    ("CH3CH2OH",               "에탄올 분자식 직접 입력"),
]

for mol_text, desc in test_cases:
    log(f"\n── 테스트: {desc} ──")

    # 창 재활성화
    try: win.activate()
    except: pass
    time.sleep(0.3)

    # 입력창 클릭 (하단 중앙)
    pyautogui.click(cx, cy)
    time.sleep(0.4)

    # 기존 텍스트 지우기
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.press('delete')
    time.sleep(0.1)

    # 텍스트 입력 (pyperclip 사용)
    try:
        import pyperclip
        pyperclip.copy(mol_text)
        pyautogui.hotkey('ctrl', 'v')
    except ImportError:
        pyautogui.typewrite(mol_text, interval=0.06)

    time.sleep(0.3)
    safe = mol_text.replace(" ", "_").replace("/", "_")
    s_typed = shot(f"03_typed_{safe}")
    shots.append((f"{desc} — 입력 후", s_typed))

    # Enter 전송
    pyautogui.press('enter')
    log(f"  Enter 전송, 렌더링 대기 3s...")
    time.sleep(3.0)

    # SMILES 확인
    smiles = get_smiles()
    smiles_ok = bool(smiles and smiles not in ("", "C"))
    step(f"[{mol_text}] SMILES 생성", smiles_ok, f"→ '{smiles}'")

    # 스크린샷
    s_drawn = shot(f"04_drawn_{safe}")
    shots.append((f"{desc} — 렌더링", s_drawn))

    # 이론적 구조 뷰 전환 시도 (하단 오른쪽 버튼)
    # 창 크기 기반 이론적 구조 버튼 위치 추정
    theory_x = win.left + int(win.width * 0.91)
    theory_y = win.top  + int(win.height * 0.93)
    log(f"  이론적 구조 버튼 클릭: ({theory_x},{theory_y})")
    pyautogui.click(theory_x, theory_y)
    time.sleep(2.0)

    s_theory = shot(f"05_theory_{safe}")
    shots.append((f"{desc} — 이론 뷰", s_theory))

    # 돌아가기 (다음 테스트를 위해)
    pyautogui.click(theory_x, theory_y)
    time.sleep(1.0)

# 최종 스크린샷
s_final = shot("99_final")
shots.append(("최종 화면", s_final))

# ── HTML 보고서 생성 ───────────────────────────────────────────
log("\nHTML 보고서 생성 중...")
ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
pass_n = sum(1 for s in steps if s["ok"])
total_n = len(steps)

rows = ""
for s in steps:
    icon = "✅" if s["ok"] else "❌"
    cls  = "pass" if s["ok"] else "fail"
    rows += f'<tr class="{cls}"><td>{icon}</td><td>{s["name"]}</td><td>{s["detail"]}</td></tr>\n'

shots_html = ""
for desc, p in shots:
    shots_html += f"""
    <div class="shot">
      <h4>📸 {desc}</h4>
      <img src="{p}" style="max-width:900px;border:1px solid #444;border-radius:6px"/>
    </div>"""

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>ChemGrid 라이브 테스트 보고서</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#12121f;color:#e0e0e0;padding:20px}}
h1{{color:#4fc3f7}} h2{{color:#81d4fa;border-bottom:1px solid #333;padding-bottom:5px;margin-top:25px}}
h4{{color:#b0bec5;margin:5px 0}}
.sum{{background:#16213e;padding:15px 20px;border-radius:8px;margin:12px 0;display:flex;gap:25px;align-items:center}}
.score{{font-size:2.2em;font-weight:bold;color:{'#4caf50' if pass_n==total_n else '#ff9800'}}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #333;padding:8px 12px}}
th{{background:#16213e;color:#81d4fa}}
tr.pass td{{background:rgba(76,175,80,.15)}} tr.fail td{{background:rgba(244,67,54,.15)}}
.shot{{background:#1a1a2e;padding:10px;border-radius:8px;margin:10px 0}}
</style>
</head>
<body>
<h1>🧪 ChemGrid 라이브 테스트 보고서</h1>
<div class="sum">
  <div><small style="color:#90a4ae">실행 시각</small><br>{ts_str}</div>
  <div><small style="color:#90a4ae">결과</small><br><span class="score">{pass_n}/{total_n}</span></div>
</div>
<h2>📋 테스트 결과</h2>
<table><tr><th>결과</th><th>항목</th><th>상세</th></tr>{rows}</table>
<h2>📸 단계별 화면</h2>
{shots_html}
</body></html>"""

REPORT.write_text(html, encoding="utf-8")
log(f"\n보고서 생성 완료: {REPORT}")
log(f"최종 결과: {pass_n}/{total_n} PASS")

# 앱 종료
try:
    proc.terminate()
    log("앱 프로세스 종료")
except:
    pass

print(f"\nREPORT_PATH={REPORT}", flush=True)
