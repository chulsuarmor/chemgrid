# Skill: Carbon Empty String Rule

## Rule
Carbon atoms are stored as `''` (empty string) in the internal data structure, **NOT** as `"C"`.

## Why
The drawing/parsing pipeline uses empty string to represent carbon (the default/implicit atom in organic chemistry notation). Using `"C"` will cause element lookup failures, incorrect rendering, and broken SMILES conversion.

## Pattern
```python
# CORRECT
atom_symbol = ''  # This is carbon

# WRONG - DO NOT USE
atom_symbol = 'C'  # This will break parsing
```

## Where It Applies
- `analyzer.py` — molecule analysis and atom identification
- `chem_data.py` — element data lookups
- `engine_physics.py` — bond length/angle calculations
- Any code that reads or writes atom symbols from the canvas
