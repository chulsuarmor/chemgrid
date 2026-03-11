
import sys
import os
import json
import logging
import subprocess
from pathlib import Path
from rdkit import Chem

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Verifier")

EXPECTED_SMILES = {
    "Ammonia": "N",
    "Ethanol": "CCO",
    "Pentane": "CCCCC",
    "Phenol": "Oc1ccccc1",
    "S-Lactic Acid": "C[C@H](O)C(=O)O"
}

def verify_molecule(name, expected_smiles):
    logger.info(f"Verifying {name}...")
    
    # Run interactive test
    cmd = [sys.executable, "_interactive_verification.py", name]
    logger.info(f"Running command: {' '.join(cmd)}")
    try:
        # Run with timeout to prevent hanging
        subprocess.run(cmd, timeout=30) 
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout while verifying {name}")
        return False
    except Exception as e:
        logger.error(f"Error executing interactive test: {e}")
        return False
        
    # Check result
    result_file = "_interactive_test_result.json"
    if not os.path.exists(result_file):
        logger.error("Result file not found")
        return False
        
    with open(result_file, "r") as f:
        data = json.load(f)
        generated_smiles = data.get("smiles", "")
        
    logger.info(f"Expected: {expected_smiles}")
    logger.info(f"Got: {generated_smiles}")
    
    # Simple canonical check
    try:
        can_expected = Chem.CanonSmiles(expected_smiles)
        can_generated = Chem.CanonSmiles(generated_smiles)
        
        if can_expected == can_generated:
            logger.info(f"[PASS] {name} verification successful!")
            return True
        else:
            logger.error(f"[FAIL] {name} verification failed. Mismatch.")
            return False
    except Exception as e:
        logger.error(f"SMILES parsing error: {e}")
        # Fallback to string comparison if RDKit fails or strict match
        if expected_smiles == generated_smiles:
            logger.info(f"[PASS] {name} verification successful (Exact String Match)!")
            return True
        return False

def main():
    results = {}
    # Run Ethanol ONLY
    molecules_to_test = ["Ethanol"] 
    
    for mol in molecules_to_test:
        expected = EXPECTED_SMILES.get(mol)
        success = verify_molecule(mol, expected)
        results[mol] = success
        
    logger.info("Verification Summary:")
    for mol, res in results.items():
        logger.info(f"{mol}: {'PASS' if res else 'FAIL'}")

if __name__ == "__main__":
    main()
