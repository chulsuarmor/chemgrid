"""ChemGrid 검증 도구 — SMILES 입력 → RDKit/PubChem 대조"""
import sys
from rdkit import Chem
from rdkit.Chem import Descriptors, AllChem, Draw, rdMolDescriptors
import requests
import json

def verify_smiles(smiles):
    print(f"\n{'='*60}")
    print(f"SMILES: {smiles}")
    print(f"{'='*60}")
    
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print("[ERROR] Invalid SMILES!")
        return
    
    # RDKit 기본 속성
    print("\n--- RDKit 계산값 (신뢰도 ★★★★★) ---")
    print(f"  분자식: {rdMolDescriptors.CalcMolFormula(mol)}")
    print(f"  분자량: {Descriptors.MolWt(mol):.4f} g/mol")
    print(f"  LogP:   {Descriptors.MolLogP(mol):.4f}")
    print(f"  TPSA:   {Descriptors.TPSA(mol):.2f} A^2")
    print(f"  H-bond donors:    {Descriptors.NumHDonors(mol)}")
    print(f"  H-bond acceptors: {Descriptors.NumHAcceptors(mol)}")
    print(f"  Rotatable bonds:  {Descriptors.NumRotatableBonds(mol)}")
    print(f"  Ring count:       {Descriptors.RingCount(mol)}")
    print(f"  Canonical SMILES: {Chem.MolToSmiles(mol)}")
    
    # 3D 좌표 생성 테스트
    mol3d = Chem.AddHs(mol)
    res = AllChem.EmbedMolecule(mol3d, AllChem.ETKDGv3())
    if res == 0:
        AllChem.MMFFOptimizeMolecule(mol3d)
        conf = mol3d.GetConformer()
        print(f"\n--- 3D 좌표 (ETKDGv3 + MMFF) ---")
        for i, atom in enumerate(mol3d.GetAtoms()):
            pos = conf.GetAtomPosition(i)
            print(f"  {atom.GetSymbol():>2} {i:3d}: ({pos.x:8.4f}, {pos.y:8.4f}, {pos.z:8.4f})")
    else:
        print("  [WARN] 3D embedding failed")
    
    # PubChem API 조회
    print(f"\n--- PubChem DB (신뢰도 ★★★★★) ---")
    try:
        canonical = Chem.MolToSmiles(mol)
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{canonical}/property/IUPACName,MolecularFormula,MolecularWeight,XLogP,ExactMass/JSON"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            props = data["PropertyTable"]["Properties"][0]
            print(f"  IUPAC Name: {props.get('IUPACName', 'N/A')}")
            print(f"  Formula:    {props.get('MolecularFormula', 'N/A')}")
            print(f"  MW:         {props.get('MolecularWeight', 'N/A')}")
            print(f"  XLogP:      {props.get('XLogP', 'N/A')}")
            print(f"  Exact Mass: {props.get('ExactMass', 'N/A')}")
        else:
            print(f"  PubChem API error: {resp.status_code}")
    except Exception as e:
        print(f"  PubChem lookup failed: {e}")
    
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        verify_smiles(sys.argv[1])
    else:
        # 기본 테스트 분자 5종
        test_molecules = [
            ("CCO", "에탄올"),
            ("CC(=O)O", "아세트산"),
            ("c1ccccc1", "벤젠"),
            ("CC(=O)Oc1ccccc1C(=O)O", "아스피린"),
            ("O=C(O)CC(O)(CC(=O)O)C(=O)O", "구연산"),
        ]
        for smiles, name in test_molecules:
            print(f"\n>>> {name}")
            verify_smiles(smiles)
