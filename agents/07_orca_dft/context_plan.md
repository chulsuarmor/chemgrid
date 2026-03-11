# 📋 Agent 07: ORCA DFT — Context Plan
## 최종 업데이트: 2026-02-28 21:50 / Manager 승인 완료

### 0. 역할
- **Worker AI** (ORCA DFT 전담)
- 작업 폴더: `agents/07_orca_dft`

### 1. 🔴 긴급 수정: C1 + C5 (포터블 경로)

#### 현재 문제 (하드코딩된 절대 경로)
```python
# ❌ orca_interface.py L27-28
ORCA_PATH = Path(r"C:\Users\김남헌\Desktop\organicdraw\Orca.6.1.1")
ORCA_EXE = ORCA_PATH / "Orca6.1.1.Win64.exe"
```

#### 수정 (포터블 경로)
```python
# ✅ 수정
import os
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
# ORCA는 프로젝트 루트/Orca.6.1.1에 위치
ORCA_PATH = _SCRIPT_DIR / "Orca.6.1.1"
ORCA_EXE = ORCA_PATH / "orca.exe"  # 실제 exe명 확인 필요
```

**실제 exe 파일명 확인 방법:**
```cmd
dir "Orca.6.1.1\*.exe" /b
```
프로젝트 루트에 `Orca.6.1.1/` 폴더가 있으며, 안에 다수의 exe 파일이 존재합니다.

### 2. 세부 구현 목표
- orca_interface.py 리팩토링: 인풋 생성 / 실행 / 파싱 3단계 분리
- 에러 처리 강화 (ORCA 미설치, 수렴 실패, 타임아웃 등)
- electron_density_analyzer.py 정리

### 3. 3단계 분리 구조
```
orca_interface.py
├── OrcaInputGenerator (클래스)
│   └── generate_input(atoms, bonds, charge, mult) → Path
├── OrcaExecutor (클래스)
│   └── execute(input_path, work_dir, timeout) → Path  # .out 파일 경로
├── OrcaOutputParser (클래스)
│   └── parse(out_path) → OrcaCalculationResult
└── OrcaCalculatorThread (QThread) — 위 3개를 조합하여 백그라운드 실행
```

### 4. ORCA 설치 자동 감지
```python
def find_orca_executable():
    """포터블: 여러 후보 경로에서 ORCA 실행 파일 탐색"""
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    
    candidates = [
        script_dir / "Orca.6.1.1" / "orca.exe",
        script_dir / "Orca.6.1.1" / "Orca6.1.1.Win64.exe",
        script_dir.parent / "Orca.6.1.1" / "orca.exe",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    # 환경변수 PATH에서 orca 검색
    import shutil
    orca_in_path = shutil.which("orca")
    if orca_in_path:
        return Path(orca_in_path)
    
    return None  # ORCA 미발견
```

### 5. 포터블 경로 규칙 (MANDATORY)
- 절대 경로 금지
- `__file__` 기반 상대 경로 필수
- zip 배포 시 어떤 디렉토리에서도 ORCA 자동 감지

### 6. 마일스톤
- Phase 1: ORCA 경로 포터블화 (C1, C5)
- Phase 2: 3단계 클래스 분리
- Phase 3: 에러 처리 강화
- Phase 4: electron_density_analyzer.py 정리
- Phase 5: H2O 분자 DFT 테스트

> **상태:** 승인 완료 — 작업 시작 가능
