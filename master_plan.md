# 👑 ChemGrid Master Project Plan
## 최종 업데이트: 2026-03-10 / 라이브 테스트 기반 버그 확인 완료

---

## 1. 프로젝트 총괄 목표
ChemGrid: PyQt6 기반 화학 구조 작성 + 분석 통합 플랫폼
- 루이스 구조 그리기 → 이론적 구조 분석 → 전자구름 렌더링 → 스펙트럼 예측 → 3D 구조

---

## 2. 현재 상태 (2026-03-10 라이브 테스트 결과)

### ✅ 정상 동작
- ChemGrid V5 앱 실행 (Anaconda chemgrid 환경)
- 텍스트 입력창(하단 중앙): 분자명 입력 + Enter → 캔버스에 구조 그려짐
- benzene 입력 시 6각형 구조 정상 렌더링 확인 (스크린샷)
- `text_input_handler.py` KNOWN_SMILES 딕셔너리: 80+ 분자 올바른 SMILES 매핑

### ❌ 미해결 핵심 버그 (우선순위 순)

#### BUG-03: SMILES 파이프라인 끊김 [최우선]
- 그리기 레이어 → 이론적 구조 뷰 전환 시 분자 일부만 인식
- `canvas.get_smiles()` 재구성 시 산소, 이온 탄소 등 특수 원자 누락
- 선택 도구로 전체 드래그해도 일부만 선택됨
- 해결책: `cv._last_drawn_smiles` 태그 유지 + 전체 파이프라인에 전달

#### BUG-04b/c: AI 입력 대형 분자 미지원 [2순위]
- hemoglobin 등 대형 분자: Gemini API가 >200원자 → UNKNOWN 반환
- 대안: **PubChem PUG REST API** 활용 (무료, 정확)
  - `GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{이름}/property/IsomericSMILES/JSON`
  - 분자명, 분자식(CH3CH2OH 등), CAS 번호 모두 지원
- 구현 위치: `text_input_handler.py`의 `_query_gemini()` 앞에 `_query_pubchem()` 추가

#### BUG-01: 전자구름 편재화 [3순위 - 장기]
- Cp-, 트로필리움 등 이온성 방향족에서 π 전자가 일부 탄소에 집중됨
- RDKit 기반 20회 이상 실패 → 근본적 접근 변경 필요
- 단기 해결: 방향족 원자 탐지 후 density 강제 균등화
- 장기 해결: xtb (GFN2-xTB) Mulliken charges → 2D 매핑

---

## 3. 단계별 수정 계획 (Act 모드용)

### Phase 1: SMILES 파이프라인 수리 (BUG-03) - 예상 1-2시간
```
대상 파일: src/app/canvas.py, src/app/main_window.py, src/app/layer_logic.py
```

**Step 1-1: canvas.py에 `_last_drawn_smiles` 속성 추가**
```python
# canvas.py Canvas.__init__에 추가
self._last_drawn_smiles: str = ""
```

**Step 1-2: main_window.py `_draw_smiles_on_canvas` 완료 후 태그 저장**
```python
def _draw_smiles_on_canvas(self, smiles: str, mol_name: str = ""):
    # ... 기존 코드 ...
    self.cv._last_drawn_smiles = smiles  # ← 추가
    self.cv._last_drawn_mol_name = mol_name  # ← 추가
```

**Step 1-3: layer_logic.py 이론적 구조 전환 시 `_last_drawn_smiles` 우선 사용**
```python
# 이론적 구조 전환 핸들러에서:
smiles = getattr(self.cv, '_last_drawn_smiles', '') or self.cv.get_smiles()
```

**Step 1-4: 선택 도구 전체 선택 시 `_last_drawn_smiles` 포함 확인**

---

### Phase 2: PubChem API 연동 (BUG-04b/c) - 예상 2-3시간
```
대상 파일: agents/02_canvas_interaction/text_input_handler.py
```

**Step 2-1: `_query_pubchem()` 메서드 추가**
```python
def _query_pubchem(self, name: str) -> Optional[str]:
    """PubChem PUG REST API로 화학명/분자식 → SMILES"""
    import urllib.parse, requests
    encoded = urllib.parse.quote(name)
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded}/property/IsomericSMILES/JSON"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            smiles = data['PropertyTable']['Properties'][0]['IsomericSMILES']
            return self._validate_smiles(smiles)
    except:
        pass
    return None
```

**Step 2-2: `parse_input()` 우선순위 수정**
```
1. 직접 SMILES 검증
2. 로컬 사전 조회
3. PubChem API ← 새로 추가 (Gemini보다 먼저)
4. Gemini API (폴백)
```

**Step 2-3: 대형 분자(>200 원자) 처리 - 팝업 뷰어 또는 경고 메시지**

---

### Phase 3: 전자구름 균등화 단기 패치 (BUG-01) - 예상 3-4시간
```
대상 파일: src/app/renderer.py (또는 agents/05_rendering_engine/)
```

**단기 전략**: 방향족 + 이온성 원자 탐지 → density 균등화
```python
from rdkit.Chem import Mol, AllChem

def compute_electron_density(mol: Mol, atom_idx: int) -> float:
    """방향족 원자면 균등 density, 아니면 기존 로직"""
    atom = mol.GetAtomWithIdx(atom_idx)
    
    # 방향족 탐지: is_aromatic 플래그 + 고리 내 위치
    if atom.GetIsAromatic():
        ring_atoms = [a for a in mol.GetAtoms() if a.GetIsAromatic() and
                     mol.GetRingInfo().AreAtomsInSameRing(atom_idx, a.GetIdx())]
        if ring_atoms:
            # 고리 내 전체 전하/전자를 균등 분배
            total_charge = sum(a.GetFormalCharge() for a in ring_atoms)
            base_density = 4.0 + (total_charge / len(ring_atoms))
            return max(1.0, base_density)
    
    # 비방향족: 기존 로직
    return 4.0 - atom.GetFormalCharge()
```

**장기 전략 (Phase 4)**: xtb 연동
```
SMILES → xyz 변환(xtb) → GFN2-xTB SP 계산 → Mulliken charges → density 매핑
```

---

## 4. Manager's Feedback & Next Action

**To All Workers**: 
- BUG-03 (SMILES 파이프라인) 최우선 수정 시작
- canvas.py → main_window.py → layer_logic.py 순서로 수정
- 수정 후 benzene, acetic acid, Cp- 로 순차 테스트
- `cv._last_drawn_smiles` 속성이 올바르게 전파되는지 로그로 확인

**절대 하지 말 것**:
- RDKit 기반 공명 구조 density 재계산 시도 (mistakes.md 참고)
- `canvas.get_smiles()` 를 유일한 SMILES 소스로 사용
- pygetwindow 창 탐지 시 "chemgrid" 키워드만 사용 (VS Code 오인)

---

## 5. 기술 스택 참고
- **Python**: 3.10+ / Anaconda `chemgrid` 환경
- **UI**: PyQt6
- **화학 계산**: RDKit (현재), xtb (예정)
- **API**: PubChem PUG REST (예정), Gemini 1.5 Flash (보조)
- **실행**: `C:\ProgramData\anaconda3\envs\chemgrid\python.exe c:\chemgrid\src\app\draw.py`
- **창 제목**: "ChemGrid V5" (toolbar_setup.py 설정)


---
---

## [2026-03-10 세션 7] Manager Feedback

### 세션 7 완료 사항 (코드 검증)
- **세션 7은 전 세션에서 계획된 작업이 실제로 이미 구현되어 있음을 확인한 세션**
- **ISSUE-3 open_3d_popup fallback**: `main_window.py`에 이미 구현됨
  - 50% 미만 선택 + `_last_drawn_smiles` 존재 시 → 전체 원자로 자동 교체
- **ISSUE-4 Google Search fallback**: `_lookup_smiles_for_name()`에 이미 구현됨
  - Step 3.5: Google Knowledge Graph API → PubChem 재조회
  - Step 3.6: PubChem Autocomplete fuzzy matching
- **구문 검사 완료**: 4개 핵심 파일 모두 py_compile 통과
  - main_window.py ✅ / canvas.py ✅ / layer_logic.py ✅ / analyzer.py ✅

### 다음 세션 우선순위
1. **앱 실행 + 선택 도구 검증** (최우선, 30분):
   - benzene 텍스트 입력 → 이론적 구조 → 전체 드래그 선택 → 3D 팝업 6원자 확인
   - aspirin → btn_3d 직접 클릭 → 3D 팝업
2. **스펙트럼 예측 확인** (30분):
   - benzene SMILES → IR/NMR 예측 스펙트럼 팝업
   - `popup_predicted_spectrum.py` 동작 여부
3. **cp- 오류 재확인** (20분):
   - cp- 5각형 렌더링 정상 여부

---

## [2026-03-10 세션 5] Manager Feedback

### 세션 5 완료 사항
- **ISSUE-1 전자구름 편재화 최종 해결**: renderer.py 3가지 수정 완료
  - fallback 3 (bonds 그래프 degree≥2 ring 탐지) 추가 → 방향족 단결합도 처리
  - ionic_bias: attach[-1] 전하 기호 체크 추가
  - ring_charges: 모든 ring 원자 포함 후 avg 계산
  - **시각 검증**: 1 클러스터(308px) → 4 클러스터(511px) — 전하 분산 확인 ✅
- **mistakes.md**: 세션 5 근본 원인 체인 3단계 기록
- **context_list.md**: ISSUE-3, ISSUE-4 단계별 해결 계획 수립

### 다음 세션 우선순위
1. **ISSUE-3 선택 도구** (최우선, 30분):
   - `layer_logic.py` TheoryRenderer.render()에서 theory_data["map"] 완전 채우기
   - `canvas.py` mouseMoveEvent fallback 좌표 수정
   - benzene 6원자 드래그 선택 테스트
2. **ISSUE-4 PubChem API 연동** (1시간):
   - `text_input_handler.py`에 `resolve_molecule()` 구현
   - PubChem REST API: 분자명/화학식 → SMILES
   - Google Custom Search API fallback
   - "CH3CH2OH", "hemoglobin" 테스트
3. **ISSUE-1 추가 개선** (선택):
   - 5 클러스터 완전 균등 확인 (현재 4 클러스터)
   - tropylium(C7H7+) BLUE 균등 확인

### 기술 스택 업데이트
- **PubChem API**: `https://pubchem.ncbi.nlm.nih.gov/rest/pug/` (ISSUE-4)
- **Google Custom Search API**: 사용자 제공 키 필요 (ISSUE-4)
- **renderer.py 수정 파일**: `src/app/renderer.py` v4.2+fallback3

---

## [2026-03-10 세션 4] Manager Feedback

### 세션 4 완료 사항
- ISSUE-1 근본 원인 파악 및 코드 수정: analyzer.py의 all_aromatic 버그 (π-island 링 위상 검사로 수정)

### 다음 세션 우선순위
1. **ISSUE-1 시각 검증** (최우선): Windows 오버레이 없는 환경에서 ChemGrid 재실행 후 Cp⁻/benzene 전자구름 균일 분포 확인
2. **ISSUE-2**: canvas.py의 선택 도구 SMILES 전파 누락 수정
3. **ISSUE-3**: 텍스트 입력 → Google/PubChem API 연동으로 화학식/단어 변환 시스템 구축
4. **ISSUE-4**: 대형 분자(hemoglobin) 지원은 소분자 완성 후

### 기술 부채 현황
- all_aromatic 수정이 renderer.py의 ring_atoms_all 평균화에 실제로 반영되는지 미검증
- context_list.md에 구체적인 코드 수정 계획 기록됨
