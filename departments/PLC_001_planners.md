# 전학공 #1 — 기획자(P) 직렬 교차학습
> 실시일: 2026-03-18 | Cascade #3 사후
> 참여 대상: P-UI, P-CHEM, P-RENDER, P-3D, P-SPEC, P-RXTN, P-ORCA, P-DOCK, P-EXPORT, P-VFB, P-TEST, P-ALPHA

---

## 1. 공통 패턴: Graceful Fallback Architecture (12/12 부서 채택)

**핵심 원칙**: 외부 의존성(RDKit, scipy, Gemini API, xtb, Vina, reportlab)이 없어도 크래시 없이 기능이 동작해야 한다.

**표준 패턴**:
```python
try:
    result = primary_method(data)
except (ImportError, RuntimeError) as e:
    result = fallback_method(data)  # 대체 로직
    result.is_fallback = True       # 플래그로 구분
```

**우수 사례**:
- P-DOCK: 3-tier (Python Vina → subprocess Vina → simulation heuristic)
- P-3D: scipy.ndimage.map_coordinates → distance-based fallback
- P-EXPORT: reportlab → QPrinter
- P-ALPHA: ColabFold API → RCSB → error dict

**채택 지침**: 새 기능 구현 시 반드시 2-tier 이상 fallback 설계 후 코딩 시작.

---

## 2. 공통 패턴: Dual Codebase Sync (src/app/ ↔ _source/)

**교훈**: 12개 부서 모두 sync 검증 통과. 방법:
- 수정 완료 후 즉시 `_source/` 복사 (절대 나중에 하지 않음)
- R-agent가 MD5/diff로 재검증

**채택 지침**: 파일 수정 시 `_source/` sync를 마지막이 아닌 즉시 수행.

---

## 3. Carbon = '' (빈 문자열) 규칙 (전 부서 필수)

**교훈**: P-CHEM, P-RENDER, P-DOCK, P-TEST 모두 이 규칙 위반 시 즉시 버그 발생.
- `atom["element"] == "C"` → **틀림**
- `atom["element"] == ""` → **맞음**

**채택 지침**: 새 코드에서 원소 비교 시 반드시 chem_data.py ELEMENT_DATA 참조.

---

## 4. 부서별 우수 기법 공유

### P-UI (Canvas 부서)
- **3-stage fallback for analysis()**: (1) With SMILES → (2) Without SMILES → (3) Minimal dict with guaranteed keys
- **Grid-relative positioning**: 절대 pixel 값 대신 `offset * grid_size` 사용

### P-CHEM (화학 엔진)
- **Dual aromatic detection**: Hückel (4n+2) → RDKit GetIsAromatic() fallback
- **CRC Handbook 기반 bond length**: 64개 결합 ±0.01Å 정확도

### P-RENDER (렌더링)
- **Logical toggle decoupling**: `show_clouds` 토글을 `view_state`와 분리 → 모든 레이어에서 동작
- **painter.save()/restore()**: QPainter 상태 관리 try/finally 패턴
- **Cross-department 버그 보고**: 타 부서 파일 수정 대신 context_note.md에 기록 → 올바른 에스컬레이션

### P-3D (3D 뷰어)
- **Connected component analysis**: Ferrocene 등 금속 착물의 disconnected fragment 처리
- **Threshold + clamp 패턴**: bond strain ±2% 노이즈 필터, ±15% 오버슈트 방지
- **Orbital colormap 통일**: +phase=Blue, -phase=Red (Atkins/Clayden 표준)

### P-SPEC (분광학)
- **Group priority logic**: specific groups → generic groups 순서 (C=N_pyridine before C=C)
- **Dual SMARTS for charged variants**: P=O, NO2 등 중성/하전 형태 모두 매칭
- **Explicit atom validation**: `GetTotalNumHs() > 0` 확인 후 bonded H 가정

### P-RXTN (반응/합성)
- **Multi-fragment handling**: `GetMolFrags()` + pairwise combination
- **Adaptive arrow geometry**: 길이 기반 arrowhead 크기 (min 7, max 12, 0.12*length)
- **3-tier SanitizeMol**: full → partial → original SMILES (valence 위반 중간체 처리)

### P-ORCA (DFT/ORCA)
- **MOREAD+NOITER**: 기존 .gbw 재활용으로 SCF 재계산 없이 cube 생성
- **xtb wrapper pattern**: executable finder → validation → XYZ generator → charge parser

### P-DOCK (도킹)
- **SpatialHash**: 5.5Å 셀 기반 공간 인덱싱 → O(n) 근접 원자 탐색
- **Path validation**: `is_file()` 사용 (not `exists()`) — Windows에서 `Path("")` 함정 회피
- **Newell's method**: 비평면 고리의 normal vector 계산

### P-EXPORT (출력/통합)
- **Temporary state switching**: view_state 변경 후 캡처 → 원래 상태 복원
- **Format versioning**: `_chem_version` 키로 v1/v2 호환성 유지
- **Korean font fallback chain**: Malgun → Gulim → Helvetica

### P-VFB (시각적 피드백)
- **Headless screenshot**: QWidget.grab() + WA_DontShowOnScreen
- **processEvents cycling**: 백그라운드 스레드 spawn 후 3x processEvents() 대기
- **Archive automation**: results.json 메타데이터 + zip 자동 압축

### P-TEST (테스팅/빌드)
- **unittest.subTest**: 분자별 파라메트릭 테스트 (1개 실패해도 나머지 계속)
- **Hidden imports**: PyInstaller spec에 24개 모듈 명시적 추가

### P-ALPHA (AlphaFold/신약)
- **SMARTS-based feature detection**: Pharm2D factory 대신 직접 SMARTS로 pharmacophore 추출
- **Composite scoring**: 가중합 패턴 (QED 0.30 + affinity 0.35 + ADMET 0.25 - alerts 0.10)
- **dataclass 기반 결과 구조**: type-safe + 직렬화 용이

---

## 5. Cascade #4 적용 지침

1. **새 기능 설계 시**: 반드시 fallback 2-tier 이상 포함
2. **Carbon 비교**: `== ""` 사용, `== "C"` 절대 금지
3. **src/app/ 수정 즉시**: `_source/` 동기화 (마지막에 모아서 하지 않음)
4. **타 부서 파일 발견 시**: context_note.md에 REQUEST 기록, 직접 수정 금지
5. **QPainter 사용 시**: save()/restore() try/finally 패턴 적용
6. **spatial proximity 문제**: SpatialHash 패턴 참조 (dept_docking/skills/)
