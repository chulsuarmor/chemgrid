import ast
import sys

files = [
    r"c:\chemgrid\_source\draw.py",
    r"c:\chemgrid\_source\analyzer.py",
    r"c:\chemgrid\_source\renderer.py",
    r"c:\chemgrid\_source\layer_logic.py",
    r"c:\chemgrid\_source\chem_data.py",
    r"c:\chemgrid\_source\coord_utils.py",
    r"c:\chemgrid\_source\popup_3d.py",
    r"c:\chemgrid\_source\orca_interface.py",
]

for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            ast.parse(fh.read())
        print(f"[OK] {f.split(chr(92))[-1]}")
    except Exception as e:
        print(f"[FAIL] {f.split(chr(92))[-1]}: {e}")

print("\nTrying actual import of draw.py modules...")
sys.path.insert(0, r"c:\chemgrid\_source")
try:
    import chem_data
    print("[OK] chem_data imported")
except Exception as e:
    print(f"[FAIL] chem_data: {e}")

try:
    from rdkit import Chem
    mol = Chem.MolFromSmiles("CCO")
    print(f"[OK] RDKit SMILES test: CCO -> {Chem.MolToSmiles(mol)}")
except Exception as e:
    print(f"[FAIL] RDKit: {e}")
