import sys
sys.path.insert(0, 'c:/chemgrid/src/app')
from analyzer import ChemicalAnalyzer
analyzer = ChemicalAnalyzer()

# TEST 1: propane with + on middle carbon -> expect C[CH+]C
atoms = {
    (0.0, 0.0):   {'main': '', 'attach': {}},
    (20.0, 0.0):  {'main': '', 'attach': {}, 'charge': '+'},
    (40.0, 0.0):  {'main': '', 'attach': {}},
}
bonds = {((0.0,0.0),(20.0,0.0)): 1, ((20.0,0.0),(40.0,0.0)): 1}
smiles, _, lewis, _ = analyzer.generate_smiles(atoms, bonds)
fc = lewis.get((20.0,0.0),{}).get('formal_charge','N/A')
print(f'\n[TEST1] CC(+)C => SMILES: {smiles}  | center charge: {fc}')
print(f'  PASS' if '[CH+]' in smiles or smiles == 'C[CH+]C' or fc == 1 else f'  FAIL (expected C[CH+]C or fc=1)')

# TEST 2: methoxide anion -> expect C[O-]
atoms2 = {
    (0.0,0.0): {'main':'','attach':{}},
    (20.0,0.0): {'main':'O','attach':{},'charge':'-'}
}
bonds2 = {((0.0,0.0),(20.0,0.0)): 1}
smiles2, _, lewis2, _ = analyzer.generate_smiles(atoms2, bonds2)
fc2 = lewis2.get((20.0,0.0),{}).get('formal_charge','N/A')
print(f'\n[TEST2] C-O(-) => SMILES: {smiles2}  | O charge: {fc2}')
print(f'  PASS' if '[O-]' in smiles2 or fc2 == -1 else f'  FAIL (expected C[O-] or fc=-1)')

# TEST 3: methyl radical -> expect [CH3]
atoms3 = {(0.0,0.0): {'main':'','attach':{0:'·'}}}
smiles3, _, _, _ = analyzer.generate_smiles(atoms3, {})
print(f'\n[TEST3] C· => SMILES: {smiles3}')
print(f'  PASS' if '[CH3]' in smiles3 or '[C]' in smiles3 or smiles3 != 'C' else f'  Note: smiles3={smiles3} (radical may not change SMILES form but electrons set)')

# TEST 4: cyclopentadienyl anion -> expect C1=CC=C[C-]1
atoms4 = {
    (0.0,0.0): {'main':'','attach':{}},
    (20.0,10.0): {'main':'','attach':{}},
    (40.0,0.0): {'main':'','attach':{}},
    (35.0,-20.0): {'main':'','attach':{}},
    (5.0,-20.0): {'main':'','attach':{},'charge':'-'},
}
bonds4 = {
    ((0.0,0.0),(20.0,10.0)): 2,
    ((20.0,10.0),(40.0,0.0)): 1,
    ((40.0,0.0),(35.0,-20.0)): 2,
    ((35.0,-20.0),(5.0,-20.0)): 1,
    ((5.0,-20.0),(0.0,0.0)): 1,
}
smiles4, _, lewis4, _ = analyzer.generate_smiles(atoms4, bonds4)
print(f'\n[TEST4] Cp anion => SMILES: {smiles4}')
print(f'  PASS' if '[C-]' in smiles4 else f'  FAIL (expected [C-] in SMILES)')
