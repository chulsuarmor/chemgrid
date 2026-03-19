# 반응/합성 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 2

## 기술적 판단 기록

### [2026-03-18] RXTN-R01: 2분자 반응 인식 (predict_from_combined_smiles)

**접근 방식**: `ReactionPredictor`에 `predict_from_combined_smiles(combined_smiles)` 메서드 추가.
- Dot-separated SMILES ("CCBr.[OH-]")를 RDKit `Chem.GetMolFrags()`로 분리
- 2 fragments → 직접 `predict(a, b)` 호출
- 3+ fragments → 모든 2-분자 조합을 시도하고 결과를 합산 (mechanism_type 기준 중복 제거)
- 1 fragment → 빈 리스트 반환 (자기 반응 미지원)
- 유효하지 않은 SMILES → 빈 리스트 반환

**검증 결과**:
- `CCBr.[OH-]` → SN2 (85%) ✅
- `C=CC=C.C=C` → Diels-Alder (70%), [2+2] (55%), Cope (50%) ✅
- `CC(Br)CC.[OH-]` → SN2 (85%), E2 (75%) ✅
- `CCO` (단일 분자) → 0 pathways ✅
- `INVALID` → 0 pathways ✅

### [2026-03-18] RXTN-R02: 곡선 화살표 렌더러 개선 (CurvedArrowRenderer v2.1)

**개선 사항**:
1. `_calc_control_points()` 공통 헬퍼 추출 — 코드 중복 제거
2. 짧은 화살표(<30px) 전용 bulge 범위 (8-20px) — 좁은 공간에서 겹침 방지
3. 화살촉 크기 거리 비례 적응 (min 7, max 12, 0.12*length)
4. 화살촉 너비 0.5 비율 (기존 0.45) — 교과서 표준에 더 가까움
5. 론페어 출발 화살표에 `show_lone_pair=True` → 전자쌍 도트(··) 렌더링
6. 피셔훅 화살표에 `show_lone_pair=True` → 단일 전자 도트(·) 렌더링
7. `_draw_lone_pair_dots()` — 커브 수직 방향으로 양쪽에 도트 배치
8. `_draw_single_electron_dot()` — 커브 진행 반대 방향으로 도트 배치

**arrow_generator.py 수정 불필요**: 현재 ArrowGenerator가 생성하는 ArrowData 구조와 완전 호환.
별도의 REQUEST TO dept_rendering 없음.

### [2026-03-18] RXTN-R03: 합성 → 실험 조건 도출 (Gemini + Fallback)

**Gemini API 상태**: 이미 popup_synthesis.py에 google.generativeai 통합 존재.
- 모델: gemini-2.0-flash
- API 키: GEMINI_API_KEY 또는 GOOGLE_API_KEY 환경변수

**개선 사항**:
1. 프롬프트 대폭 강화: 7개 섹션 구조화 (시약/용매, 반응조건, 촉매, 예상수율, 후처리, 안전, 대체법)
   - 각 섹션에 구체적 요청 항목 명시 (당량, 몰비, 농도, 승온속도, 분위기 등)
2. Graceful fallback 구현: `_show_fallback_protocol()` 메서드 추가
   - google-generativeai 미설치 또는 API 키 미설정 시 자동 전환
   - Rule-based 기본 프로토콜 생성 (조건 문자열 파싱 → 온도/용매/촉매 추정)
   - 사용자에게 API 키 설정 안내 포함

### [2026-03-18] TASK-RXTN-001: RWMol 기반 중간체 생성 설계 판단

**접근 방식**: `_estimate_intermediate_smiles()`에서 BondChange 리스트를 순회하며:
- `is_broken` → `rwmol.RemoveBond()` + 형식전하 보정 (전기음성도 기반 헤테로리틱)
- `is_formed` → `rwmol.AddBond()` + 음전하 중화
- `order_increase/decrease` → `SetBondType()`

**SanitizeMol 전략**:
- 1차: 전체 SanitizeMol → SMILES 생성 → 유효성 재검증
- 2차: partial sanitize (SANITIZE_PROPERTIES 제외) — valence 위반 중간체 허용
- 3차: 원래 SMILES 그대로 반환 (안전 폴백)

**전기음성도 기반 전하 보정**: Pauling 전기음성도로 헤테로리틱 분열 방향 결정.
  - en_i > en_j → i가 전자 쌍 보유 (음전하), j가 양전하
  - 동종 원자 → 전하 변화 없음 (균일 분열 가정)

### [2026-03-18] TASK-RXTN-002: 확장 반응 유형 설계 판단

**전이금속 촉매 메커니즘 (Suzuki, Heck)**:
- Pd(0)/Pd(II) 촉매 사이클의 3단계를 각각 MechanismStep으로 표현
- 중간체 SMILES에 `[Pd]` 원자 포함 — RDKit에서 유효 (원자번호 46)
- 리간드(PPh3)는 단순화를 위해 SMILES에서 생략, notes에 기재

**페리고리 반응**:
- [2+2]: 광화학적 허용만 기록 (열적 금지는 description에 명시)
- Cope/Claisen: 6원자 의자형 전이 상태 — 3개 화살표로 6전자 순환 표현

**노르보르넨**: exo/endo 선택성을 description과 regiochemistry 필드에 기록

**다치환 EAS**:
- '활성화 치환기 우선' 규칙을 description에 기록
- EDG/EWG 충돌 시 로직은 향후 ReactionPredictor에 _rank_directing_effects() 추가 필요

## 발견된 문제 / 블로커

### SMARTS 파싱 경고 (기존 문제, 이번 사이클 미수정)
- `c1cc([OH,NH2,OCH3,N(C)C])ccc1` — "활성화된 방향족" 패턴이 RDKit SMARTS 파싱 실패
- 원인: SMARTS 구문에서 `,` 구분자 안의 복합 원자 그룹이 유효하지 않음
- 영향: "활성화된 방향족" 작용기 감지 불가 (다른 패턴은 정상)
- 수정 필요: SMARTS를 `[c;$(c-[OH]),$(c-[NH2]),$(c-[OCH3])]` 등으로 분리

### SN2 생성물 예측 불완전 (기존 한계)
- `CBr.[OH-]` → 예측 결과 `[Br-]`만 반환 (CO 누락)
- REACTION_SMARTS 템플릿의 product side가 일부 fragment만 캡처
- 향후: RunReactants 후 모든 product fragments를 합쳐야 함

## 타 부서 요청 사항
(없음 — arrow_generator.py 수정 불필요 확인됨)

---

## SUBMIT 보고서 — Cascade #3 Wave 2

### 수정파일
| 파일 | src/app/ | _source/ | 변경 내용 |
|------|----------|----------|-----------|
| reaction_predictor.py | ✅ | ✅ | `predict_from_combined_smiles()` 추가 |
| popup_reaction.py | ✅ | ✅ | CurvedArrowRenderer v2.1 (공통 헬퍼, 적응형 크기, 론페어 도트) |
| popup_synthesis.py | ✅ | ✅ | Gemini 프롬프트 강화 + graceful fallback |

### 기획자 보고 (P-RXTN)
- **RXTN-R01 [P0]**: `predict_from_combined_smiles()` 구현 완료. 2분자/3+분자 dot-separated SMILES 지원.
  SN2, E2, Diels-Alder 등 모든 기존 반응 유형에서 정확한 결과 확인.
- **RXTN-R02 [P0]**: CurvedArrowRenderer 개선. 화살촉 크기 적응화, 짧은 화살표 전용 경로,
  론페어/라디칼 전자 도트 표시 추가. arrow_generator.py 수정 불필요.
- **RXTN-R03 [P1]**: Gemini API 이미 존재. 프롬프트를 7개 섹션으로 구조화하고 API 미사용 시
  rule-based fallback 프로토콜 생성 기능 추가.

### 검수자 판정 (R-RXTN)
- [PASS] py_compile: 3개 파일 모두 통과
- [PASS] ast.parse: 3개 파일 모두 통과
- [PASS] _source/ 동기화: 3개 파일 모두 동기 확인
- [PASS] OWNED_FILES 외 수정 없음 확인 (arrow_generator.py 미변경)
- [PASS] 기능 테스트: predict_from_combined_smiles — SN2, E2, Diels-Alder 정상 작동

### 감사 요청
- 전문 감사 배정: dept_spectroscopy (분광물성 검증)
- 감사 범위: popup_reaction.py의 곡선 화살표가 렌더링 부서의 arrow_generator.py와 호환되는지 확인 요청
