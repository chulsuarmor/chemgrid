# domain_reaction_anim Task List

## Initial Build (2026-03-19)
- [x] Create reaction_animation_engine.py (BondChange, ReactionTrajectory, ReactionAnimationEngine)
- [x] Implement generate_frames() - MCS generic interpolation
- [x] Implement generate_sn2_animation() - backside attack + Walden inversion
- [x] Implement generate_proton_transfer() - acid-base H transfer
- [x] Implement generate_chair_flip() - chair -> boat -> chair
- [x] Create popup_reaction_animation.py (ReactionAnimationPopup, _Viewer3DWidget, _EnergyDiagramWidget)
- [x] Modify popup_synthesis.py - add animation button + _on_reaction_animation()
- [x] py_compile all files
- [x] Copy to _source/
- [x] Write evidence

## Future Tasks
- [ ] ORCA IRC/NEB trajectory parsing (Phase 2)
- [ ] OpenGL 3D rendering upgrade
- [ ] Electron pushing curved arrows overlay
- [ ] GUI screenshot verification
