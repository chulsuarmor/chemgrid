# domain_3d Task Checklist

## 2026-03-19: Orbital MC Dot Density Conversion
- [x] Analyze all gluSphere calls in AdvancedOrbitalRenderer
- [x] Identify _lobe() as single rendering endpoint for all orbital types
- [x] Implement _generate_mc_lobe_points() with |psi|^2 rejection sampling
- [x] Replace _lobe() gluSphere rendering with GL_POINTS MC dots
- [x] Add _mc_lobe_cache for position+direction based caching
- [x] Verify non-orbital gluSphere calls preserved (atoms, ESP, indicators)
- [x] py_compile PASS
- [x] Copy to _source/
- [ ] GUI screenshot verification (blocked: test env dependency issue)
- [x] Evidence written: evidence/orbital_mc_fix_20260319.md
- [x] mistakes.md updated
- [x] skills/ updated
