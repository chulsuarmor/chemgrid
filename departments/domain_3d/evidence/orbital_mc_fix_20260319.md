# Evidence: Orbital MC Dot Density Fix
## Date: 2026-03-19
## Worker: domain_3d

---

## Problem
AdvancedOrbitalRenderer._lobe() used gluSphere to draw orbital lobes as solid prolate spheroids.
This produced shiny teardrop/wedge shapes for sp/sp2/sp3/sp3d/sp3d2/d/f orbitals.
PiOrbitalRenderer already used Monte Carlo dot density for p-orbital lobes, creating visual inconsistency.

## Root Cause
_lobe() at line ~2607 used:
- glScalef(0.55, 0.55, scale_z) to stretch a sphere into a prolate spheroid
- gluSphere(sq, radius, 32, 24) to render as a solid surface

This single method was the rendering endpoint for ALL orbital types via callers:
_sp(), _sp2(), _sp3(), _sp3d(), _sp3d2(), _render_d(), _render_f()

## Fix Applied

### 1. Added `_generate_mc_lobe_points()` method (line ~2610)
- Monte Carlo rejection sampling within prolate spheroid bounds
- Wavefunction: psi(r,theta) proportional to r*cos(theta)*exp(-zeta*r)
- Density: |psi|^2 = r^2 * cos^2(theta) * exp(-2*zeta*r)
- Slater exponent zeta=2.2 (carbon 2p approximation)
- Local coordinate system built from lobe direction vector
- Points cached by position+direction+scale+radius key

### 2. Replaced `_lobe()` method (line ~2697)
- Removed: glPushMatrix/glTranslatef/glRotatef/glScalef/gluSphere/glPopMatrix
- Added: Cache lookup, GL_POINTS rendering with per-lobe color
- Point count scales with lobe size: 400 * max(1.0, scale_z/1.5)
- Point size: 2.5 (matching PiOrbitalRenderer style)

### 3. Added class-level cache
- `_mc_lobe_cache: Dict = {}` on AdvancedOrbitalRenderer class

## gluSphere calls remaining in popup_3d.py (non-orbital, correct):
- Line 1475: BallAndStickRenderer - atom spheres
- Line 1669: SpaceFillingRenderer - atom spheres
- Line 2299: ESP surface VDW spheres
- Line 2835: _draw_hyb_indicator - small colored marker dot
- Lines 3631/3649/3796: Molecule3DViewer binding site visualization

## Verification
- py_compile: PASS
- _source/ sync: DONE
- test_visual_auto.py: Environment dependency error (ModuleNotFoundError: ui_utils), unrelated to this change

## Files Modified
- `src/app/popup_3d.py` (AdvancedOrbitalRenderer class)
- `_source/popup_3d.py` (backup sync)
