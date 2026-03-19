# domain_synthesis Context Note
## Technical Decisions & Observations (2026-03-19)

### PDF Exporter Architecture
- `MechanismPDFExporter` uses reportlab for PDF generation + RDKit for 2D molecule rendering
- Snake (serpentine) layout: even rows L->R, odd rows R->L, with vertical dashed connectors
- Korean font: malgun.ttf (Windows) auto-registered at first use
- File sizes: 38-62KB for 1-3 step routes (well above 10KB threshold)

### Retrosynthesis Engine Behavior
- Phenol/Aniline return 0-step routes because they're in `building_blocks.py` DB (~120 entries)
- Complex molecules (Aspirin, Caffeine, Ibuprofen) successfully decompose via BFS + SMARTS matching
- Caffeine's 3-step route: triple N-methylation of xanthine core (C-N bond formation x3)
- Route scores can be negative (penalty-based scoring)

### Mechanism Engine Quality Tiers
1. **Gold standard** (hardcoded in reaction_mechanisms.py): SN2, SN1, E2, E1, etc. -- highest accuracy
2. **Auto-generated** (BondChangeDetector + ArrowGenerator): catches bond changes but may oversimplify multi-step mechanisms
3. Missing gold standards: EAS bromination, ester hydrolysis, aldol condensation

### ORCA Integration
- ORCA 6.1.1 detected at `C:\chemgrid\Orca.6.1.1\Orca6.1.1.Win64.exe`
- ArrowGenerator uses ORCA availability flag for Tier 1 quality arrows
- Not tested in this cascade (would require actual DFT calculations)

### RDKit Warnings (Expected)
- "non-ring atom 0 marked aromatic" -- appears during retrosynthesis SMARTS matching for aromatic disconnections. Harmless noise from some retro-transform SMARTS patterns that produce invalid intermediates.
- "product 1 has no mapped atoms" -- some SMARTS reaction patterns don't map all atoms. Expected in reverse direction.
