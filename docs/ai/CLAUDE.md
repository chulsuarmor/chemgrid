# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ChemDraw Pro** is a quantum chemistry visualization and analysis application built with Python and PyQt6. It enables users to draw molecular structures, perform DFT calculations using ORCA, and analyze spectroscopic properties (IR, NMR, UV-Vis, Raman). The application validates molecular structures against theoretical literature values using B3LYP/6-31G(d) DFT methods.

**Primary Language:** Python 3.x with PyQt6 GUI framework

**Target Platform:** Windows (executables built with PyInstaller)

## Build and Run Commands

### Build Executable
```bash
# Build ChemDraw.exe from source
build_chemdraw.bat

# Or use Python directly
python _source/build_exe.py
```

The build process uses PyInstaller with `ChemDraw.spec`. The executable is created in `dist/` and copied to the root directory.

### Run Application
```bash
# Run from source
python _source/draw.py

# Run built executable
ChemDraw.exe
```

### Testing
```bash
# Run validation tests
run_validator.bat

# Run general tests
run_test.bat

# Run progress tracker
run_progress.bat
```

### Molecule Validation
```bash
# Validate molecules against theoretical values
python _source/molecule_validator.py

# Simple validation
python _source/validate_molecules.py
```

## Architecture Overview

### Core Application Structure

The application follows a modular phase-based architecture with clear separation of concerns:

**Main Application (`_source/draw.py`)**
- PyQt6-based GUI with multi-layer rendering system
- Integrates all phase modules via conditional imports
- Canvas handles drawing, bonds, atoms, and user interactions
- Three visualization layers: Base (2D structure), Lewis (electron distribution), Theory (optimized geometry)

**Chemical Analysis Pipeline**
1. **Structure Input** → User draws 2D molecular structure on canvas
2. **Parsing** → `analyzer.py` extracts atoms, bonds, creates adjacency graph
3. **Analysis** → Conjugation detection, charge calculation, aromatic system identification
4. **SMILES Generation** → RDKit integration for molecular representation
5. **DFT Calculation** → ORCA interface for quantum calculations (optional)
6. **Visualization** → Multiple rendering modes (2D, 3D, spectroscopy)

### Core Engine Modules

**`engine_core.py`** - Conjugation and π-system analysis
- Detects conjugated π-systems and aromatic rings
- Hückel's rule validation (4n+2 electrons)
- Molecular island discovery (disconnected components)

**`engine_physics.py`** - Inductive effects
- Electronegativity-based charge distribution
- Substituent effects on π-systems

**`engine_resonance.py`** - Resonance structure analysis
- Resonance contributor enumeration
- Charge delocalization modeling

**`analyzer.py`** - Chemical structure analysis orchestrator
- Integrates all three engines
- RDKit SMILES generation and validation
- Stereochemistry detection (R/S labels)
- Generates Lewis structure data (hydrogen counts, lone pairs)
- Generates Theory layer data (optimized coordinates)

### ORCA Integration

**`orca_interface.py`** - DFT calculation interface
- Creates ORCA input files with B3LYP/6-31G(d) template
- Executes ORCA calculations in background QThread
- Parses output files for:
  - Mulliken and Löwdin population analysis
  - Electronic density from .gbw binary files
  - Optimized molecular geometry
  - Bond orders (Mayer analysis)
- **ORCA Path:** `C:\Users\김남헌\Desktop\organicdraw\Orca.6.1.1\Orca6.1.1.Win64.exe`
- **Critical:** Column validation in parser prevents coordinate hijacking

### Spectroscopy Modules

**`spectrum_analyzer.py`** - IR/Raman spectrum analysis
- Parses ORCA vibrational frequency output
- Calculates Lorentzian-broadened spectra
- matplotlib integration for visualization

**`popup_nmr.py`** - NMR spectrum viewer
- ¹H and ¹³C NMR visualization
- Chemical shift prediction

**`popup_uvvis.py`** - UV-Vis spectrum viewer
- Electronic transitions (TD-DFT)
- Absorption spectrum plotting

**`popup_md.py`** - Molecular dynamics viewer
- Trajectory visualization

**`popup_molorbital.py`** - Molecular orbital viewer
- HOMO/LUMO visualization
- Orbital energy diagrams

**`popup_3d.py`** - 3D molecule viewer
- Interactive 3D structure display
- Ball-and-stick models

### Phase Integration System

**`phase_integration.py`** - Coordinates all phase modules
- `Phase2ESPCalculationManager` - Electrostatic potential calculations
- `Phase3DPopupManager` - 3D visualization window management
- `Phase4IUPACLabelManager` - IUPAC naming integration
- Handles graceful degradation if phase modules unavailable

### Advanced Features (Phase 4)

**`molecule_comparator.py`** - Molecular similarity comparison
- Structural similarity metrics
- Property comparison

**`history_manager.py`** - Calculation history tracking
- Logs all DFT calculations
- Result caching

**`batch_processor.py`** - Batch calculation management
- Multiple molecule processing
- Queue management with status tracking

### Rendering System

**`renderer.py`** - Multi-layer rendering engine
- `CloudRenderer` - Electronic cloud visualization (ESP coloring)
- Base layer rendering (2D structure)

**`layer_logic.py`** - Layer-specific rendering
- `LewisRenderer` - Draws formal charges, lone pairs, hydrogen counts
- `TheoryRenderer` - Draws optimized geometry from DFT

### Export and Reporting

**`export_manager_enhanced.py`** - Export functionality
- Save molecular structures
- Export calculations

**`spectrum_pdf_exporter.py`** - PDF report generation
- Spectrum plots
- Calculation summaries

**`calculation_logger.py`** - Calculation logging
- Structured logging of DFT runs
- Error tracking

**`verification_report.py`** - Validation reports
- Comparison against literature values

### Utilities

**`coord_utils.py`** - Coordinate transformation utilities
- 2D/3D conversions
- Rotation matrices

**`error_handler.py`** - Error handling framework
- User-friendly error messages
- Recovery strategies

**`progress_tracker.py`** - Progress tracking UI
- Long-running calculation feedback

**`smiles_validator.py`** - SMILES validation
- RDKit integration
- Molecular formula verification

**`iupac_analyzer.py`** - IUPAC nomenclature
- Systematic naming (requires Phase D module)

**`chem_data.py`** - Chemical data tables
- `ELEMENT_DATA` - Periodic table data (electronegativity, radii, colors)
- `VISUAL_SETTINGS` - Rendering constants

## Key Technical Details

### Coordinate System
- All coordinates are normalized to 2 decimal places: `(round(x, 2), round(y, 2))`
- Atom matching uses 8-pixel distance threshold for robustness
- QPointF conversion: `pt_key = (round(pt.x(), 2), round(pt.y(), 2))` for point objects

### Charge Calculation Model
- **Inductive effects** applied first (base layer)
- **Resonance effects** added as deltas (additive model)
- **Substituent vector effects** modulate π-system charges (75% pull force)
- Total charge must be conserved across molecule

### ORCA Calculation Workflow
1. Generate 3D coordinates from 2D structure
2. Create ORCA input file with B3LYP/6-31G(d) template
3. Execute ORCA in background thread (QThread)
4. Parse .out file for Mulliken charges (3-column validation)
5. Parse .out file for optimized geometry (5-column validation)
6. Parse .gbw binary for electronic density
7. Validate total charge matches expected value
8. Display results in Theory layer and/or popup windows

### Module Import Pattern
All phase modules use conditional imports with availability flags:
```python
try:
    from phase_module import FeatureClass
    FEATURE_AVAILABLE = True
except ImportError:
    FEATURE_AVAILABLE = False
    print("[draw.py] phase_module not available")
```

This allows graceful degradation if optional dependencies are missing.

### File Format (.chem)
- Custom JSON-based format for saving molecular structures
- Stores atoms, bonds, coordinates, and metadata
- Examples: `_source/1.chem` through `_source/8.chem`

## Working with the Codebase

### Adding New Spectroscopy Features
1. Create new popup module following pattern: `popup_newfeature.py`
2. Implement data parsing from ORCA output
3. Create PyQt6 viewer widget
4. Add conditional import to `draw.py`
5. Add menu action to trigger popup

### Modifying DFT Calculations
- Edit `DFT_TEMPLATE` in `orca_interface.py` for different methods/basis sets
- Current method: B3LYP/6-31G(d) with TightSCF convergence
- Ensure output parser regex patterns match new ORCA output format

### Testing Molecular Analysis
- Use existing .chem files in `_source/` as test cases
- Validate against known theoretical values in `MOLECULE_VALIDATION_REPORT.md`
- Target accuracy: >95% agreement with literature

### Debugging DFT Issues
1. Check ORCA executable path in `orca_interface.py`
2. Verify ORCA input file creation in temp directory
3. Examine .out file for convergence errors
4. Check column validation in parser (strict 3-col Mulliken, 5-col geometry)
5. Verify total charge conservation

## Dependencies

### Required Python Packages
```
PyQt6          # GUI framework
rdkit          # Molecular structure, SMILES
numpy          # Numerical operations
matplotlib     # Spectrum plotting
reportlab      # PDF generation
Pillow         # Image processing
pyinstaller    # Executable building
svgwrite       # SVG export
```

Install with: `pip install -r requirements_advanced.txt`

### External Software
- **ORCA 6.1.1** - Quantum chemistry calculations
  - Located at: `Orca.6.1.1/Orca6.1.1.Win64.exe`
  - Download from: https://orcaforum.kofo.mpg.de/

## Common Development Pitfalls

### Coordinate Matching Issues
**Problem:** Atoms not found when matching coordinates between layers.
**Solution:** Use distance-based matching (8px threshold) instead of exact key matching. Normalize all coordinates to 2 decimal places.

### ORCA Parser Fails
**Problem:** Parser reads wrong data (coordinates in Mulliken section).
**Solution:** Enforce strict column count validation (`line.split()` length check) and immediate section exit on keywords like "FINAL GEOMETRY" or "LÖWDIN".

### Charge Conservation Violations
**Problem:** Total molecular charge drifts from expected value.
**Solution:** Validate total charge after all analysis steps. Use additive resonance model, not overwriting charges.

### PyInstaller Build Fails
**Problem:** Missing modules or data files in executable.
**Solution:** Check `ChemDraw.spec` for hiddenimports and datas. Add missing modules explicitly.

### Phase Module Import Errors
**Problem:** Application crashes when optional modules unavailable.
**Solution:** All phase imports must be wrapped in try/except with availability flags. Use flags before calling phase features.

## Validation Process

The application has been validated against 10 complex molecules with 99.4% average accuracy:
- Norbornane, Cyclohexane, Benzo[a]pyrene, ATP, Allicin, Cholesterol, Hemin, Caffeine, Aspartame, Naphthalene
- Validation methodology documented in `METHODOLOGY.md`
- Detailed results in `MOLECULE_VALIDATION_REPORT.md`
- Target: >95% agreement with literature DFT values

## Project Documentation

Key documentation files:
- `README.md` - Project overview, quick start, results summary
- `METHODOLOGY.md` - Computational chemistry procedures, DFT parameters
- `SPECTROSCOPY_REFERENCE.md` - IR/NMR/UV-Vis interpretation guide
- `TECHNICAL_SPECIFICATIONS.md` - System requirements, ORCA configuration
- Various status reports (`*_REPORT.md`, `*_SUMMARY.md`) - Implementation tracking

## Notes for Future Development

- All source code is in `_source/` directory
- Main application entry point: `_source/draw.py`
- Build scripts and executables in root directory
- ORCA software in `Orca.6.1.1/` subdirectory
- Test molecules stored as `_source/*.chem` files
- Memory and auto-memory system in `memory/` directory (if present)
