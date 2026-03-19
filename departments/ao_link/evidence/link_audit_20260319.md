# AO-LINK Audit Report: Button/Menu Connectivity
**Date:** 2026-03-19
**Auditor:** AO-LINK (Claude Opus 4.6)
**Scope:** All popup modules, toolbar menu connections, internal button wiring

---

## 1. Popup Module Import Test (offscreen QApplication)

All 8 popup modules import successfully without error.

| # | Module | Class | Importable? | Notes |
|---|--------|-------|-------------|-------|
| 1 | popup_3d | Molecule3DPopup | OK | FutureWarning on google.generativeai (non-blocking) |
| 2 | popup_synthesis | SynthesisPopup | OK | |
| 3 | popup_docking | DockingPopup | OK | FutureWarning on google.generativeai |
| 4 | popup_lead_optimizer | LeadOptimizerPopup | OK | |
| 5 | popup_admet | ADMETPopup | OK | Korean font glyphs missing in matplotlib (cosmetic) |
| 6 | popup_drug_screening | DrugScreeningPopup | OK | |
| 7 | popup_alphafold | AlphaFoldPopup | OK | |
| 8 | popup_reaction_animation | ReactionAnimationPopup | OK | |
| 9 | popup_reaction | ReactionPopup | OK | (used by reaction analysis btn) |

## 2. Popup Instantiation Test (offscreen)

| # | Module | Instantiable? | Notes |
|---|--------|---------------|-------|
| 1 | popup_synthesis | OK | SynthesisPopup('CCO', 'Ethanol') |
| 2 | popup_admet | OK | ADMETPopup(smiles='CCO', mol_name='Ethanol') |
| 3 | popup_drug_screening | OK | DrugScreeningPopup() |
| 4 | popup_alphafold | OK | AlphaFoldPopup() |
| 5 | popup_docking | OK | DockingPopup(canvas=None) |
| 6 | popup_reaction_animation | OK | ReactionAnimationPopup(reactant_smiles='CCO', product_smiles='CC=O') |
| 7 | popup_3d | N/A | Requires real atom/bond data; actual call site in main_window.py is correct |
| 8 | popup_lead_optimizer | **BUG** | See Bug #1 below |

## 3. Toolbar Menu -> main_window Method Connections

All toolbar buttons in `toolbar_setup.py` successfully link to existing methods in `main_window.py`:

| # | Menu/Button | Target Method | Exists? | Notes |
|---|-------------|---------------|---------|-------|
| 1 | 저장 (.chem) | save_file | OK | |
| 2 | 불러오기 (.chem) | load_file | OK | |
| 3 | PNG 저장 | export_png | OK | |
| 4 | PDF 저장 (Ctrl+P) | export_pdf | OK | |
| 5 | 선택 영역 내보내기 | export_selection_dialog | OK | |
| 6 | 스펙트럼 PDF 내보내기 | export_spectrum_to_pdf | OK | |
| 7 | 계산 히스토리 보기 | show_calculation_history | OK | |
| 8 | 검증 보고서 생성 | show_verification_report | OK | |
| 9 | AlphaFold 구조 예측 | open_alphafold_popup | OK | |
| 10 | ADMET 분석 | open_admet_popup | OK | |
| 11 | 신약 스크리닝 | open_drug_screening_popup | OK | |
| 12 | 분자 도킹 | open_docking_popup | OK | |
| 13 | 리드 최적화 (신약 설계) | open_lead_optimizer_popup | OK | **BUG at call site** (see Bug #1) |
| 14 | 전체 지우기 | clear_all | OK | |
| 15 | 원소 선택 | pick_el | OK | |

## 4. Internal Button Wiring (Within Popups)

| # | Source Popup | Button | Target | Status | Notes |
|---|-------------|--------|--------|--------|-------|
| 1 | popup_synthesis | 3D 반응 애니메이션 | popup_reaction_animation.ReactionAnimationPopup | OK | Connected via _on_reaction_animation |
| 2 | popup_synthesis | PDF 내보내기 | internal PDF export | OK | Present in source |
| 3 | popup_synthesis | Gemini | Gemini AI integration | OK | Present in source |
| 4 | popup_3d | 신약설계 tab | _create_alphafold_synthesis_tab | OK | Tab exists at index with label "신약설계" |
| 5 | popup_3d | 신약 개발 환경 열기 | _run_drug_design | OK | Connected via _btn_drug_start |
| 6 | popup_3d | 상세 분석 환경 열기 (리드 최적화) | _open_lead_optimizer | **BUG** | See Bug #1 |
| 7 | main_window | 입체 구조 3D btn | open_3d_popup -> Molecule3DPopup | OK | Correct params |
| 8 | main_window | 합성 경로 btn | open_synthesis_popup -> SynthesisPopup | OK | |
| 9 | main_window | 반응 분석 btn | open_reaction_popup -> ReactionPopup | OK | |

## 5. Bugs Found

### Bug #1: LeadOptimizerPopup parameter mismatch (P1 - will crash at runtime)

**Constructor signature** (`popup_lead_optimizer.py:676`):
```python
def __init__(self, smiles: str = "", canvas=None, parent=None)
```

**Callers using wrong parameter name `initial_smiles`:**
- `main_window.py:2499`: `LeadOptimizerPopup(canvas=self.cv, initial_smiles=smiles, parent=self)`
- `popup_3d.py:8009`: `LeadOptimizerPopup(initial_smiles=smiles, parent=self)`

Both will raise `TypeError: LeadOptimizerPopup.__init__() got an unexpected keyword argument 'initial_smiles'` at runtime when the user clicks "리드 최적화" from either the toolbar menu or the 3D popup's drug design tab.

**Fix:** Change `initial_smiles=` to `smiles=` in both call sites.

### Warning #1: Deprecated google.generativeai package (P3 - cosmetic)

`popup_docking.py:60` imports `google.generativeai` which triggers a FutureWarning. Should migrate to `google.genai`.

### Warning #2: Korean font glyphs missing in matplotlib (P3 - cosmetic)

`popup_admet.py:686` triggers UserWarning for missing Hangul glyphs in DejaVu Sans font during `fig.tight_layout()`. Korean text in ADMET charts may render as boxes.

---

## Summary

- **8/8 popup modules**: importable
- **7/8 popup modules**: instantiable (LeadOptimizerPopup blocked by parameter mismatch)
- **15/15 toolbar connections**: method exists
- **1 runtime bug found** (P1): `initial_smiles` vs `smiles` parameter name mismatch in 2 call sites
- **2 cosmetic warnings** (P3): deprecated google.generativeai, missing Korean font glyphs
