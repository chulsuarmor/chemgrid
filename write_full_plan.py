"""
사용자가 요청한 4개 이슈 전체를 context_list.md에 기록하고
과거 실패 내역을 mistakes.md에 추가
"""

# === context_list.md 전체 이슈 기록 ===
plan_section = """
================================================================================
# 2026-03-10 사용자 요청 이슈 목록 및 단계적 해결 계획
================================================================================

## ISSUE-1: 공명구조 분자의 전자구름 편재화 오류 (20회 시도 실패)

### 현상
- 사이클로펜타디에닐 음이온(Cp⁻), 트로필리움 이온(C7H7⁺) 등
  공명구조로 전자가 고리 전체에 고르게 분포해야 하는 분자에서
  전자구름이 일부 탄소에만 편재화되어 표시됨
- 이론값: 모든 탄소에 동일한 전자밀도 → 시각화: 균일한 구름 색상

### 실패한 방법들 (mistakes.md 참조)
- RDKit formal_charge 기반 → 부분 전하 계산 오류
- SMILES 파싱 후 Gasteiger 전하 → 방향족 이온에서 부정확
- 수동 공명구조 가중치 → 케이스별 하드코딩 한계
- 20회 이상 시도 전부 실패

### 단계적 해결 계획

#### Phase 1: 방향족 이온 감지 + 강제 균등화 (단기, 1일)
- [ ] SMILES에서 완전 방향족 고리(aromatic ring) + 전하 조합 감지
  - 예: `[CH-]1cccc1` (Cp⁻), `[cH+]1cccccc1` (C7H7⁺)
- [ ] 방향족 고리 내 탄소의 전자밀도를 평균화하는 후처리 함수 작성
  - `engine_resonance.py`의 `fix_resonance_charge()` 확장
- [ ] 사이클로펜타디에닐, 트로필리움, 벤젠, 나프탈렌 테스트 케이스 검증

#### Phase 2: ORCA DFT 연계 파이프라인 (중기, 1주)
- [ ] SMILES → RDKit 3D 좌표 생성 → ORCA input 파일 작성
- [ ] ORCA: `! RHF/UHF 6-31G* Mulliken` 전자밀도 계산
- [ ] `.out` 파일 파싱 → 원자별 Mulliken 전하 추출
- [ ] Mulliken 전하 → 2D 렌더러 전자구름 색상 매핑
- [ ] `agents/07_orca_dft/` 모듈에 파이프라인 구현

#### Phase 3: 대체 학술 도구 활용 (Phase 2 실패 시)
- [ ] `pySCF`, `xtb` (Grimme 그룹) 경량 전자밀도 계산 라이브러리 검토
- [ ] GitHub: `github.com/grimme-lab/xtb` → 설치 및 연동 테스트

---

## ISSUE-3: SMILES 선택 도구 일부만 인식 (레이어 간 누락 버그)

### 현상
- 그리기 레이어 → 이론적 구조 변환은 정상
- 이론적 구조 → 입체 구조 변환 시:
  - 분자 전체를 선택해도 산소, 양전하 탄소 등 일부만 인식
  - 분자가 클수록 더 심각 (헤모글로빈 등 대형 분자 전혀 인식 못 함)

### 근본 원인 (분석 완료)
- `main_window.py`: `_last_drawn_smiles`를 `analyze()` 호출 AFTER에 설정
  → 이론→입체 변환 시 이전 SMILES 또는 공백이 넘어감 (BUG-B 수정 완료)
- `layer_logic.py`: 레이어 간 SMILES 전달 체인 검토 필요

### 단계적 해결 계획

#### Step 1: BUG-B 후속 검증 (즉시)
- [x] `_last_drawn_smiles` 타이밍 수정 완료 (2026-03-10)
- [ ] 실제 구동으로 산소 포함 분자(CCO, c1ccccc1O 등) 선택 도구 테스트

#### Step 2: layer_logic.py 파이프라인 추적 (1일)
- [ ] `layer_logic.py`의 이론→입체 변환 코드에서 SMILES 전달 경로 완전 추적
- [ ] 선택 도구가 `canvas.py`에서 SMILES를 어떻게 가져오는지 확인
  - `_get_smiles_from_selection()` 또는 유사 함수 분석
- [ ] 빈 SMILES / None 가드 추가

#### Step 3: 대형 분자 지원 (1주)
- [ ] 헤모글로빈 SMILES 분할 처리 (서브구조 단위 처리)
- [ ] `layer_logic.py`에 청크 기반 SMILES 파싱 시스템 구현

---

## ISSUE-4: AI 텍스트 분자 생성기 Google API 연동

### 현상
- "benzene" 입력 → cyclohexane 그림 (방향족 인식 못 함)
- "hemoglobin" 입력 → 아무것도 안 나옴
- 그리기 로직 자체가 SMILES 없이 원자 배치에만 의존

### 단계적 해결 계획

#### Step 1: Google Custom Search API → PubChem 연결 (즉시 구현 가능)
- [ ] `text_input_handler.py` 수정:
  ```python
  def name_to_smiles(query: str) -> str:
      # 1) PubChem REST API (무료, 가장 정확)
      url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/property/IsomericSMILES/JSON"
      resp = requests.get(url, timeout=5)
      if resp.ok:
          return resp.json()['PropertyTable']['Properties'][0]['IsomericSMILES']
      
      # 2) Fallback: Google Custom Search API
      #    query → 상위 결과에서 SMILES 추출
      ...
  ```
- [ ] `CH3CH2OH`, `ethanol`, `에탄올` 등 다양한 입력 형태 처리
  - 화학식 → PubChem `formula` 엔드포인트
  - 분자명 → PubChem `name` 엔드포인트
  - SMILES 직접 입력 → 유효성 검증 후 바로 사용

#### Step 2: Google API 키 활용 (Step 1 실패 케이스)
- [ ] `agents/mcp_server/.env`의 GOOGLE_API_KEY 확인
- [ ] Google Knowledge Graph API로 분자 CID 검색 → PubChem 연결

#### Step 3: 대형 분자 처리
- [ ] PubChem에서 헤모글로빈 SMILES 가져오기 (너무 길 수 있음)
- [ ] 서브유닛 분리 렌더링 또는 "분자가 너무 복잡합니다" 안내 메시지

---

## 현재 완료된 수정 내역 요약

| 날짜 | 버그 | 파일 | 상태 |
|------|------|------|------|
| 2026-03-10 | BUG-A: 3D 방향족 결합 이중결합 표현 | popup_3d.py | ✅ 완료 |
| 2026-03-10 | BUG-B: _last_drawn_smiles 타이밍 | main_window.py | ✅ 완료 |
| 2026-03-10 | IR/NMR 스펙트럼 검증 | predict_spectra.py | ✅ PASS |

"""

# mistakes.md에 과거 실패 기록 추가
mistakes_section = """
---

## [2026-03-10] ISSUE-1: 공명구조 전자구름 편재화 — 20회 실패 패턴 정리

**상황**: 방향족 이온(Cp⁻, C7H7⁺)의 전자구름을 균등하게 표시하려는 시도

**실패한 접근들 (공통 패턴)**:
1. RDKit `GetFormalCharge()` → 단일 원자에만 전하 배정됨 (공명구조 반영 안 됨)
2. Gasteiger 전하 계산 → 방향족 이온에서 부정확 (이온화 상태 미고려)
3. 수동 SMARTS 패턴 매칭 → 모든 케이스 커버 불가
4. partial charge 평균화 → 고리 크기에 따라 다른 결과
5. resonance_forms 열거 → RDKit 제한으로 일부 공명구조만 생성

**공통 실패 원인**:
- RDKit의 2D SMILES 파싱 기반 전하 계산은 공명 평균화를 지원하지 않음
- 방향족 이온의 실제 전자 분포는 양자역학적 계산 없이 정확히 결정 불가

**올바른 접근**:
- SMILES → 3D 구조 → ORCA RHF/DFT 계산 → Mulliken/Löwdin 전하 → 2D 매핑
- 단기: 방향족 고리 감지 후 강제 균등화 (근사적 해결)
- 절대 금지: `GetFormalCharge()` 또는 `Gasteiger` 기반 방향족 이온 처리

---

## [2026-03-10] ISSUE-4: AI 텍스트 분자 생성기 — 반복 실패 패턴

**상황**: "benzene" 입력 시 cyclohexane이 그려지는 등 AI 생성기 오작동

**실패 원인**:
- LLM에게 SMILES 생성을 요청했을 때 방향족 표기(소문자 c) 대신
  일반 탄소(C)로 그림 → RDKit에서 non-aromatic으로 해석
- 자체 생성 SMILES가 유효하지 않아 fallback 처리 없이 에러

**올바른 접근**:
- LLM에게 SMILES 생성 시키지 말 것
- PubChem REST API `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/property/IsomericSMILES/JSON`
  으로 검색 후 검증된 SMILES 사용
- SMILES 유효성 검증: `Chem.MolFromSmiles(s)` None이면 재시도
"""

# context_list.md에 추가
with open('context_list.md', 'a', encoding='utf-8') as f:
    f.write(plan_section)
print('context_list.md 전체 계획 추가 완료')

# mistakes.md에 추가
with open('docs/ai/mistakes.md', 'a', encoding='utf-8') as f:
    f.write(mistakes_section)
print('mistakes.md 과거 실패 기록 추가 완료')

print('\n=== 전체 문서화 완료 ===')
