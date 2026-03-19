# Skill: 인코딩 및 플랫폼 이슈

## Windows + 한글 환경 문제

### cp949 인코딩 오류
- **문제**: `conda run`이 stdout을 cp949로 처리 → 한글/특수문자 오류
- **해결**: conda run 대신 직접 Python 실행
```bash
C:/ProgramData/anaconda3/envs/chemgrid/python.exe script.py
```

### Em dash (—) 인코딩
- **문제**: 윈도우 제목 "ChemGrid — 통합 3D"의 em dash가 cp949에서 오류
- **해결**: `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')`

### 파일 I/O
- 항상 `encoding='utf-8'` 명시
- PDB 파일: `errors='ignore'` 추가 (비표준 문자 포함 가능)

## pyautogui / pygetwindow 이슈

### activate() Error 183
- **문제**: "파일이 이미 있으므로 만들 수 없습니다" (Windows 내부 오류)
- **해결**: try/except 래핑
```python
def safe_activate(win):
    try:
        win.activate()
    except Exception:
        pass
    time.sleep(0.3)
```

### 창 탐색 혼동
- 3D 팝업 제목이 "ChemGrid"로 시작 → 메인 창으로 오인
- **해결**: 정확한 "ChemGrid V5" 매칭 우선

### DPI 스케일링
- 현재 환경: 2560×1440, DPI=96 (100% 스케일링)
- pyautogui 좌표는 논리 좌표 (스케일링 무관)
- QTabWidget 탭 위치는 스크린샷 픽셀 분석으로 측정 필요
