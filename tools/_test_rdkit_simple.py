import sys
print("Checking Python environment...")
print(f"Python: {sys.version}")

try:
    print("Importing rdkit...")
    import rdkit
    print(f"RDKit: {rdkit.__version__}")
    
    from rdkit import Chem
    print("Importing rdkit.Chem successful")
    
    from rdkit.Chem import Draw
    print("Importing rdkit.Chem.Draw successful")
    
    mol = Chem.MolFromSmiles('C')
    print("Created MolFromSmiles")
    
    img = Draw.MolToImage(mol)
    print("Generated Image")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("Check Complete")
