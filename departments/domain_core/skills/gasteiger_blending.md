# Skill: Gasteiger Blending Formula

## Rule
Partial atomic charges must use the blending formula:

```
final_charge = 0.6 * gasteiger_charge + 0.4 * custom_charge
```

- **60% Gasteiger** (RDKit `ComputeGasteigerCharges`)
- **40% Custom** (domain-specific corrections for electronegativity, resonance, etc.)

## Why
Pure Gasteiger charges underestimate charge separation in polar bonds and conjugated systems. The 40% custom component compensates for known Gasteiger limitations while preserving its empirically validated baseline.

## Where It Applies
- `analyzer.py` — charge computation pipeline
- `electron_density_analyzer.py` — ESP surface generation
- Any function that outputs partial charges for visualization or energy calculations

## Verification
For a C=O bond (e.g., formaldehyde):
- Gasteiger alone: O ~ -0.30
- Blended: O ~ -0.36 to -0.40 (closer to ab initio reference)
