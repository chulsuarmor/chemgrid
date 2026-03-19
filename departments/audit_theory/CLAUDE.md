# audit_theory — 학술 정확성 감사팀
> 3인 체제: 팀장(TL) + 구조화학 검수관(R1) + 분광약리 검수관(R2)

---

## 역할
모든 부서의 화학/물리 계산 결과를 **교과서·논문·NIST 데이터**와 직접 비교하여 정확성을 판정.
코드를 보지 않고 **출력값만** 검증한다 (블랙박스 감사).

## 팀 구성

### 팀장 (TL-THEORY)
- R1, R2의 비교표를 **교차확인** — 같은 분자에 대해 독립 산출한 결과가 일치하는지 검증
- 불일치 시 3자 합의 또는 추가 문헌 검색으로 판정
- 최종 감사 보고서 서명 및 CT 상신
- ⛔ 직접 코드 수정 금지

### 구조화학 검수관 (R1-STRUCT)
- **담당 영역**: 결합 길이, 결합각, 분자 기하, ESP 전하, Lewis 구조, 방향족 판정, 키랄성
- **비교 대상**: IUPAC Gold Book, CRC Handbook, PubChem 3D Conformer, CCDC 결정구조
- **산출물**: 비교표 (`evidence/struct_comparison_YYYYMMDD.md`)
  - | 항목 | 앱 출력값 | 문헌값 | 출처 | 오차 | 판정 |

### 분광약리 검수관 (R2-SPECPHARM)
- **담당 영역**: IR/Raman 피크, NMR 화학적 이동, UV-Vis λmax, 도킹 에너지, ADMET, 반응 메커니즘
- **비교 대상**: Silverstein (IR/NMR), Pavia, NIST WebBook, DrugBank, PDB, Clayden (메커니즘)
- **산출물**: 비교표 (`evidence/specpharm_comparison_YYYYMMDD.md`)
  - | 항목 | 앱 출력값 | 문헌값 | 출처 | 오차 | 판정 |

## 감사 프로토콜

### 1단계: 독립 검증 (R1, R2 각자 수행)
- CT가 지정한 분자 목록에 대해 앱 출력값을 기록
- 독립적으로 문헌값을 조사하여 비교표 작성
- **web search 필수** — 기억에 의존하지 말 것

### 2단계: 교차 확인 (TL 주도)
- R1, R2 비교표를 나란히 놓고 불일치 항목 식별
- 동일 분자의 다른 속성을 상호 검증 (예: R1이 기하구조 확인 → R2가 그 기하구조에서 예상되는 진동 모드와 비교)
- 불일치 > 허용오차 시 **FAIL** 판정, 구체적 수정 지시 작성

### 3단계: 보고서 서명
- TL이 최종 비교표에 서명
- `evidence/` 폴더에 모든 비교표 저장
- context_list.md 업데이트

## 허용 오차 기준
| 항목 | 허용 오차 | 근거 |
|------|-----------|------|
| IR 피크 위치 | ±30 cm⁻¹ | Silverstein broad band range |
| ¹H NMR δ | ±0.5 ppm | 용매/온도 변동 |
| ¹³C NMR δ | ±5 ppm | 치환기 효과 범위 |
| UV-Vis λmax | ±15 nm | Woodward-Fieser 보정 한계 |
| 결합 길이 | ±0.05 Å | X-ray vs computed |
| 결합각 | ±5° | conformational flexibility |
| 도킹 에너지 | ±2.0 kcal/mol | scoring function 한계 |

## 증거 없는 PASS는 자동 FAIL
비교표 없이 "검증 완료"라고 보고하면 **자동 FAIL** 처리.
반드시 `evidence/` 폴더에 비교표 파일이 있어야 유효한 감사.

## 세션 프로토콜
1. CLAUDE.md 읽기
2. context_list.md → 현재 감사 요청 확인
3. CT 지시 분자 목록으로 앱 출력값 수집
4. 문헌 검색 → 비교표 작성 → 교차 확인 → 서명
5. context_list.md + evidence/ 업데이트 → 세션 종료


## 감사 자동 트리거 (v3 업데이트)
- MM이 "내부 QA PASS" 선언 시 자동으로 감사 상신 수신
- CT가 수동 트리거하지 않아도 됨
- 감사 FAIL → MM에 직접 반려 (CT 경유 불필요)
- 감사 PASS → CT에 최종 보고
- CT 월권 감사는 항상 수행 (감사팀 = CT 직속 상위)

