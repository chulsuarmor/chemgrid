# DryLab Report Mistakes (14 entries)
> 3 P0 incidents (empty report passed, wrong purpose, missing docking). Key lesson: auto-score 100/100 is worthless.
> Manual audit of every page required. DryLab = theory -> derivative -> organic synthesis experiment.
> See: CLAUDE.md Rule E, docs/ai/skills/audit_pipeline.md
> LAST_M_NUMBER: M1368 (2026-05-18, spectrum_graph_fallback_banner)

---

## [2026-05-18] M1368 — DryLab PDF 빈 페이지 (Raman/EI-MS) — DATA PENDING 배너 누락
- **Situation:** 5종 분자 conference PDF 감사 결과: pages 7 (Raman) + 9 (EI-MS/Mass) = 10 words only (사실상 빈 페이지). 섹션 제목 + 축 라벨만 존재.
- **Mistake:** `_add_spectrum_with_interpretation`에서 `png_bytes=None` (그래프 생성 실패) 시 기존 fallback이 단순 영어 텍스트 1줄만 출력. Rule GG(SIMULATION_MODE 배너 의무) 위반.
- **Root cause:** 폴백 메시지가 `s["blank_hint"]` 스타일(흰 배경, 연한 텍스트)이라 fitz로 extract 시 사실상 빈 페이지로 보임. 학생이 DATA PENDING 임을 명시적으로 확인 불가.
- **Fix (M1368, K3 surgical):**
  - `_add_spectrum_with_interpretation` else 분기 교체: 노랑(#FFCC00)/빨강테두리(#E53935) Table 배너 삽입.
  - "[DATA PENDING] {spec_type} 스펙트럼 그래프 이미지 생성 실패 (SIMULATION MODE — 실험 측정값 아님)" + logger.warning 발화 (Rule M).
  - reportlab 미설치 fallback: 텍스트 1줄 (기존 패턴 보존).
  - 신규 섹션/MO/분자 추가 없음 (Rule K3 strict).
- **Verification:** py_compile PASS, _source/ sync PASS (diff -q: 크기 일치).
- **체화 4단계 (Rule H):**
  - H-1: 이 항목 (왜 실패: GG 배너 없는 빈 텍스트 폴백)
  - H-2: skills/drylab_review.md 기존 §7 금지사항에 "그래프 PNG None → 반드시 GG 배너, 텍스트 폴백 금지" 추가
  - H-3: patrol SC106 기존 패턴 — 탐지 불가 (스타일 내용은 runtime 확인 필요)
  - H-4: Rule GG 보강 ("스펙트럼 PNG None 시 DATA PENDING 배너" 사례 추가)

---

## [2026-04-27] M573 — DryLab 도킹 통합 + SIMULATION_MODE 배너 (격분 #27 fix)
- **Situation:** 사용자 격분 (2026-03-20T16:23): "도킹 시뮬레이션이 실행되지 않았어. 기준 분자의 도킹 데이터가 없어 정량적 비교는 수행할 수 없으나 이런 문구가 있는데 감사팀은 어떻게 통과한 거야?"
- **Mistake (격분 #27):** DryLab Part 2 수용체 도킹에서 docking_score=0이면 "정량적 비교 수행 불가" 문구 출력 → 학생이 보고서에 사용 못함.
- **Mistake (격분 #10):** 수용체가 어디 있는 뭔지/기능/역할 안 알려줘서 학생이 이해 못함.
- **Mistake (격분 #9):** 결합 부위 잔기 명시 없음.
- **Mistake (FP-15):** SIMULATION_MODE 시 PDF에 배너 없음 → 학생이 휴리스틱 추정값을 실험값으로 오인.
- **Fix (M573):**
  1. `drylab_report_exporter.py` 191~215: `from docking_interface import SIMULATION_MODE, VINA_AVAILABLE` 추가
  2. `_make_simulation_banner()` 신규 메서드 — 노랑(#FFCC00)/빨강(#7A0000)/빨강 테두리(#E53935) 배너 + PDBe Mol* 외부 링크 (R-21 Sehnal 2021)
  3. `_sec_part2_receptor_docking()` Part 2 시작 시점에 `extend(self._make_simulation_banner(s))` 호출
  4. `_generate_docking_interpretation()` 강화:
     - 수용체 자동 설명 (rec_name + rec_organism + rec_func + rec_disease) — 격분 #10 fix
     - SIMULATION_MODE 시 "(휴리스틱 추정값, HEURISTIC ESTIMATE — Not Vina)" 라벨 — FP-15
     - 5종 ligand 도킹 결과 평균 비교 자동 설명 — 격분 #27
     - 결합 부위 잔기 자동 설명 (binding_site_residues 5건) — 격분 #9
     - 도킹 결과 0건 시 silent return 금지, "정량적 해석 제공할 수 없다" 명시 — Rule M
  5. `tools/generate_drylab_5mol_M573.py` 신규 — 5종 분자 (epinephrine/aspirin/aniline/benzene/caffeine) PDF 자동 생성
- **Verification:**
  - 5/5 PDFs (456-494 KB, 21 pages each) generated under `docs/reports/drylab_5mol_M573/`
  - 5/5 DOCX (40 KB) generated (M469 패리티)
  - PDF text validation: docking=True, receptor=True, heuristic=True (5/5)
  - aspirin Part 2 Page 10 sample text:
    - "표적 수용체 Epidermal Growth Factor Receptor (EGFR) (Homo sapiens 유래)는 수용체 타이로신 키나아제..."
    - "기준 분자의 결합 에너지는 -6.57 kcal/mol로 측정되었다. (휴리스틱 추정값, HEURISTIC ESTIMATE — Not Vina)"
    - "이는 중등도 이상의 결합 친화력을 나타내며, 약물 후보로서의 가능성을 시사한다"
    - "결합 부위는 Leu718, Val726, Ala743, Lys745, Met793 등의 잔기로 구성되며..."
- **체화 4단계 (Rule H):**
  - H-1 (사유 기록): mistakes/drylab.md M573 entry — "DryLab 도킹 silent failure + SIMULATION_MODE 배너 부재 + 수용체 자동 설명 누락"
  - H-2 (skills 패턴): docs/ai/skills/drylab_docking.md 신규 — 5요소 의무 (수용체/기준도킹/유도체비교/AI설명/SIMULATION 배너)
  - H-3 (patrol/AV 권고): patrol SC58 권고 — `_make_simulation_banner` 함수 존재 + 5요소 검증
  - H-4 (CLAUDE.md): Rule E 강화 권고 — DryLab Part 2 5요소 의무
- **재발 방지:**
  - SIMULATION_MODE False여도 코드 경로는 항상 활성 (조건 분기로 배너만 숨김)
  - PDBe Mol* 외부 링크는 SIMULATION 시 자동 표시
  - 5종 분자 정기 PDF 생성 자동화 (학회 시연용)

---

---

## [2026-03-27] drylab_report_exporter: 3D docking screenshot silent failure
- **Mistake:** Docking3DViewerWidget.grab() fails headless/offscreen, caught by except with logger.debug + return None
- **Fix:** logger.warning + matplotlib 3D fallback renderer (ETKDG 3D + Axes3D CPK ball-and-stick)

---

## [2026-03-27] polymer_lead_report_exporter: no reusable helper for spectra sections
- **Mistake:** Copy-paste spectra code for Part 1 and Part 4 instead of shared helper
- **Fix:** `_add_full_spectra_section(elements, smiles, prefix)` class method. DRY principle.

---

## [2026-03-27] polymer_lead_report_exporter [Table N] "Empty Table" debugging order
- **Lesson:** Table bug suspected -> generate actual PDF -> fitz page text extraction -> confirm data presence. Don't fix code before confirming the bug exists.

---

## [2026-03-20] Spectrum PDF 1 page - _smiles_cache not set (80th request)
- **Root causes:** (1) _smiles_cache not set in ORCA path (2) Mass Spectrum loop missing (3) except:pass
- **Fix:** _resolve_smiles() 3-source fallback + MS added + logger.warning()
- **Lesson:** 80 repeated requests because except:pass swallowed errors. Never use pass.

---

## [2026-03-14] PDF export - single spectrum only
- **Mistake:** SpectrumPDFExporter import fails, fallback saves only current figure
- **Fix:** matplotlib PdfPages for 6-page PDF (structure + IR/Raman/NMR_H/NMR_C13/UV-Vis)

---

## [2026-03-20] P0: CT bypassed audit and delivered DryLab report directly
- **Mistake:** DryLabReportReviewer 100/100 PASS -> CT sent to user. Audit team skipped entirely.
- **Result:** User: "everything from spectra to experiment steps is broken"
- **Fix:** CLAUDE.md Rule 0: Worker -> MM QA -> audit team manual review -> CT -> user

---

## [2026-03-20] P0: Audit team passed empty report as Grade A
- **Mistake:** Audit checked "section exists" not "content quality". Placeholders counted as content.
- **Fix:** "placeholder text = auto FAIL". Computed results must have AI interpretation filled in.

---

## [2026-03-20] P0: DryLab report purpose fundamentally misunderstood
- **User intent:** Theory analysis -> purpose-based derivative design -> organic synthesis experiment
- **What was built:** Molecular info listing + blanks + 3-line experiment
- **Key gaps:** Spectra from ChemGrid popups (not separate), receptor+docking first, student reasoning for derivative selection, textbook-level experiment (dozens of reagents/steps)

---

## [2026-03-21] P0: DryLab docking simulation not executed
- **Mistake:** TNT report says "no docking data for base molecule" because docking_score=0 passed
- **Fix:** Exporter must auto-run docking simulation internally (preset receptor + empirical scoring)

---

## [2026-03-21] P1: Reaction mechanism images not included
- **Mistake:** Experiment steps exist but no curved-arrow/straight-arrow mechanism diagrams
- **Fix:** Insert mechanism_pdf_exporter reaction scheme images into DryLab Part 5

---

## [2026-03-21] P2: Image aspect ratio distorted
- **Cause:** reportlab Image width-only without preserveAspectRatio
- **Fix:** Always use preserveAspectRatio=True or calculate height from aspect ratio

---

## [2026-03-27] except:pass 262 instances codebase-wide
- **Situation:** Antivirus organic check + manual scan found 262 cases in 34 files
- **Top offenders:** drylab_report_exporter(95), mechanism_rule_engine(34), popup_3d(28)
- **Fix:** All except:pass -> logger.warning("context: %s", e). ImportError/ValueError -> debug level

---

### [2026-04-25] M469 — DOCX 콘텐츠 패리티 부족 + RDKit 2D 단독 = 학계 미수용
- **Situation:** DryLab PDF에 PDBe Mol* 단백질-리간드 PNG 있었으나 DOCX에는 이미지 없음. RDKit 2D 구조만 보조로만 표시. 학생 Word 수정용 파일에 학술 시각화 부재.
- **C1 실수:** `_export_docx()`가 `_sec_part2e_alphafold_docking()` PDF 섹션의 이미지를 복사하지 않음. PDF용 `RLImage` 추가 시 DOCX `doc.add_picture()` 동시 추가 누락.
- **C2 실수:** PDBe Mol* URL만 텍스트로 표시 — 실제 PNG 렌더링(mplot3d fallback)이 PDF/DOCX 모두 없었음.
- **올바른 방법:**
  1. `molstar_capture.py` 신규 — `build_molstar_panel_images()` (mplot3d fallback + QR code)
  2. PDF `_sec_part2e`: `RLImage(molstar_png)` + `RLImage(qr_png)` 삽입
  3. DOCX `_export_docx()` Part 2-E: `doc.add_picture(molstar_png)` + `doc.add_picture(qr_png)` 동시 삽입
  4. `main_window.py`: 파일 다이얼로그에 `.docx` 필터 추가 + 결과 메시지에 DOCX 경로 표시
  5. `patrol G7-SC29`: DOCX `add_picture` + `build_molstar_panel_images` 자동 검사 (WARN 비차단)
- **체화 4단계:**
  - H-1: PDF 이미지 추가 → DOCX 이미지 누락 = "PDF 수정 시 DOCX 동시 수정 의무" 패턴
  - H-2: `docs/ai/skills/drylab_word_export.md` 신규 — DOCX 패리티 + py3Dmol 패턴
  - H-3: `patrol G7-SC29` 신설 — `doc.add_picture` + `build_molstar_panel_images` 미존재 탐지
  - H-4: (CLAUDE.md Rule E 강화 필요 — CT 결정 대기)
- **재발 방지:** SC29 자동 탐지, `_sec_part2e` 수정 시 `_export_docx` Part 2-E 동시 수정 의무화
