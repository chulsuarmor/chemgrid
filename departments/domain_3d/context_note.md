# domain_3d Technical Notes

## 2026-03-19: MC Dot Density Design Decisions

### Why _lobe() is the single conversion point
All orbital types (sp/sp2/sp3/sp3d/sp3d2/d/f) call `_lobe(sq, pos, direction, scale_z, radius, color)`.
By converting this one method, all 7+ orbital rendering paths are converted simultaneously.
No need to touch _sp(), _sp2(), _sp3(), _render_d(), _render_f() individually.

### MC sampling parameters
- Slater exponent zeta=2.2 (slightly less than PiOrbitalRenderer's 2.5 for broader lobes)
- Prolate spheroid bounds: r_xy = radius*0.55, r_z = radius*scale_z*0.5
- Point count: 400 * max(1.0, scale_z/1.5) - larger lobes get more points
- Point size: 2.5 (consistent with PiOrbitalRenderer)

### Cache strategy
- Key: position (2 decimal) + direction (3 decimal) + scale_z + radius
- Class-level dict (shared across instances within same session)
- No cache invalidation needed (orbital positions don't change during render)

### gluSphere calls intentionally kept
- Atom spheres (BallAndStickRenderer, SpaceFillingRenderer): physical atoms, not orbitals
- ESP VDW surface: electrostatic potential mapping on VDW radius spheres
- Hybridization indicator: tiny colored dot above atom (UI marker)
- Binding site spheres: docking visualization geometry
