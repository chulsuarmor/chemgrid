# 📝 🧪 테스트/빌드 — Technical Notes
## 기술적 판단 및 결정 기록

### [2026-02-28] Phase 6-1A Critical + Major 버그 수정 완료

#### 수정 전략
- 원본 `_source/` 파일은 읽기 전용 유지
- `apply_critical_fixes.py` 스크립트로 프로그래밍 방식 패치 적용
- 수정본은 `fixed_*.py` 파일로 에이전트 폴더에 생성
- `verify_critical_fixes.py`로 27개 자동 검증 항목 전량 통과

#### 수정 상세
| ID | 파일 | 수정 내용 |
|----|------|----------|
| C1 | orca_interface.py | `ORCA_PATH = Path(r"C:\Users\...")` → `_SCRIPT_DIR / "Orca.6.1.1"` |
| C2 | popup_3d.py | `from PyQt6.QtOpenGL import GL` 제거 (PyQt6에 없는 모듈) |
| C3 | draw.py | `self.canvas.repaint()` → `self.update()` (self 자체가 canvas) |
| C4 | draw.py | verification_report except에서 Orbital 메시지 분리 |
| C5 | draw.py | `_analyze_dft_electron_density()` 하드코딩 경로 → `__file__` 기반 |
| M1 | draw.py | `draw_crosshairs_v32()` 3회→1회 (최상위 Z-INDEX만 유지) |
| M2 | draw.py + renderer.py | 디버그 print 15개 제거 (매 프레임 콘솔 스팸 방지) |
| M5 | draw.py | `start_periodic_reporting()` 주석처리 (Discord 보고 비활성화) |

---

### [2026-02-28 23:10] Phase 6-1B 통합 빌드 완료

#### 충돌 해결 전략 (Master Plan 결정 기반)
3건의 파일 충돌이 있었으며 Manager의 결정에 따라 해결:

**이슈 1: orca_interface.py**
- Agent 10: C1 경로만 수정 (minimal)
- Agent 07: 전면 리팩토링 (포터블 경로 + 3클래스 분리 + 예외 5종 + os.chdir 제거)
- **결정:** Agent 07 채택 (더 포괄적)

**이슈 2: draw.py**
- Agent 10: C3/C4/C5/M1/M2/M5 패치 (원본 기반)
- Agent 02: MoleculeCanvas → canvas.py 분리 + C3/C4/C5/M1/M2 동일 수정
- **결정:** Agent 02 채택 (구조 분리 포함)
- M5 패치: Agent 02에서 progress_tracker 참조가 이미 없음 → 추가 적용 불필요

**이슈 3: renderer.py**
- Agent 10: M2 print 제거만
- Agent 05: draw_clouds 8헬퍼 분리 + print→logging + QPen 수정
- **결정:** Agent 05 채택 (print 제거가 이미 포함됨)

---

### [2026-03-01 00:40] Phase 6-3 최종 통합 + 빌드 완료

#### 병합 수행 내용
- `merge_phase63.py` 스크립트로 26개 에이전트 산출물을 `integrated/`에 병합
- 6개 신규 파일 추가: main_window.py, dialogs.py, toolbar_setup.py, ui_utils.py, base_spectrum.py, phase_integration.py
- Agent 01 (UI), Agent 02 (캔버스), Agent 03 (루이스), Agent 04 (분석), Agent 05 (렌더링), Agent 06 (3D), Agent 07 (ORCA), Agent 08 (분광학) 산출물 전부 반영

#### base_spectrum.py metaclass 충돌 수정
- **문제:** `class BaseSpectrumPopup(QDialog, ABC)` — ABCMeta + sip.wrappertype 메타클래스 충돌
- **해결:** 결합 메타클래스 `_ABCQMeta(ABCMeta, type(QDialog))` 생성 → `metaclass=_ABCQMeta`
- **패턴:** PyQt6 + ABC 사용 시 항상 이 패턴 필요

#### ChemDraw → ChemGrid 이름 변경
- 19개 파일에서 34건 교체
- 대소문자 3가지 변형 모두 처리: ChemDraw→ChemGrid, chemdraw→chemgrid, CHEMDRAW→CHEMGRID
- 검증: 잔존 0건

#### PyInstaller 빌드
- **빌드 도구:** PyInstaller 6.19.0
- **환경:** Python 3.12.12 (Anaconda chemgrid), Windows 11
- **옵션:** --onefile --windowed --name ChemGrid
- **Hidden imports:** PyQt6, OpenGL, matplotlib, numpy, scipy, networkx, rdkit, requests (18개)
- **리소스 번들링:** .png(7), .ico(1), .chem(9), orca_history/ — --add-data 사용
- **결과:** ChemGrid.exe 110.4 MB → c:\chemgrid\ChemGrid.exe 복사 완료

#### 비차단 경고
- `popup_3d.py:85`: `google.generativeai` FutureWarning → `google.genai`로 교체 권장
  - Agent 06 소관 파일이므로 여기서 수정하지 않음
  - 기능 정상 동작 (deprecation warning만)

#### 통합 디렉토리 최종 구조
```
integrated/ (57 항목)
├── draw.py              ← Agent 01 (런처/MainWindow)
├── main_window.py       ← Agent 01 (NEW)
├── dialogs.py           ← Agent 01 (NEW)
├── toolbar_setup.py     ← Agent 01 (NEW)
├── ui_utils.py          ← Agent 01 (NEW)
├── canvas.py            ← Agent 02 (MoleculeCanvas)
├── coord_utils.py       ← Agent 02
├── layer_logic.py       ← Agent 03 (VSEPR v3.0)
├── lasso_selection.py   ← Agent 03 (NEW)
├── analyzer.py          ← Agent 04 (Procrustes)
├── engine_core.py       ← Agent 04
├── engine_physics.py    ← Agent 04
├── engine_resonance.py  ← Agent 04
├── renderer.py          ← Agent 05 (8헬퍼+logging)
├── popup_3d.py          ← Agent 06 (Phase 7)
├── orca_interface.py    ← Agent 07 (3클래스+예외)
├── electron_density_analyzer.py ← Agent 07
├── base_spectrum.py     ← Agent 08 (NEW, metaclass 수정)
├── popup_spectrum.py    ← Agent 08
├── spectrum_analyzer.py ← Agent 08
├── popup_nmr.py         ← Agent 08
├── popup_uvvis.py       ← Agent 08
├── popup_molorbital.py  ← Agent 08
├── popup_md.py          ← Agent 08
├── spectrum_pdf_exporter.py ← Agent 08
├── phase_integration.py ← Agent 08 (NEW)
├── chem_data.py         ← 통합본 유지
├── (9 Agent 09 모듈)    ← 통합본 유지
├── (9 리소스 파일)      ← .png, .ico
├── (9 .chem 파일)       ← 샘플 데이터
├── build_chemgrid.py    ← 빌드 스크립트
├── test_integration.py  ← 통합 테스트
└── dist/ChemGrid.exe    ← 110.4 MB
```

---

### [2026-03-01 01:29] Phase 6-4 v4 통합 + exe 재빌드 완료

#### 병합 수행 내용
- `merge_phase64.py` 스크립트로 9개 에이전트 산출물을 `integrated/`에 병합
- Agent 01 (UI): draw.py +3258바이트, toolbar_setup.py +2769바이트 (v4: 툴바 2줄, 반응화살표+텍스트 버튼)
- Agent 02 (캔버스): canvas.py +11145바이트 (v4: +/- charge 분리, 반응화살표, 텍스트, user_lp, Undo/Redo 통합)
- Agent 05 (렌더링): renderer.py +2444바이트 (Phase 6-3: 공명구조 균등화, user_lp 전자구름 제외)
- Agent 06 (3D): popup_3d.py +2779바이트 (v4: 원자크기/CPK, 다중결합, PropertiesPanel 오류핸들링)

#### v4 주요 변경점
1. **툴바 2줄 분리** — `addToolBarBreak()` 사용, tb1(파일), tb2(그리기)
2. **Theory→3D 자동오픈 제거** — 3D 팝업은 오직 btn_3d 클릭으로만
3. **반응 화살표 + 텍스트 도구** — Arrow/Text 모드, 4방향 스냅, 아래첨자 변환
4. **+/- charge 분리** — atoms["charge"] 별도 필드, 위첨자 렌더링
5. **비공유전자쌍 user_lp** — 사용자 직접 LP 지정, 전자구름 제외
6. **공명구조 전자구름 균등화** — 고리 원자 전하 평균화
7. **3D 원자크기 확대** — ATOM_SCALE 0.35→0.85, CPK 색상 강화
8. **다중결합 3D 표현** — 이중: 2개 평행 실린더, 삼중: 3개 실린더
9. **PropertiesPanel 오류핸들링** — 오프라인/ORCA 미로드 안전 메시지

#### ChemDraw 잔존 처리
- coord_utils.py:3 "ChemDraw Pro" → "ChemGrid" (1건 수정)
- 최종 잔존 0건

#### PyInstaller 빌드
- **빌드 도구:** PyInstaller 6.19.0
- **환경:** Python 3.12.12 (Anaconda chemgrid), Windows 11
- **결과:** ChemGrid.exe 110.4 MB → c:\chemgrid\ChemGrid.exe 복사 완료

#### 주의사항
- `py` 명령어 사용 (python 아닌) — Windows Store alias 문제
- 좌표 정밀도: `round(coord, 2)` — 0.01 단위
- conda 환경: `C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python <script>`
- 인코딩: `open(file, encoding='utf-8')` 필수 (Windows cp949 방지)

### [2026-03-01 20:28] 사용자 관점 E2E 테스트 최종 완료
#### 테스트 개요
- `_user_verification_10.py` 스크립트를 사용하여 종합적인 UI 상호작용 검증
- 테스트 분자: Benzene, Nitrobenzene group, Cis-2-Butene, Norbornane, Cubane, Glyceraldehyde, Thiophene, Tropylium, Cyclopentadienyl, Ospirane
- 테스트 항목: 도구 클릭, 마우스 드래그/클릭, 마우스 휠 줌, 텍스트 입력, 화살표 생성, 레이어 전환(Drawing, Lewis, Theory)
#### 결과
- 통합 오류 없이 정상적으로 모든 검증 스크립트 실행 완료.
- 출력 이미지 정상 생성 확인 (`_veri_10_full_drawing.png`, `_veri_10_lewis.png`, `_veri_10_theory.png`, `_veri_10_theory_selected.png`).
- 런타임 Crash 없음. RDKit fallback 정상 작동 확인. E2E 검증 PASS.
