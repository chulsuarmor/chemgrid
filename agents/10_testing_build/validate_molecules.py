#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
from datetime import datetime
from pathlib import Path

# Direct molecule database
MOLECULES = {
    1: {"name": "Norbornane", "formula": "C7H12", "smiles": "C1CC2CCC1C2"},
    2: {"name": "Cyclohexane", "formula": "C6H12", "smiles": "C1CCCCC1"},
    3: {"name": "Benzo[a]pyrene", "formula": "C20H12", "smiles": "c1cc2c(cc1)ccc1c2cc3ccccc3c1"},
    4: {"name": "ATP", "formula": "C10H16N5O13P3", "smiles": "Nc1ncnc2n(cnc12)[C@@H]1O[C@H](COP(=O)(O)OP(=O)(O)OP(O)(O)=O)[C@H](O)[C@H]1O"},
    5: {"name": "Allicin", "formula": "C6H10OS2", "smiles": "C=CCS(=O)SCC=C"},
    6: {"name": "Cholesterol", "formula": "C27H46O", "smiles": "CC(C)CCCC(C)C1CCC2C1(CCCC2=CC=C3CC(CCC3=C)O)C"},
    7: {"name": "Hemin", "formula": "C35H33ClFeN4O4", "smiles": "CC(=C)c1c(C)c2c(c(C)c1[N-]2)C(=C)C3=C(C(=C4C(=C(c5c(C)c([N-]4)C(c6n5C(=C(C(=O)O)C)C(c7c(C)c([N-]6)C(=C(C)C)C)=CC)=C)C(=O)OC)C)C)C)[Fe]C(Cl)C(=O)O"},
    8: {"name": "Caffeine", "formula": "C8H10N4O2", "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"},
    9: {"name": "Aspartame", "formula": "C14H18N2O5", "smiles": "CC(=O)N[C@@H](Cc1ccccc1)[C@@H](=O)N[C@@H](CC(=O)O)C(=O)OC"},
    10: {"name": "Naphthalene", "formula": "C10H8", "smiles": "c1ccc2ccccc2c1"},
}

report = """# ChemDraw Pro - Complex Molecule Spectrum Validation Report

## Project Information
- **Workspace:** C:\\Users\\김남헌\\Desktop\\organicdraw
- **Generated:** {}
- **Task:** 10 Complex Molecules DFT Validation
- **Method:** B3LYP/6-31G(d)
- **Target Accuracy:** >95%

## Validation Summary

""".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S KST'))

report += "| # | Molecule | Formula | Status | Notes |\n"
report += "|---|----------|---------|--------|-------|\n"

for num in range(1, 11):
    mol = MOLECULES[num]
    report += f"| {num} | {mol['name']} | {mol['formula']} | INITIALIZED | SMILES: {mol['smiles'][:30]}... |\n"

report += "\n---\n\n## Detailed Validation (Molecule by Molecule)\n\n"

# Add detailed sections
for num in range(1, 11):
    mol = MOLECULES[num]
    report += f"""## Molecule {num}: {mol['name']} ({mol['formula']})

### Basic Information
- **SMILES:** {mol['smiles']}
- **Status:** ⏳ Validation Pending
- **Phase:** Molecular Formula Verification

### Expected Properties
- **Molecular Formula:** {mol['formula']}
- **Computational Method:** B3LYP/6-31G(d)
- **Target Properties:** Energy, HOMO-LUMO, Dipole, Spectra

### Progress
- [x] SMILES Defined
- [ ] DFT Calculation
- [ ] Spectrum Analysis
- [ ] Error Calculation
- [ ] Literature Comparison

**Status Message:** Awaiting DFT calculation and spectroscopic analysis...

---

"""

# Write report
output_path = Path("VALIDATION_REPORT.md")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(report)

print(f"✓ Report created: {output_path}")
print(f"✓ {len(MOLECULES)} molecules initialized")
print("Status: Working - DFT calculations pending")
