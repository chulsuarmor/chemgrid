# domain_export Mistakes Log

## [2026-03-19] P0: Spectrum PDF export produces 1 page instead of 6
- **Situation**: User clicks "PDF 저장" in SpectrumPanel tab of 3D popup
- **Root causes found (3)**:
  1. `_smiles_cache` was never set on SpectrumPanel when ORCA data was loaded (only set in non-ORCA path). Without SMILES, `spectra_data = {}` and fallback to single-page `figure.savefig()`.
  2. Mass Spectrum ("MS") was missing from the spectrum generation loop — only 5 types were generated, not 6.
  3. `except Exception: pass` silently swallowed all errors during spectrum data collection, making failures invisible.
- **Fix applied**:
  1. Added `_resolve_smiles()` helper that searches multiple sources: `_smiles_cache` > parent popup `mol_data.smiles` > parent popup `_current_smiles`.
  2. In `Molecule3DPopup._load_data()`, always set `tab_spectrum._smiles_cache = smiles` regardless of ORCA presence.
  3. Added "MS"/"Mass" to the spectrum loop (now 6 types: IR, Raman, NMR_1H, NMR_13C, UV-Vis, Mass).
  4. Replaced `except: pass` with `except Exception as e: logger.warning(...)`.
  5. Added matplotlib PdfPages multi-page fallback if SpectrumPDFExporter import fails.
  6. Added Mass Spectrum support to `spectrum_pdf_exporter.py` (spectra_types list + stem plot in generate_spectrum_graph).
- **Files modified**: `src/app/popup_3d.py`, `agents/09_data_export/spectrum_pdf_exporter.py`
- **Test result**: Benzene PDF = 7 pages (1 title + 6 spectra), 1.27 MB
