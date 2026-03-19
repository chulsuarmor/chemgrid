# Skill: Mechanism Engine Testing

## Gold Standard vs Auto-Generated
- **Gold standard mechanisms** are in `reaction_mechanisms.py`. Use `mechanism_type_hint` parameter to access them.
- Known gold standards: `sn2`, `sn1`, `e2`, `e1` (check MECHANISMS dict for full list)
- Auto-generated mechanisms use BondChangeDetector + ArrowGenerator -- functional but may oversimplify multi-step reactions.

## Test Patterns
| Reaction | Reactants | Products | Hint | Expected |
|----------|-----------|----------|------|----------|
| SN2 | CCBr.[OH-] | CCO.[Br-] | sn2 | 1 step, 2 arrows |
| EAS | c1ccccc1.BrBr | Brc1ccccc1 | (none) | auto-gen, 1-2 steps |
| Ester hydrolysis | aspirin.O | salicylic acid.AcOH | (none) | auto-gen, 1-2 steps |

## Known Issues
- `[HBr]` is not valid SMILES (should be `Br` for HBr). Don't include it in product SMILES.
- EAS bromination has no gold standard -- auto-generates as concerted (educational oversimplification)
- Ester hydrolysis has no gold standard -- misses tetrahedral intermediate

## MechanismEngine API
```python
engine = MechanismEngine()
mech = engine.generate_mechanism(
    reactant_smiles="CCBr.[OH-]",
    product_smiles="CCO.[Br-]",
    mechanism_type_hint="sn2"  # optional
)
# Returns MechanismData with .steps (list of MechanismStep)
# Each step has .arrows (list of ArrowData)
```
