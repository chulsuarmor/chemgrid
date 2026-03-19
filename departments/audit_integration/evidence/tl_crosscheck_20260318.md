# TL Cross-Check 검증 결과 — 2026-03-18

## 빌드(B1) vs E2E(V1) 교차 검증

### 일관성 확인
| 검증 항목 | B1 (빌드) | V1 (E2E) | 일치 여부 |
|-----------|-----------|----------|-----------|
| py_compile 통과율 | 63/64 | - | - |
| import chain 통과율 | - | 63/64 | **일치** (동일 실패: edit_popup.py) |
| 실패 모듈 | edit_popup.py | edit_popup.py | **일치** |
| visual test | - | 44/44 PASS | - |
| conda deps | sklearn FAIL | - | - |

### 핵심 발견 사항

#### CRITICAL (즉시 수정 필요)
1. **`edit_popup.py` 구문 오류** — py_compile과 import chain 모두에서 동일하게 실패.
   - 원인: line 2에서 시작되는 triple-quoted string이 line 4에서 종료되지 않음
   - 영향: 해당 모듈을 사용하는 기능 전체 불능

#### HIGH (빠른 수정 권장)
2. **scikit-learn 미설치** — `sklearn` import 실패
   - 현재 `scikit-image`만 설치됨
   - sklearn을 사용하는 모듈이 있는 경우 런타임 에러 발생 가능
   - 수정: `pip install scikit-learn` 또는 `conda install scikit-learn`

3. **_source/ 동기화 심각한 불일치** — 86건 차이
   - 12개 파일 내용 불일치 (draw.py, coord_utils.py 등 핵심 파일 포함)
   - src/app/에만 존재하는 파일 다수 (base_spectrum.py, dialogs.py, lasso_selection.py 등)
   - _source/에 테스트/디버그 잔여 파일 다수
   - 백업 목적의 _source/ 역할이 무력화된 상태

#### MEDIUM
4. **google.generativeai 패키지 FutureWarning** — `popup_docking.py`에서 발생
   - 지원 종료된 패키지 사용 중, `google.genai`로 전환 필요

### 전체 판정
| 항목 | 판정 |
|------|------|
| 빌드 안정성 | **PASS (조건부)** — edit_popup.py 1건 제외 |
| 테스트 통과율 | **PASS** — 44/44 visual tests |
| 파이프라인 정합성 | **PASS** — 4/5 pipelines OK |
| 의존성 완결성 | **FAIL** — sklearn 미설치 |
| 듀얼 코드베이스 동기화 | **FAIL** — 86건 불일치 |
| **종합 판정** | **CONDITIONAL PASS** |

### 권장 조치 우선순위
1. `edit_popup.py` 구문 오류 수정
2. `scikit-learn` 설치
3. `_source/` 동기화 작업 (src/app/ -> _source/ 복사 또는 동기화 스크립트 실행)
4. `google.generativeai` -> `google.genai` 마이그레이션 계획 수립
