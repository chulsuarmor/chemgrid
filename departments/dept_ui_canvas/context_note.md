# UI/Canvas 부서 기술 노트
> 최종 업데이트: 2026-03-18 | TASK-UC-003/004 완료

## 기술적 판단 기록

### [2026-03-18] TASK-UC-003: scale 하드코딩 → 동적 계산 전환 근거
- 기존: `scale = 26.7` — grid_size=40일 때만 정확 (40/1.5=26.67)
- 수정: `scale = self.cv.grid_size / 1.5` — grid_size가 변경되어도 자동 대응
- 키 충돌 오프셋: `offset * 2.0`은 hex grid와 무관한 2px 이동이라 grid 정렬 깨짐 → `offset * self.cv.grid_size`로 grid 셀 단위 이동

### [2026-03-18] TASK-UC-004: guaranteed fallback 설계
- analyze()가 None을 반환하는 경로: (1) 원자 0개, (2) SMILES 파싱 실패, (3) 내부 예외
- 기존: try/except 2단계만 → 두 번 다 실패하면 analysis_results = None → 하류 코드 크래시
- 수정: 3단계 방어선 추가:
  1. analyze(atoms, bonds, smiles=smiles) [기존]
  2. analyze(atoms, bonds) [기존 fallback]
  3. minimal dict 생성 [NEW: smiles, atoms={}, norm_atoms={}, theory_data=None, formula]
- 'smiles' 키 존재 보장: fallback이 아닌 정상 경로에서도 analyze()가 smiles 키를 빠뜨릴 수 있음 → 명시적 체크

## 📤 SUBMIT 보고서 — CT 상신용

### 수정 파일
| 파일 | 변경 | 동기화 |
|------|------|--------|
| src/app/main_window.py | TASK-UC-003 + UC-004 | _source/ ✅ |

### 검증 결과
- py_compile: OK
- ast.parse: OK
- _source/ diff: 동일
- 10종 분자 headless 테스트: 10/10 PASS
- R-UI 검수자 판정: **PASS**

### 잔여 리스크
- 실제 GUI 시각 검증(스크린샷 기반)은 이 세션에서 미수행 — CT 판단하에 별도 시각 테스트 세션 권장
- grid_size가 40이 아닌 환경은 테스트되지 않음 (현재 ChemGrid는 grid_size=40 고정)

## 발견된 문제 / 블로커
(없음)

## 타 부서 요청 사항
(없음)
