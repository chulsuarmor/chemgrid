# domain_export Task List

## 2026-03-19
- [x] P0 FIX: Spectrum PDF export 1-page bug (popup_3d.py _export_pdf)
  - [x] Added _resolve_smiles() multi-source SMILES lookup
  - [x] Added Mass Spectrum (6th spectrum type) to export loop
  - [x] Fixed _smiles_cache not set when ORCA loaded
  - [x] Added PdfPages multi-page fallback
  - [x] Added Mass support to spectrum_pdf_exporter.py
  - [x] py_compile passed
  - [x] _source sync done
  - [x] Test: benzene PDF = 7 pages, 1.27 MB
