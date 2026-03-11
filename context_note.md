# Context Note — 루트 (QA/검증 세션)
## 최종 업데이트: 2026-03-05 00:28

### 기술적 판단 기록

#### [2026-03-01] draw.py vs main_window.py 이중 구조 발견
- **상황:** toolbar_setup.py 수정이 반영되지 않는 문제
- **원인:** `draw.py`에 **자체 MainWindow 클래스** (line 1577)가 있으며, `if __name__ == "__main__"`으로 직접 실행됨. `main_window.py`는 draw.py와 **별개 파일**이며, draw.py 실행 시 무시됨.
- **해결:** `_patch_draw.py`로 draw.py의 인라인 툴바 코드(122줄)를 `from toolbar_setup import setup_toolbars; setup_toolbars(self)` 호출로 교체
- **주의:** 앞으로 draw.py의 MainWindow를 수정할 때는 main_window.py가 아닌 **draw.py 직접** 또는 **toolbar_setup.py** 등 draw.py가 import하는 모듈을 수정해야 함

#### [2026-03-01] .pyc 캐시 문제
- Python은 __pycache__에 .pyc를 생성하며, 프로세스가 실행 중이면 새 .pyc를 즉시 재생성함
- **해결:** 반드시 `taskkill /IM python.exe /F` 후 .pyc 삭제 → 재시작 순서를 지켜야 함

#### [2026-03-01] conda run -n chemgrid 멀티라인 -c 불가
- `conda run -n chemgrid python -c "...multiline..."` 실행 시 NotImplementedError 발생
- **해결:** 스크립트를 파일로 저장 후 `conda run -n chemgrid python script.py`로 실행

#### [2026-03-04] Interactive Verification & Mouse Drawing Feedback
- **목표:** 실제 마우스 이벤트 없이 `MoleculeCanvas`의 그리기 로직과 SMILES 생성 기능을 검증.
- **구현:** `IsolatedCanvasTester` 클래스 (`_interactive_verification.py`)
  - **이벤트 우회:** `QMouseEvent`를 시뮬레이션하는 대신, `canvas.atoms`와 `canvas.bonds` 딕셔너리에 데이터를 직접 주입(Direct Injection)하는 방식 채택.
  - **좌표 스냅 문제 해결:** `get_closest_pt` 메서드가 `MoleculeCanvas` 내부의 그리드 스냅 로직(반올림 오차 등)으로 인해 `None`을 반환하는 문제가 발생.
  - **해결책:** `get_closest_pt`를 호출하지 않고, 테스트 스크립트에서 계산한 그리드 좌표를 `round(x, 2)` 처리하여 바로 딕셔너리 키로 사용. `self.test_atoms`와 `self.test_bonds`에 데이터를 먼저 저장하고 `self.canvas`에 동기화하여 데이터 소실 방지.
  - **검증 흐름:** Recipe 정의 (좌표, 액션) -> `execute_steps` (데이터 주입) -> `verify_result` (SMILES 생성 및 비교).
- **교훈:** UI 컴포넌트의 내부 로직(SMILES 변환 등)을 테스트할 때는 UI 이벤트 시뮬레이션보다 **데이터 상태 제어**가 훨씬 안정적이고 디버깅이 용이함.

---

## 2026-03-10 BUG-3 해결 기술 메모

### 발견된 버그 체인
1. **analyze() generate_smiles() 실패** (이온성 방향족 SMILES 파싱 오류)
   → smiles_str = "" → ring 감지 없음 → aromatic set 비어있음
   
2. **renderer.py fallback 1** (aromatic set 비어있으면 ring_atoms_all도 비어있음)

3. **renderer.py fallback 2 버그** ← 진짜 근본 원인!
   ```python
   at_sym = atoms.get(pt_key, {}).get("main", "C")
   if is_size >= 3 and at_sym == "C":  # WRONG
   ```
   - carbon은 main='' (빈 문자열) 로 저장됨!
   - "C" 비교가 항상 False → ring_atoms_all 영원히 비어있음

### 적용된 수정
- `src/app/renderer.py`: `at_sym == "C"` → `at_sym in ('', 'C')`
- `src/app/analyzer.py`: `analyze(atoms, bonds, smiles=None)` + SMILES 폴백
- `src/app/canvas.py`: `analyze()` 호출 시 `_last_drawn_smiles` 주입
- `src/app/main_window.py`: `analyze()` 호출 시 `_last_drawn_smiles` 주입

### ChemGrid atoms dict 규칙 (필수 암기)
| 원소 | main 값 |
|------|---------|
| 탄소 (C) | '' (빈 문자열) |
| 산소 (O) | 'O' |
| 질소 (N) | 'N' |
| 기타 | 원소기호 그대로 |

### 검증 결과
- 15/15 PASS (render_test_report.html 2026-03-10 10:57 생성)
- cp- Cyclopentadienyl anion: RED 균등분포 확인
- Tropylium cation: BLUE 균등분포 확인
- Benzene: GREEN 균등분포 확인 (기존과 동일)
