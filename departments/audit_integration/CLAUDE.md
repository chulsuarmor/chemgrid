# audit_integration — 통합 파이프라인 감사팀
> 3인 체제: 팀장(TL) + 빌드관(B1) + E2E 검증관(V1)

---

## 역할
빌드 성공, 테스트 통과, 부서간 API 호환, 듀얼 코드베이스 동기화를 검증.
**코드가 실제로 실행 가능한지** + **부서간 연결이 끊어지지 않았는지** 확인.

## 팀 구성

### 팀장 (TL-INTEG)
- B1, V1 결과를 **교차확인** — 빌드 성공인데 E2E 실패이면 원인 추적
- 부서간 인터페이스 변경 감지 (함수 시그니처, import 경로)
- 최종 감사 보고서 서명 및 CT 상신
- ⛔ 직접 코드 수정 금지

### 빌드관 (B1-BUILD)
- py_compile 전체 파일 (src/app/*.py)
- _source/ ↔ src/app/ 동기화 diff 확인
- conda 환경 의존성 확인
- PyInstaller 빌드 테스트 (tools/build_chemdraw.bat)
- 산출물: `evidence/build_log_YYYYMMDD.md`

### E2E 검증관 (V1-E2E)
- test_visual_auto.py 실행 → 결과 확인 (44/44 PASS 기대)
- test_visual_3d.py 실행 → 3D 렌더링 확인
- 부서간 데이터 흐름 테스트:
  - canvas → analyzer → renderer (2D 파이프라인)
  - main_window → popup_3d → vibration_engine (3D 파이프라인)
  - retrosynthesis_engine → building_blocks → popup_synthesis (합성 파이프라인)
  - popup_docking → docking_interface → docking_interaction_analyzer (도킹 파이프라인)
- import 체인 검증: 모든 모듈이 순환 참조 없이 import 가능한지
- 산출물: `evidence/e2e_results_YYYYMMDD.md`

## 감사 프로토콜

### 1단계: 빌드 검증 (B1)
```bash
# 전체 py_compile
/c/ProgramData/anaconda3/envs/chemgrid/python.exe -c "
import py_compile, glob
files = glob.glob('src/app/*.py')
ok = fail = 0
for f in files:
    try:
        py_compile.compile(f, doraise=True); ok += 1
    except: fail += 1; print(f'FAIL: {f}')
print(f'{ok}/{ok+fail} passed')
"

# _source/ 동기화 확인
diff -rq src/app/ _source/ --exclude=__pycache__ --exclude=tests
```

### 2단계: E2E 테스트 (V1)
```bash
# 자동화 테스트
PYTHONIOENCODING=utf-8 /c/ProgramData/anaconda3/envs/chemgrid/python.exe src/app/tests/test_visual_auto.py

# 3D 테스트 (디스플레이 필요)
/c/ProgramData/anaconda3/envs/chemgrid/python.exe src/app/tests/test_visual_3d.py
```

### 3단계: 교차 확인 (TL)
- B1: 빌드 PASS인데 V1: E2E FAIL → import 경로 변경 또는 런타임 에러 추적
- V1: E2E PASS인데 B1: sync FAIL → _source/ 업데이트 누락 추적

## 증거 없는 PASS는 자동 FAIL
빌드 로그, 테스트 결과 로그 없이 "통과"라고 보고하면 **자동 FAIL**.
반드시 `evidence/` 폴더에 로그 파일이 있어야 유효한 감사.

## 세션 프로토콜
1. CLAUDE.md 읽기
2. context_list.md → 현재 감사 요청 확인
3. B1: 빌드 + sync 검증 → 로그 저장
4. V1: E2E 테스트 실행 → 결과 저장
5. TL: 교차확인 → 서명
6. context_list.md + evidence/ 업데이트 → 세션 종료


## 감사 자동 트리거 (v3 업데이트)
- MM이 "내부 QA PASS" 선언 시 자동으로 감사 상신 수신
- CT가 수동 트리거하지 않아도 됨
- 감사 FAIL → MM에 직접 반려 (CT 경유 불필요)
- 감사 PASS → CT에 최종 보고
- CT 월권 감사는 항상 수행 (감사팀 = CT 직속 상위)

