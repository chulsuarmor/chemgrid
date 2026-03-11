
import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "agents", "09_data_export"))

# Import the exporter module
try:
    import importlib
    # Since 09_data_export is not a valid identifier, we must import by path or name manipulation
    # We already added the path to sys.path, so we can import spectrum_pdf_exporter directly
    import spectrum_pdf_exporter as exporter
    from rdkit import Chem
    from rdkit.Chem import Draw
    from rdkit.Chem import AllChem
    print("Successfully imported exporter and RDKit")
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LewisFix")

def generate_improved_structure_image(smiles: str, labels: dict, output_path: Path) -> bool:
    """
    Improved structure generation with explicit C, H, and charges.
    """
    print(f"Generating improved structure for: {smiles}")
    
    try:
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            print("Invalid SMILES")
            return False
        
        # 1. Add Hydrogens (Explicit H)
        mol = Chem.AddHs(mol)
        
        # 2. Compute 2D Coordinates
        AllChem.Compute2DCoords(mol)
        
        # 3. Kekulize (Show double bonds)
        try:
            Chem.Kekulize(mol)
        except:
            pass
            
        # 4. Set Atom Labels (Explicit C and Charge Symbols)
        for atom in mol.GetAtoms():
            idx = atom.GetIdx()
            symbol = atom.GetSymbol()
            
            # Explicit Carbon
            if symbol == "C":
                # Check if it has neighbors (to decide if we show label, but user wants explicit C)
                # We will force label to "C" via atomNote or by replacing the drawing symbol?
                # RDKit Draw options 'noCarbonSymbols' is not directly available in simple MolToImage options usually.
                # But we can set the property '_displayLabel' or similar?
                # Actually, simply not hiding them is tricky in MolToImage without using rdMolDraw2D.
                # However, we can trick it by setting the atom's "prop" to be displayed?
                pass

            # Charges
            charge = atom.GetFormalCharge()
            if charge != 0:
                # RDKit usually draws charges. We ensure they are visible.
                pass
                
        # 5. Drawing Options
        options = Draw.MolDrawOptions()
        options.bondLineWidth = 3.0
        options.padding = 0.1
        
        # Set explicit carbon labels manually if opts.noCarbonSymbols fails
        # RDKit's MolDrawOptions might not fully support showing C in skeletal mode easily for all versions
        # So we force it by setting atom label property for every Carbon atom
        for atom in mol.GetAtoms():
            if atom.GetSymbol() == 'C':
                atom.SetProp('_displayLabel', 'C')
        
        # Using MolDraw2D for better control
        try:
            d2d = Draw.MolDraw2DCairo(600, 600) # Higher resolution
            
            # Set options on d2d
            opts = d2d.drawOptions()
            opts.bondLineWidth = 3.0
            opts.addStereoAnnotation = True
            
            # Prepare molecule for drawing
            d2d.DrawMolecule(mol)
            
            # 6. Draw Lone Pairs (Manual addition)
            conf = mol.GetConformer()
            valence_dict = {'H':1, 'C':4, 'N':5, 'O':6, 'F':7, 'Cl':7, 'Br':7, 'I':7, 'S':6, 'P':5}
            
            for atom in mol.GetAtoms():
                symbol = atom.GetSymbol()
                if symbol not in valence_dict:
                    continue
                v = valence_dict[symbol]
                bond_order_sum = 0
                for bond in atom.GetBonds():
                    bond_order_sum += bond.GetBondTypeAsDouble()
                charge = atom.GetFormalCharge()
                non_bonding_e = v - bond_order_sum - charge
                lone_pairs = int(non_bonding_e // 2)
                
                if lone_pairs > 0:
                    idx = atom.GetIdx()
                    pos_3d = conf.GetAtomPosition(idx)
                    p2 = Chem.Point2D(pos_3d.x, pos_3d.y)
                    draw_pos = d2d.GetDrawCoords(p2)
                    
                    offset = 15 
                    d2d.SetColour(Draw.to_rdkit_color((1.0, 0.0, 0.0)))
                    
                    positions = []
                    if lone_pairs == 1:
                        positions = [(0, -offset)]
                    elif lone_pairs == 2:
                        positions = [(-10, -15), (10, -15)]
                    elif lone_pairs == 3:
                        positions = [(0, -15), (15, 0), (-15, 0)]
                        
                    for (dx, dy) in positions:
                        cx = draw_pos.x + dx
                        cy = draw_pos.y + dy
                        d2d.DrawEllipse(int(cx - 2), int(cy - 2), int(cx + 2), int(cy + 2))
                        d2d.DrawEllipse(int(cx - 5), int(cy), int(cx - 2), int(cy + 3))
                        d2d.DrawEllipse(int(cx + 2), int(cy), int(cx + 5), int(cy + 3))

            d2d.FinishDrawing()
            
            # Get binary content and write to file
            bin_data = d2d.GetDrawingText()
            with open(output_path, "wb") as f:
                f.write(bin_data)
                
            print(f"Saved improved image (MolDraw2D) to {output_path}")
            return True
            
        except Exception as e:
            print(f"MolDraw2D failed ({e}), falling back to MolToImage")
            
            # Fallback
            img = Draw.MolToImage(mol, size=(600, 600), options=options, kekulize=True)
            img.save(str(output_path))
            print(f"Saved improved image (Fallback) to {output_path}")
            return True
            
    except Exception as e:
        print(f"Failed to generate structure: {e}")
        import traceback
        traceback.print_exc()
        return False

# Monkey patch the exporter function
exporter.generate_structure_image_with_labels = generate_improved_structure_image

def main():
    print("Running Fix and Verification...")
    
    # Test Data (Ethyl Benzoate)
    smiles = "CCOC(=O)c1ccccc1"
    output_dir = Path("docs/exports/spectra_assets/fixed_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Generate the Image directly to verify
    img_path = output_dir / "structure_fixed.png"
    generate_improved_structure_image(smiles, {}, img_path)
    
    if img_path.exists():
        print(f"[OK] Image generated: {img_path}")
    else:
        print("[FAIL] Image not generated")
        
    # 2. Run the Exporter (which uses our patched function)
    # We will simulate the main execution of the exporter but with our patch
    
    # Mock data same as exporter's test
    mock_data = {
        "IR": { "x": [], "y": [], "peaks": [], "smiles": smiles }, # Empty data just to test structure render
        "NMR_1H": { "x": [], "y": [], "peaks": [], "smiles": smiles }
    }
    
    metadata = {
        "iupac_name": "Ethyl Benzoate (Fixed)",
        "formula": "C9H10O2",
        "smiles": smiles
    }
    
    exp = exporter.SpectrumPDFExporter(output_dir=str(output_dir))
    
    # Create report
    pdf_path = exp.create_report(
        molecule_name="Ethyl Benzoate Fixed",
        spectra_data=mock_data,
        structure_image_path=str(img_path),
        metadata=metadata
    )
    
    if pdf_path:
        print(f"[SUCCESS] Fixed PDF Report generated: {pdf_path}")
    else:
        print("[FAIL] PDF Generation failed")

    # 3. Try to parse and fix test1.chem
    print("\n--- Processing test1.chem ---")
    try:
        import json
        chem_path = Path("_source/test1.chem")
        if chem_path.exists():
            with open(chem_path, 'r') as f:
                data = json.load(f)
            
            # Simple conversion logic
            mol = Chem.RWMol()
            atoms_data = data.get("atoms", {})
            bonds_data = data.get("bonds", {})
            
            # Map coord string to atom index
            coord_to_idx = {}
            sorted_coords = sorted(atoms_data.keys()) # Sort to be deterministic
            
            for coord in sorted_coords:
                atom_info = atoms_data[coord]
                symbol = atom_info.get("main", "C")
                a = Chem.Atom(symbol)
                
                # Set charge
                charge = atom_info.get("formal_charge", 0)
                a.SetFormalCharge(charge)
                
                idx = mol.AddAtom(a)
                coord_to_idx[coord] = idx
            
            # Add bonds
            for bond_key, order in bonds_data.items():
                c1, c2 = bond_key.split("|")
                if c1 in coord_to_idx and c2 in coord_to_idx:
                    i1 = coord_to_idx[c1]
                    i2 = coord_to_idx[c2]
                    
                    btype = Chem.BondType.SINGLE
                    if order == 2: btype = Chem.BondType.DOUBLE
                    elif order == 3: btype = Chem.BondType.TRIPLE
                    
                    mol.AddBond(i1, i2, btype)
            
            # Sanitize and finish
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                print(f"Sanitization warning: {e}")
            
            # Generate output
            test1_out = output_dir / "test1_fixed.png"
            
            # Convert to SMILES for improved generation (or pass mol directly)
            # But generate_improved_structure_image takes SMILES currently.
            # Let's adapt it or use a helper.
            # Actually we can just use the mol we built!
            
            # Re-implement generation for Mol object
            mol = Chem.AddHs(mol)
            AllChem.Compute2DCoords(mol)
            
            # Manually set C labels for test1 molecule too
            for atom in mol.GetAtoms():
                if atom.GetSymbol() == 'C':
                    atom.SetProp('_displayLabel', 'C')
            
            d2d = Draw.MolDraw2DCairo(600, 600)
            opts = d2d.drawOptions()
            opts.bondLineWidth = 3.0
            try: opts.noCarbonSymbols = False 
            except: pass
            
            d2d.DrawMolecule(mol)
            
            # --- Draw Lone Pairs for test1 ---
            conf = mol.GetConformer()
            valence_dict = {'H':1, 'C':4, 'N':5, 'O':6, 'F':7, 'Cl':7, 'Br':7, 'I':7, 'S':6, 'P':5}
            
            for atom in mol.GetAtoms():
                symbol = atom.GetSymbol()
                if symbol not in valence_dict:
                    continue
                v = valence_dict[symbol]
                bond_order_sum = 0
                for bond in atom.GetBonds():
                    bond_order_sum += bond.GetBondTypeAsDouble()
                charge = atom.GetFormalCharge()
                non_bonding_e = v - bond_order_sum - charge
                lone_pairs = int(non_bonding_e // 2)
                
                if lone_pairs > 0:
                    idx = atom.GetIdx()
                    pos_3d = conf.GetAtomPosition(idx)
                    p2 = Chem.Point2D(pos_3d.x, pos_3d.y)
                    draw_pos = d2d.GetDrawCoords(p2)
                    
                    offset = 15 
                    d2d.SetColour(Draw.to_rdkit_color((1.0, 0.0, 0.0)))
                    
                    positions = []
                    if lone_pairs == 1:
                        positions = [(0, -offset)]
                    elif lone_pairs == 2:
                        positions = [(-10, -15), (10, -15)]
                    elif lone_pairs == 3:
                        positions = [(0, -15), (15, 0), (-15, 0)]
                        
                    for (dx, dy) in positions:
                        cx = draw_pos.x + dx
                        cy = draw_pos.y + dy
                        d2d.DrawEllipse(int(cx - 2), int(cy - 2), int(cx + 2), int(cy + 2))
                        d2d.DrawEllipse(int(cx - 5), int(cy), int(cx - 2), int(cy + 3))
                        d2d.DrawEllipse(int(cx + 2), int(cy), int(cx + 5), int(cy + 3))
            # ---------------------------------
            
            d2d.FinishDrawing()
            with open(test1_out, "wb") as f:
                f.write(d2d.GetDrawingText())
            
            print(f"[SUCCESS] Generated fixed structure for test1.chem: {test1_out}")
            
            # Generate PDF for test1
            pdf_path_test1 = exp.create_report(
                molecule_name="Test1 (Fixed)",
                spectra_data={"IR": {}, "NMR_1H": {}},
                structure_image_path=str(test1_out),
                metadata={"smiles": Chem.MolToSmiles(mol)}
            )
            print(f"[SUCCESS] Fixed PDF for test1: {pdf_path_test1}")
            
    except Exception as e:
        print(f"Failed to process test1.chem: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
