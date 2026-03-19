# domain_3d Mistakes Log

## [2026-03-19] P0: AlphaFold/Drug-design methods defined in wrong class
- **Situation:** `_create_alphafold_synthesis_tab()` and 5 related methods (`_run_drug_design`, `_open_lead_optimizer`, `_open_alphafold`, `_open_synthesis`, `_open_admet`) were defined inside `DockingEnergyPanel` (line ~7025) but called from `Molecule3DPopup._init_ui()` (line ~7537).
- **Error:** `AttributeError: 'Molecule3DPopup' object has no attribute '_create_alphafold_synthesis_tab'`
- **Root Cause:** During a prior code addition, the new methods were appended to the end of `DockingEnergyPanel` instead of `Molecule3DPopup`. Since both classes are in the same file and `DockingEnergyPanel` appears first, the methods were accidentally placed in the wrong class scope.
- **Fix:** Moved all 6 methods from `DockingEnergyPanel` to `Molecule3DPopup` (before `closeEvent`).
- **Prevention:** When adding methods to a large multi-class file, always verify the target class by checking `class ClassName` line numbers and ensuring the new method's indentation falls within the correct class boundary. Use `grep -n 'class '` to map all class boundaries first.

## [2026-03-19] P1: gluSphere used for orbital lobes instead of MC dots
- **Situation:** AdvancedOrbitalRenderer._lobe() used gluSphere to draw orbital lobes as solid prolate spheroids, appearing as shiny wedge/teardrop shapes inconsistent with PiOrbitalRenderer which uses Monte Carlo dot density.
- **Error:** Visual inconsistency between pi orbital mode (MC dots) and hybrid/d/f orbital modes (solid gluSphere lobes). Solid shapes look unphysical for orbital visualization.
- **Root Cause:** Original implementation used gluSphere with glScalef for performance/simplicity, but this creates opaque geometric shapes rather than electron cloud density representations.
- **Fix:** Replaced _lobe() with MC rejection sampling approach: _generate_mc_lobe_points() creates points within a prolate spheroid using |psi|^2 density, rendered via GL_POINTS. Cache by position+direction+params. Single _lobe() method change covers all callers (sp/sp2/sp3/sp3d/sp3d2/d/f).
- **Prevention:** Orbital lobes should always use dot density (MC rejection sampling) for physically meaningful visualization. Only non-orbital geometry (atom spheres, VDW surfaces, indicators) should use gluSphere.

## [2026-03-19] P1: popup_3d.py — "진동 영역 확대" 버튼 제거
- **Situation:** btn_zoom_to ("진동 영역 확대") 버튼이 UI에 표시되었으나 카메라 포지셔닝이 불안정하여 사용자에게 혼란 유발
- **Fix:** 버튼 생성 코드를 제거하고 _zoom_to_vibrating_atoms 메서드는 dead code로 유지 (향후 개선 시 복원 가능)
