# Skill: ChemGrid 아키텍처 가이드

## 코드베이스 구조

### 실행 경로
- **메인 앱**: `src/app/draw.py` → `Run_ChemGrid.bat` → conda `chemgrid` 환경
- **백업 소스**: `_source/` (항상 `src/app/`과 동기화 필수!)
- **Conda 환경**: `chemgrid` (Python 3.12, RDKit 2025.09.5, PyQt6 6.10.2, PyOpenGL)

### 3-레이어 캔버스 시스템
| 레이어 | 파일 | 역할 |
|--------|------|------|
| Drawing | `canvas.py` | 마우스로 분자 그리기 (원자, 결합) |
| Lewis | `layer_logic.py` | 루이스 구조 (론페어, 형식전하) |
| Theory | `layer_logic.py` | 이론적 구조 (전자 구름, ESP, 결합각) |

### 핵심 엔진
| 파일 | 역할 |
|------|------|
| `analyzer.py` (v6.11) | SMILES 생성, 전하 분포, 입체화학, lewis_map, theory_data |
| `engine_core.py` (v2.80) | π-시스템 감지, 고리 탐지, Hückel 4n+2 방향족 판정 |
| `engine_physics.py` (v7.0) | 유도 효과, 치환기 점수, 전기음성도 기반 부분 전하 |
| `engine_resonance.py` (v5.90) | HMO π-전자 밀도, EDG/EWG 방향성 효과 |

### 팝업 윈도우
| 파일 | 기능 |
|------|------|
| `popup_3d.py` | 통합 3D 분석 (OpenGL, 5탭: 속성/스펙트럼/진동/AI/도킹) |
| `popup_reaction.py` | 유기합성반응 분석 (반응 예측 + 메커니즘 시각화) |
| `popup_spectrum.py` | IR/Raman 스펙트럼 |
| `popup_nmr.py` | NMR 스펙트럼 |
| `popup_molorbital.py` | 분자 오비탈 시각화 (ORCA cube) |
| `popup_docking.py` | 분자 도킹 (AutoDock Vina) |

### 도킹 시스템
| 파일 | 역할 |
|------|------|
| `docking_interface.py` | AutoDock Vina 백엔드 (PDB 다운로드, PDBQT 변환, Vina 실행) |
| `docking_data.py` | 데이터 클래스 (PDBAtom, ReceptorData, DockingResult 등) |
| `docking_3d_viewer.py` | QPainter 기반 2D 투영 단백질 뷰어 |
| `docking_interaction_analyzer.py` | H-bond, π-stacking, 소수성 접촉 분석 |

## 중요 규칙

### Dual Codebase 동기화
변경 시 반드시 `src/app/`과 `_source/` **양쪽 모두** 수정!
```bash
cp src/app/modified_file.py _source/modified_file.py
```

### 다중 분자 감지
`analyzer.py`의 `_get_molecular_islands()` — DFS 기반 연결 성분 분석
- 반환: `List[Set[atom_keys]]` — 각 set이 하나의 분자
- RDKit `GetMolFrags()`도 dot-SMILES 분리에 사용

### Theory 레이어 데이터 흐름
```
canvas atoms/bonds → analyzer.analyze() → analysis_results
    ↓
analysis_results["theory_data"]["coords"] → TheoryRenderer.render()
analysis_results["lewis_map"] → h_count, lp_count, formal_charge per atom
analysis_results["charges"] → ESP color mapping (δ+/δ-)
```

### ORCA DFT 통합
- `orca_interface.py`: ORCA 입력 생성 (B3LYP/6-31G(d))
- `OrcaOutputParser`: .out 파일 파싱 (에너지, 쌍극자, 주파수, 노말모드)
- `popup_3d.py`에서 ORCA 데이터 로드 → 진동모드 애니메이션/스펙트럼 표시
