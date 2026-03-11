import sys, warnings
sys.path.insert(0,'c:/chemgrid/src/app')
warnings.filterwarnings('ignore')
from rdkit import Chem; from rdkit.Chem import AllChem
from analyzer import ChemicalAnalyzer

def build_data(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if not mol: return None, None
    mol = Chem.RemoveHs(mol); AllChem.Compute2DCoords(mol)
    conf = mol.GetConformer()
    xs=[conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys=[conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    cx,cy=(max(xs)+min(xs))/2,(max(ys)+min(ys))/2
    s=26.7; cx_l,cy_l=200,200
    atoms={}; bonds={}; idx_to_key={}
    for i in range(mol.GetNumAtoms()):
        pos=conf.GetAtomPosition(i); a=mol.GetAtomWithIdx(i)
        sym='' if a.GetSymbol()=='C' else a.GetSymbol()
        key=(round(cx_l+(pos.x-cx)*s,2), round(cy_l-(pos.y-cy)*s,2))
        fc=a.GetFormalCharge()
        entry={'main':sym,'attach':{}}
        if fc!=0: entry['formal_charge']=fc; entry['charge']='+'if fc>0 else '-'
        atoms[key]=entry; idx_to_key[i]=key
    for b in mol.GetBonds():
        k1,k2=idx_to_key.get(b.GetBeginAtomIdx()),idx_to_key.get(b.GetEndAtomIdx())
        if k1 and k2:
            bt=b.GetBondTypeAsDouble(); order=1 if bt<1.5 else(2 if bt<2.5 else 3)
            bonds[(k1,k2)]=order
    return atoms,bonds

mols=[('Cp-','[cH-]1cccc1'),('Tropylium','C1=CC=CC=C[CH+]1'),('Benzene','c1ccccc1')]
an = ChemicalAnalyzer()
print("="*60)
print("SMILES 주입 전/후 ring 감지 비교")
print("="*60)
for name,smi in mols:
    atoms,bonds=build_data(smi)
    r_old=an.analyze(atoms,bonds)
    r_new=an.analyze(atoms,bonds,smiles=smi)
    
    aro_old=len(r_old.get('aromatic',set()) if r_old else [])
    ring_old=len(r_old.get('ring_atoms_all',set()) if r_old else [])
    aro_new=len(r_new.get('aromatic',set()) if r_new else [])
    ring_new=len(r_new.get('ring_atoms_all',set()) if r_new else [])
    charges_new=[round(v,3) for v in (r_new.get('charges',{}).values() if r_new else [])]
    
    diff = round(max(charges_new)-min(charges_new),4) if len(charges_new)>1 else 'N/A'
    status = "OK 균등" if isinstance(diff,float) and diff < 0.01 else "BAD 불균등"
    
    print(f"\n{name} ({smi}):")
    print(f"  BEFORE: aro={aro_old}  ring_all={ring_old}")
    print(f"  AFTER:  aro={aro_new}  ring_all={ring_new}  charges={charges_new}")
    print(f"  charge_diff={diff} -> {status}")
