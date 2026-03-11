
import os
import sys
import logging
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import Draw

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('_pentane_verify.log', mode='w')
    ]
)
logger = logging.getLogger("PentaneVerify")

def verify_pentane_structure():
    logger.info("Starting Pentane Structure Verification...")
    
    # 1. Generate from SMILES
    smiles = "CCCCC"
    mol = Chem.MolFromSmiles(smiles)
    
    if not mol:
        logger.error("Failed to generate molecule from SMILES")
        return False
        
    logger.info(f"Molecule generated from SMILES: {smiles}")
    
    # 2. Add Hydrogens
    mol_h = Chem.AddHs(mol)
    num_atoms = mol_h.GetNumAtoms()
    logger.info(f"Number of atoms after adding Hs: {num_atoms}")
    
    # Expected: C5H12 -> 5 + 12 = 17 atoms
    if num_atoms != 17:
        logger.error(f"Incorrect atom count. Expected 17, got {num_atoms}")
        return False
    
    # Check individual atom counts
    c_count = len([a for a in mol_h.GetAtoms() if a.GetSymbol() == 'C'])
    h_count = len([a for a in mol_h.GetAtoms() if a.GetSymbol() == 'H'])
    
    logger.info(f"Carbon count: {c_count} (Expected: 5)")
    logger.info(f"Hydrogen count: {h_count} (Expected: 12)")
    
    if c_count != 5 or h_count != 12:
        logger.error("Atom composition mismatch")
        return False

    # 3. 2D Coordinate Generation & Image
    try:
        AllChem.Compute2DCoords(mol_h)
        img_path = "_pentane_structure.png"
        Draw.MolToFile(mol_h, img_path, size=(400, 300))
        logger.info(f"2D structure image saved to {img_path}")
    except Exception as e:
        logger.error(f"Failed to generate 2D image: {e}")
        return False

    # 4. 3D Conformer Generation (Stereochemistry/Stability Check)
    try:
        res = AllChem.EmbedMolecule(mol_h, randomSeed=42)
        if res == 0:
            logger.info("3D conformation generated successfully")
        else:
            logger.warning("3D conformation generation failed (return code not 0)")
            # Pentane is simple, so this should work.
    except Exception as e:
        logger.error(f"Error during 3D embedding: {e}")
        return False
        
    # 5. Isomer check (Chain vs Branched)
    # Pentane (n-pentane) should be a straight chain.
    # We can check connectivity or just rely on SMILES "CCCCC" which is n-pentane.
    # Branched isomers would be "CC(C)CC" (Isopentane) or "CC(C)(C)C" (Neopentane).
    
    # Verify it is n-pentane by checking degree of Carbon atoms
    # n-pentane: CH3-CH2-CH2-CH2-CH3
    # Degrees (excluding H): 1, 2, 2, 2, 1
    
    degrees = []
    for atom in mol.GetAtoms(): # Use mol without H for easier heavy atom degree check
        if atom.GetSymbol() == 'C':
            degrees.append(atom.GetDegree())
    
    degrees.sort()
    logger.info(f"Carbon atom degrees (sorted): {degrees}")
    
    if degrees == [1, 1, 2, 2, 2]:
        logger.info("Topology verification passed: Straight chain (n-pentane)")
    else:
        logger.error(f"Topology verification failed. Expected [1, 1, 2, 2, 2], got {degrees}")
        return False

    logger.info("Pentane verification completed successfully.")
    return True

if __name__ == "__main__":
    success = verify_pentane_structure()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
