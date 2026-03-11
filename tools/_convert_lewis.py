import json
import os
import sys
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import Draw
from rdkit.Geometry import Point3D
from rdkit.Chem import AllChem

# Robustness Update:
# 1. Use absolute paths based on script location
# 2. Add verbose logging to stdout/stderr
# 3. Explicit error handling for directory creation

def parse_chem_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"[ERROR] Failed to parse {file_path}: {e}", file=sys.stderr)
        return None

def build_mol_from_data(data):
    if not data: return None
    
    mol = Chem.RWMol()
    conf = Chem.Conformer()
    
    atom_map = {}
    
    # 1. Add Atoms
    for coord_str, atom_info in data['atoms'].items():
        symbol = atom_info.get('main', '').strip()
        if not symbol:
            symbol = 'C'
            
        try:
            atom = Chem.Atom(symbol)
            idx = mol.AddAtom(atom)
            atom_map[coord_str] = idx
            
            x, y = map(float, coord_str.split(','))
            conf.SetAtomPosition(idx, Point3D(x, -y, 0.0))
            
        except Exception as e:
            print(f"[WARN] Failed to add atom at {coord_str}: {e}", file=sys.stderr)

    mol.AddConformer(conf)

    # 2. Add Bonds
    for bond_key, order in data['bonds'].items():
        try:
            start_coord, end_coord = bond_key.split('|')
            if start_coord in atom_map and end_coord in atom_map:
                start_idx = atom_map[start_coord]
                end_idx = atom_map[end_coord]
                
                bond_type = Chem.BondType.SINGLE
                if order == 2: bond_type = Chem.BondType.DOUBLE
                elif order == 3: bond_type = Chem.BondType.TRIPLE
                
                mol.AddBond(start_idx, end_idx, bond_type)
        except Exception as e:
            print(f"[WARN] Failed to add bond {bond_key}: {e}", file=sys.stderr)

    # 3. Sanitize
    try:
        Chem.SanitizeMol(mol)
    except Exception as e:
        print(f"[WARN] Mol sanitization failed: {e}", file=sys.stderr)
        try:
            mol.UpdatePropertyCache(strict=False)
        except:
            pass
            
    return mol

def main():
    # Resolve absolute paths
    script_dir = Path(__file__).parent.absolute()
    source_dir = script_dir / "_source"
    output_dir = source_dir / "lewis_structures" / "pdf"
    
    print(f"Script Directory: {script_dir}")
    print(f"Source Directory: {source_dir}")
    print(f"Output Directory: {output_dir}")
    
    # Ensure directory exists (Robust check)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Verified output directory: {output_dir}")
    except Exception as e:
        print(f"[FATAL] Could not create directory {output_dir}: {e}", file=sys.stderr)
        return

    chem_files = sorted(list(source_dir.glob("*.chem")))
    if not chem_files:
        print(f"[ERROR] No .chem files found in {source_dir}", file=sys.stderr)
        return

    print(f"Found {len(chem_files)} .chem files. Converting...")
    
    success_count = 0
    
    for cf in chem_files:
        try:
            print(f"Processing {cf.name}...")
            data = parse_chem_file(cf)
            mol = build_mol_from_data(data)
            
            if mol and mol.GetNumAtoms() > 0:
                output_path = output_dir / f"{cf.stem}_lewis.pdf"
                
                opts = Draw.MolDrawOptions()
                opts.addAtomIndices = False
                opts.addStereoAnnotation = True
                
                # Try generating Image first then saving (ReportLab fallback if RDKit PDF fails)
                try:
                    # Method 1: Direct PDF via RDKit
                    Draw.MolToFile(mol, str(output_path), size=(600, 600), options=opts)
                    
                    if output_path.exists() and output_path.stat().st_size > 0:
                        print(f"[OK] Saved PDF via RDKit: {output_path}")
                        success_count += 1
                        continue
                    else:
                         print("[WARN] RDKit PDF generation produced empty/missing file. Trying fallback...", file=sys.stderr)
                except Exception as e:
                    print(f"[WARN] RDKit PDF generation failed: {e}. Trying fallback...", file=sys.stderr)
                
                # Method 2: Fallback to PIL Image -> PDF
                try:
                    from PIL import Image
                    img = Draw.MolToImage(mol, size=(600, 600), options=opts)
                    # Save as PDF using PIL
                    img.save(str(output_path), "PDF", resolution=100.0)
                    if output_path.exists() and output_path.stat().st_size > 0:
                        print(f"[OK] Saved PDF via PIL: {output_path}")
                        success_count += 1
                    else:
                        print(f"[ERROR] PIL PDF generation failed (0 bytes) for {cf.name}", file=sys.stderr)
                except Exception as e:
                    print(f"[ERROR] Fallback PDF generation failed for {cf.name}: {e}", file=sys.stderr)

            else:
                print(f"[SKIP] Empty or invalid molecule for {cf.name}")
                
        except Exception as e:
            print(f"[ERROR] Failed to convert {cf.name}: {e}", file=sys.stderr)

    print(f"Conversion Complete. Success: {success_count}/{len(chem_files)}")

if __name__ == "__main__":
    main()
