# Skill: 사용자 환경 피드백 (User Environment Feedback)

## 개요
실제 GUI 앱을 실행하고, pyautogui + pygetwindow로 마우스/키보드 조작 → 스크린샷 검증 → 코드 수정 루프를 수행하는 워크플로우.

## 언제 사용하는가
- Theory/Lewis/Drawing 레이어 렌더링 결과를 시각적으로 검증할 때
- 3D 팝업(popup_3d.py)의 탭/오비탈/진동모드 UI가 제대로 동작하는지 확인할 때
- 버튼 클릭, 탭 전환 등 GUI 인터랙션 테스트가 필요할 때

## 실행 방법

### 1. 앱 실행
```bash
# conda 환경 직접 Python 실행 (conda run은 인코딩 문제 있음)
C:/ProgramData/anaconda3/envs/chemgrid/python.exe src/app/draw.py
```

### 2. GUI 테스트 스크립트 패턴
```python
import pyautogui, pygetwindow, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# 창 찾기 (정확한 제목 우선 매칭)
def find_chemgrid():
    for w in pygetwindow.getAllWindows():
        if w.title == "ChemGrid V5":
            return w
    for w in pygetwindow.getAllWindows():
        if "ChemGrid" in w.title and "통합 3D" not in w.title:
            return w
    return None

# 안전한 activate
def safe_activate(win):
    try:
        win.activate()
    except Exception:
        pass
    time.sleep(0.3)
```

### 3. 스크린샷 → 분석 → 수정 루프
1. `pyautogui.screenshot(region=(left, top, width, height))` 캡처
2. 이미지 분석으로 UI 상태 확인
3. 문제 발견 시 코드 수정 → 앱 재실행 → 재검증

## 주의사항
- DPI 스케일링: 현재 환경 2560x1440, DPI=96 (100%)
- QTabWidget 탭 위치는 균등 분배가 아님 — 스크린샷 픽셀 분석 필요
- conda run에서 한글(cp949) 인코딩 오류 발생 → 직접 python.exe 사용
- pygetwindow activate() "Error 183" → try/except 래핑 필수
- 3D 팝업 제목 "ChemGrid — 통합 3D..." 때문에 메인 창과 혼동 주의

## 관련 파일
- `tools/test_3d_popup.py` — 3D 팝업 GUI 테스트 스크립트
- `tools/test_theory_buttons.py` — Theory 레이어 버튼 테스트
