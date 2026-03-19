# Evidence: domain_reaction_anim Initial Build
## Date: 2026-03-19

## Files Created
1. **src/app/reaction_animation_engine.py** (~530 lines)
   - `BondChange` dataclass: frame_start/end, atom_i/j, change_type
   - `ReactionTrajectory` dataclass: frames, symbols, bonds_per_frame, energies, bond_changes, labels
   - `ReactionAnimationEngine` class with 4 animation generators:
     - `generate_frames()`: MCS-based generic reaction interpolation
     - `generate_sn2_animation()`: SN2 backside attack + Walden inversion
     - `generate_proton_transfer()`: acid-base H transfer
     - `generate_chair_flip()`: cyclohexane chair -> boat -> chair
   - Helper functions: ease-in-out interpolation, parabolic energy, MCS atom mapping

2. **src/app/popup_reaction_animation.py** (~470 lines)
   - `ReactionAnimationPopup(QDialog)`: main popup (1000x700, dark theme #1a1a2e)
   - `_Viewer3DWidget`: QPainter 2.5D atom/bond rendering
     - CPK colors, radial gradients, depth sorting
     - Partial bonds as dashed lines, forming=green, breaking=red
     - Mouse rotation/pan/zoom
   - `_EnergyDiagramWidget`: matplotlib energy profile with real-time frame marker
   - Playback: play/pause, reset, frame slider, speed (0.25x-4x)
   - Reaction type selector (generic / SN2 / proton transfer / chair flip)
   - Korean labels throughout

## Files Modified
3. **src/app/popup_synthesis.py**
   - Added "3D 반응 애니메이션" button (blue, #1565C0) after PDF export button
   - Button enabled when a synthesis step is clicked in flowchart
   - `_on_reaction_animation()` method: opens `ReactionAnimationPopup` with step's reactant/product SMILES
   - Added `_selected_step_idx` tracking

## Verification
- py_compile: All 3 files pass (reaction_animation_engine.py, popup_reaction_animation.py, popup_synthesis.py)
- All files copied to `_source/` backup

## Design Decisions
- Used MCS (Maximum Common Substructure) for atom mapping rather than SMARTS-based reaction mapping -- more robust for arbitrary SMILES pairs
- Bond transition zone: t=0.30~0.70 (configurable via TRANSITION_START/END)
- Energy profile: simple parabolic for generic reactions; dual-peak for chair flip
- Chair flip uses idealized cyclohexane geometry rather than RDKit embedding for correct conformational path
- SN2 Walden inversion: projection onto attack axis, perpendicular components preserved
