
import yaml
import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "agents", "09_data_export"))

import spectrum_pdf_exporter as exporter
from rdkit import Chem
from rdkit.Chem import Draw
from rdkit.Chem import AllChem
from rdkit.Geometry import Point2D
from rdkit.Geometry import Point3D

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LewisBatch")

# Import the improved generation function (monkey patched or imported)
# We can just define it here or import if it was a module.
# Since it's in a script _fix_structure_generation.py, let's copy the improved logic 
# or import it if we refactor. For now, I will include the logic to ensure it runs self-contained.

def generate_improved_structure_image(mol, output_path: Path) -> bool:
    """
    Improved structure generation with explicit C, H, charges, and lone pairs.
    Takes a RDKit Mol object.
    """
    try:
        # 1. Add Hydrogens (Explicit H)
        mol = Chem.AddHs(mol)
        
        # 2. Compute 2D Coordinates
        AllChem.Compute2DCoords(mol)
        
        # 3. Kekulize (Show double bonds)
        try:
            Chem.Kekulize(mol)
        except:
            pass
            
        # 4. Set Atom Labels (Explicit C)
        for atom in mol.GetAtoms():
            if atom.GetSymbol() == 'C':
                atom.SetProp('_displayLabel', 'C')
                
        # 5. Drawing Options
        try:
            d2d = Draw.MolDraw2DCairo(600, 600)
            opts = d2d.drawOptions()
            opts.bondLineWidth = 3.0
            opts.addStereoAnnotation = True
            
            d2d.DrawMolecule(mol)
            
            # 6. Draw Lone Pairs
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
                    p2 = Point2D(pos_3d.x, pos_3d.y)
                    draw_pos = d2d.GetDrawCoords(p2)
                    
                    offset = 15 
                    # d2d.SetColour(Draw.to_rdkit_color((1.0, 0.0, 0.0)))
                    # Use setColour with RGB tuple directly or Color object if available
                    # RDKit's MolDraw2D often uses RGB tuples (r,g,b) in range 0-1
                    d2d.SetColour((1.0, 0.0, 0.0))
                    
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
                        # DrawEllipse in RDKit C++ signature takes Point2D objects
                        # Point2D(x, y)
                        
                        p1 = Point2D(cx - 2, cy - 2)
                        p2 = Point2D(cx + 2, cy + 2)
                        d2d.DrawEllipse(p1, p2)
                        
                        p1_b1 = Point2D(cx - 5, cy)
                        p2_b1 = Point2D(cx - 2, cy + 3)
                        d2d.DrawEllipse(p1_b1, p2_b1)
                        
                        p1_b2 = Point2D(cx + 2, cy)
                        p2_b2 = Point2D(cx + 5, cy + 3)
                        d2d.DrawEllipse(p1_b2, p2_b2)

            d2d.FinishDrawing()
            bin_data = d2d.GetDrawingText()
            with open(output_path, "wb") as f:
                f.write(bin_data)
            return True
        except Exception as e:
            print(f"Drawing error: {e}")
            return False
            
    except Exception as e:
        print(f"Structure generation error: {e}")
        return False

def parse_chem_file(path):
    import json
    with open(path, 'r') as f:
        data = json.load(f)
    
    mol = Chem.RWMol()
    atoms_data = data.get("atoms", {})
    bonds_data = data.get("bonds", {})
    
    coord_to_idx = {}
    sorted_coords = sorted(atoms_data.keys())
    
    for coord in sorted_coords:
        atom_info = atoms_data[coord]
        symbol = atom_info.get("main", "C")
        if not symbol:  # Handle empty string symbol
            symbol = "C"
        a = Chem.Atom(symbol)
        charge = atom_info.get("formal_charge", 0)
        a.SetFormalCharge(charge)
        idx = mol.AddAtom(a)
        coord_to_idx[coord] = idx
    
        # Helper to get or create atom index for a coordinate (Implicit Carbon Handling)
        def get_or_create_atom(coord):
            if coord in coord_to_idx:
                return coord_to_idx[coord]
            
            # If not found, assume it's a Carbon atom (implicit node found in bonds)
            try:
                a = Chem.Atom("C")
                idx = mol.AddAtom(a)
                coord_to_idx[coord] = idx
                return idx
            except Exception as e:
                print(f"Error creating implicit atom at {coord}: {e}")
                return None

        for bond_key, order in bonds_data.items():
            parts = bond_key.split("|")
            if len(parts) != 2: continue
            c1, c2 = parts
            
            i1 = get_or_create_atom(c1)
            i2 = get_or_create_atom(c2)
            
            if i1 is not None and i2 is not None:
                if i1 == i2: continue
                
                # Check if bond already exists to avoid duplicates
                if mol.GetBondBetweenAtoms(i1, i2):
                    continue

                btype = Chem.BondType.SINGLE
                if order == 2: btype = Chem.BondType.DOUBLE
                elif order == 3: btype = Chem.BondType.TRIPLE
                mol.AddBond(i1, i2, btype)
            
    try:
        Chem.SanitizeMol(mol)
    except:
        pass
    return mol

def main():
    config_path = "lewis_molecules.yaml"
    output_base = Path("docs/exports/spectra_assets/fixed_test/batch_1_10")
    output_base.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
        
    exp = exporter.SpectrumPDFExporter(output_dir=str(output_base))
    
    for mol_def in config.get('molecules', []):
        mid = mol_def['id']
        name = mol_def['name']
        print(f"Processing {mid}: {name}")
        
        mol = None
        source_info = "Unknown"
        
        if mol_def['type'] == 'chemfile':
            p = Path(mol_def['path'])
            source_info = str(p)
            if p.exists():
                try:
                    mol = parse_chem_file(p)
                except Exception as e:
                    print(f"Error parsing {p}: {e}")
            else:
                print(f"File not found: {p}")
        elif mol_def['type'] == 'smiles':
            smiles = mol_def['smiles']
            source_info = f"SMILES: {smiles}"
            try:
                mol = Chem.MolFromSmiles(smiles)
                if not mol:
                    print(f"Invalid SMILES: {smiles}")
            except Exception as e:
                print(f"Error generating from SMILES {smiles}: {e}")
        
        if mol:
            img_path = output_base / f"structure_{mid}.png"
            if generate_improved_structure_image(mol, img_path):
                print(f"Generated image: {img_path}")
                
                # Generate PDF
                pdf_path = exp.create_report(
                    molecule_name=f"Molecule {mid} ({name})",
                    spectra_data={"IR": {}, "NMR_1H": {}}, # Empty spectra for now
                    structure_image_path=str(img_path),
                    metadata={"source": source_info}
                )
                print(f"Generated PDF: {pdf_path}")
            else:
                print(f"Failed to generate image for {mid}")

if __name__ == "__main__":
    main()
