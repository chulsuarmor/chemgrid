"""
RDKit benzene 변환 로직 순수 단위 테스트 (GUI 없음)
"""
import sys

print("=== [1] RDKit 가용 여부 ===")
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    print("  RDKit: ✅ OK")
except ImportError as e:
    print(f"  RDKit: ❌ {e}")
    sys.exit(1)

print()
print("=== [2] benzene SMILES -> atoms/bonds 변환 ===")
smiles = "c1ccccc1"
mol = Chem.MolFromSmiles(smiles)
mol = Chem.RemoveHs(mol)
AllChem.Compute2DCoords(mol)
conf = mol.GetConformer()

atoms_result = {}
scale = 55.0
cx_canvas, cy_canvas = 675.0, 425.0

xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
cx_mol = (max(xs)+min(xs))/2
cy_mol = (max(ys)+min(ys))/2

idx_to_key = {}
for i in range(mol.GetNumAtoms()):
    pos = conf.GetAtomPosition(i)
    sym = mol.GetAtomWithIdx(i).GetSymbol()
    cx = cx_canvas + (pos.x - cx_mol)*scale
    cy = cy_canvas - (pos.y - cy_mol)*scale
    snap = 30
    cx = round(cx/snap)*snap
    cy = round(cy/snap)*snap
    key = (float(cx), float(cy))
    while key in atoms_result:
        key = (key[0]+5.0, key[1])
    atoms_result[key] = {"main": sym, "attach": {}}   # ← 수정된 코드
    idx_to_key[i] = key

bonds_result = {}
for bond in mol.GetBonds():
    i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
    k1, k2 = idx_to_key.get(i), idx_to_key.get(j)
    if k1 and k2:
        bt = bond.GetBondTypeAsDouble()
        order = 1 if bt < 1.5 else (2 if bt < 2.5 else 3)
        bonds_result[(k1, k2)] = order

print(f"  atoms: {len(atoms_result)} (예상: 6) {'✅' if len(atoms_result)==6 else '❌'}")
print(f"  bonds: {len(bonds_result)} (예상: 6) {'✅' if len(bonds_result)==6 else '❌'}")

all_have_attach = all('attach' in v for v in atoms_result.values())
print(f"  attach 키 검사: {'✅ 모든 원자 OK' if all_have_attach else '❌ attach 키 누락!'}")

for k, v in atoms_result.items():
    print(f"    {v['main']} @ {k}")

print()
print("=== [3] aspirin 테스트 ===")
smiles2 = "CC(=O)Oc1ccccc1C(=O)O"
mol2 = Chem.MolFromSmiles(smiles2)
mol2 = Chem.RemoveHs(mol2)
AllChem.Compute2DCoords(mol2)
print(f"  aspirin: {mol2.GetNumAtoms()} atoms, {mol2.GetNumBonds()} bonds {'✅' if mol2.GetNumAtoms() > 0 else '❌'}")

print()
print("=== 테스트 완료 ===")
