# 📦 Agent 09: Data Export & PDF Generation Plan

## Current Objective
Update `spectrum_pdf_exporter.py` to fix visualization errors identified in PDF analysis report.

## Tasks
- [x] **Phase 1: Chemical Structure Integrity**
    - [x] Replace placeholder "Bolt" image with RDKit-generated skeletal structure.
    - [x] Enforce valid SMILES usage for test data.
    - [x] Implement atom-to-peak label mapping visualization.
- [x] **Phase 2: UV-Vis Dual-View Layout**
    - [x] Switch from Inset to Side-by-Side Subplots (Linear vs Log scale).
    - [x] Relocate Energy Diagram to avoid overlap.
- [x] **Phase 3: NMR Visualization Improvements**
    - [x] Implement true stepwise integral (cumulative sum).
    - [x] Fix data clipping by adjusting Y-axis limits or using secondary axis.
    - [x] Relocate Zoom Inset to safe zone (10.0 ~ 8.5 ppm).
    - [x] Correct spelling: "Alipnetic" -> "Aliphatic".
- [x] **Phase 4: IR/Raman Visibility**
    - [x] Fix overlapping labels on IR top axis (Wavelength).
    - [x] Enhance Raman stick bar visibility (zorder, opacity).

## Technical Notes
- **UV-Vis:** Use `plt.subplots(1, 2)` for dual view.
- **NMR:** Integral line should use `drawstyle='steps-post'` and be scaled properly within plot area.
- **IR:** Use `MaxNLocator` with fewer bins for top axis.
