# domain_reaction_anim Technical Notes

## 2026-03-19: Initial Build Notes

### Architecture
- `reaction_animation_engine.py` is pure computation (no Qt dependency)
- `popup_reaction_animation.py` is pure UI (imports engine)
- Integration via `popup_synthesis.py` button click

### Key Design Choices
1. **MCS over reaction SMARTS**: Using rdFMCS for atom mapping is more general-purpose than reaction SMARTS templates. Works for any arbitrary reactant/product pair.
2. **Transition zone 0.30-0.70**: Bond changes concentrated in the middle 40% of frames, giving visual time for reactant/product states.
3. **Chair flip uses hardcoded geometry**: RDKit MMFF cannot produce correct boat intermediate from SMILES alone. Idealized hexagonal coords with z-offset used instead.
4. **SN2 Walden inversion**: Decompose substituent vectors into attack-axis (parallel) and perpendicular components. Only the parallel component flips sign.
5. **Energy profiles**: Simple parabolic for most reactions. Chair flip uses sin() for dual-peak (two transition states through boat).

### CPK Colors
- Duplicated from popup_3d.py as integer RGB (not float). This avoids import dependency on popup_3d which is a large file.

### Dependencies
- RDKit (required): Chem, AllChem, rdFMCS, rdMolAlign
- numpy (required): coordinate math
- matplotlib (optional): energy diagram
- PyQt6 (required): popup UI
