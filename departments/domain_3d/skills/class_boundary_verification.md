# Skill: Class Boundary Verification in Large Files

## When to Use
When adding or moving methods in `popup_3d.py` (7900+ lines, 15+ classes).

## Procedure
1. Run `grep -n '^class ' popup_3d.py` to list all class start lines.
2. The class a method belongs to is determined by which `class` line precedes it, NOT by visual proximity.
3. Before adding a method, confirm the target class line number and the NEXT class line number to know the valid range.
4. After adding, verify with: `hasattr(TargetClass, 'method_name')` in a quick Python check.

## Key Class Boundaries (as of 2026-03-19)
- `DockingEnergyPanel`: starts ~6326, ends before `_PubChemThread` ~7043
- `_PubChemThread`: starts ~7043
- `Molecule3DPopup`: starts ~7060, extends to EOF (~7936)

## Common Mistake
Adding methods meant for `Molecule3DPopup` at the end of `DockingEnergyPanel` because they appear close together in the file. Always check the class keyword line numbers.

## Orbital Rendering Pattern (MC Dot Density)
- ALL orbital lobes (sp/sp2/sp3/d/f) must use Monte Carlo rejection sampling, NOT gluSphere
- Reference: `AdvancedOrbitalRenderer._generate_mc_lobe_points()` and `PiOrbitalRenderer._generate_mc_points()`
- Cache pattern: `_mc_lobe_cache[cache_key]` where key = position+direction+scale+radius
- gluSphere is ONLY for non-orbital geometry: atom spheres (BallAndStickRenderer), VDW surfaces (ESP), indicators
- The `_lobe()` method is the single rendering entry point for ALL orbital types; changing it converts everything
