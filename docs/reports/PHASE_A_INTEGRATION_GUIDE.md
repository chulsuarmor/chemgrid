# Phase A Integration Guide
## How to Use orca_interface.py in ChemDraw Pro

---

## Quick Start

### 1. Import the Module
```python
from orca_interface import (
    generate_orca_input,
    create_calculation_workflow,
    OrcaCalculationResult,
    ElectronicDensity,
    validate_orca_installation
)
```

### 2. Validate ORCA Installation (One-time)
```python
# Check if ORCA is properly installed
if not validate_orca_installation():
    print("ORCA installation not found!")
    return False
print("ORCA ready for calculations")
```

### 3. Prepare Molecular Structure
```python
# Get atoms and bonds from ChemDraw analyzer
analyzer = ChemicalAnalyzer()
result = analyzer.analyze(atoms, bonds)

# Extract structure
draw_atoms = result["atoms"]  # {(x,y): {"main": "C", ...}}
draw_bonds = result["bonds"]  # {(k1,k2): bond_order}
```

### 4. Create Calculation
```python
# Create workflow (non-blocking QThread)
input_file, calculator = create_calculation_workflow(
    atoms=draw_atoms,
    bonds=draw_bonds,
    charge=0,           # Molecular charge
    multiplicity=1      # Spin state (1=singlet, 2=doublet, etc.)
)

print(f"Input file created: {input_file}")
```

### 5. Connect Signals (For GUI Integration)
```python
from PyQt6.QtCore import QObject

def on_progress(msg):
    print(f"Progress: {msg}")

def on_result(calc_result: OrcaCalculationResult):
    print(f"Calculation completed!")
    print(f"  Converged: {calc_result.converged}")
    print(f"  Energy: {calc_result.energy:.6f} Hartree")
    print(f"  Atoms: {len(calc_result.geometry)}")
    
    # Access density data
    for density in calc_result.densities:
        print(f"  Atom {density.atom_index}: "
              f"q_M={density.mulliken_charge:.3f}, "
              f"q_L={density.lowdin_charge:.3f}")

def on_error(error_msg):
    print(f"Error: {error_msg}")

# Connect signals
calculator.progress.connect(on_progress)
calculator.result.connect(on_result)
calculator.error.connect(on_error)
```

### 6. Start Calculation
```python
# Non-blocking calculation in background thread
calculator.start()

# Or in batch mode:
# calculator.run()  # Blocks until complete
```

### 7. Access Results
```python
# After calculation completes and on_result() is called:

# Geometry (optimized coordinates)
optimized_geometry = result.geometry
for atom_idx, (x, y, z) in optimized_geometry.items():
    x_norm = round(x, 2)
    y_norm = round(y, 2)
    z_norm = round(z, 2)
    print(f"Atom {atom_idx}: ({x_norm}, {y_norm}, {z_norm})")

# Partial Charges
mulliken_charges = result.charges_mulliken
lowdin_charges = result.charges_lowdin

# Electronic Density Objects
for density in result.densities:
    print(f"{density.atom_symbol} at {density.position}")
    print(f"  Mulliken: {density.mulliken_charge:+.3f}")
    print(f"  Löwdin: {density.lowdin_charge:+.3f}")
    print(f"  Density: {density.density:.6f}")

# Bond Orders (connectivity strength)
bond_orders = result.bond_orders
for (i, j), order in bond_orders.items():
    print(f"Bond {i}-{j}: {order:.2f}")
```

---

## Integration with Existing Code

### With analyzer.py
```python
from analyzer import ChemicalAnalyzer
from orca_interface import create_calculation_workflow

analyzer = ChemicalAnalyzer()
analysis = analyzer.analyze(atoms, bonds)

# Use analysis results
charges = analysis["charges"]
atoms_updated = analysis["atoms"]

# Calculate with ORCA
input_file, calc_thread = create_calculation_workflow(
    atoms=atoms_updated,
    bonds=analysis["bonds"],
    charge=0,
    multiplicity=1
)
```

### With RDKit Integration
```python
# analyzer.py already extracts SMILES and stereo info
smiles, stereo_labels, lewis_data, theory_data = analyzer.generate_smiles(atoms, bonds)

# Refine with ORCA DFT
input_file, calc_thread = create_calculation_workflow(atoms, bonds)

# Then compare ORCA geometry with RDKit 2D coordinates
# High-quality 3D structure ready for visualization
```

### Signal Integration with PyQt6
```python
from PyQt6.QtWidgets import QMainWindow, QProgressBar, QLabel
from orca_interface import OrcaCalculatorThread

class ChemDrawWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Ready")
        
        self.calculator = None  # Will be set by calculation method
    
    def run_orca_calculation(self):
        input_file, calculator = create_calculation_workflow(atoms, bonds)
        self.calculator = calculator
        
        # Connect to UI elements
        calculator.progress.connect(self.update_progress)
        calculator.result.connect(self.on_calculation_done)
        calculator.error.connect(self.on_calculation_error)
        
        # Start calculation
        calculator.start()
    
    def update_progress(self, msg: str):
        self.status_label.setText(msg)
        self.progress_bar.setValue(self.progress_bar.value() + 10)
    
    def on_calculation_done(self, result):
        self.status_label.setText(f"Calculation complete! "
                                  f"Energy: {result.energy:.6f} H")
        # Update visualization
        self.update_3d_structure(result.geometry)
        self.update_charge_display(result.densities)
    
    def on_calculation_error(self, error_msg: str):
        self.status_label.setText(f"Error: {error_msg}")
```

---

## Data Flow Diagram

```
ChemDraw Editor
      ↓
  atoms, bonds
      ↓
  analyzer.py (RDKit)
      ↓
  charges, stereo, SMILES
      ↓
  create_calculation_workflow()
  ↓                          ↓
input.inp              OrcaCalculatorThread
  ↓                          ↓
ORCA Executable (QThread)   progress signals
  ↓                          ↓
output.out, .gbw ←→ Parser
  ↓
OrcaCalculationResult
  ├─ geometry (optimized)
  ├─ charges (Mulliken, Löwdin)
  ├─ densities
  ├─ bond_orders
  └─ energy
  ↓
GUI Updates (visualization, properties, etc.)
```

---

## Precision & Coordinates

### Important Coordinate Rules

1. **Always round to 2 decimals**
   ```python
   # Correct
   x_norm = round(x_value, 2)
   
   # Wrong (loses precision tracking)
   x_norm = x_value
   ```

2. **ChemDraw coordinates (2D)**
   - Origin: Top-left
   - Range: Typically 0-1000 pixels
   - Rounding: round(coord, 2)
   - Example: (100.45, 234.67)

3. **ORCA coordinates (3D)**
   - Origin: Arbitrary (typically centered on molecule)
   - Units: Angstrom (not pixels!)
   - Precision: 6 decimal places in files
   - Conversion: `orca_coord = draw_coord / 20.0` (approximate)
   - Example: (5.00, 11.73, 0.00)

4. **Output geometry**
   ```python
   geometry = result.geometry  # Dict[int, Tuple[float, float, float]]
   x, y, z = geometry[atom_index]
   
   # Already normalized to 2 decimals by parser!
   x_normalized = round(x, 2)  # Already done
   ```

---

## Common Use Cases

### Use Case 1: Optimize Geometry
```python
# Draw molecule → Optimize with ORCA → Get refined 3D coords
input_file, calc = create_calculation_workflow(atoms, bonds)
calc.result.connect(lambda r: display_3d_structure(r.geometry))
calc.start()
```

### Use Case 2: Calculate Properties
```python
# After optimization, extract properties
def on_done(result):
    # Energies
    print(f"DFT Energy: {result.energy} Hartree")
    
    # Charges (electron density distribution)
    for i, q in result.charges_mulliken.items():
        print(f"Atom {i}: {q:+.3f} e")
    
    # Bonding (bond orders)
    for (i, j), order in result.bond_orders.items():
        print(f"Bond {i}-{j}: {order:.2f}")
```

### Use Case 3: Batch Calculations
```python
# Process multiple structures
molecules = [mol1, mol2, mol3, ...]
results = []

for mol in molecules:
    input_file, calc = create_calculation_workflow(
        mol["atoms"], mol["bonds"]
    )
    calc.result.connect(lambda r: results.append(r))
    calc.start()
    # Note: Use proper queue/threading for large batches
```

### Use Case 4: Export to External Tools
```python
# ORCA → Visualization in another tool
result = calculation_result

# Export as XYZ format (common format)
with open("molecule.xyz", "w") as f:
    f.write(f"{len(result.geometry)}\n")
    f.write("Optimized molecule\n")
    for i, (x, y, z) in result.geometry.items():
        # Get atom symbol from original atoms dict
        symbol = atoms_dict[i]["main"]
        f.write(f"{symbol} {x:.6f} {y:.6f} {z:.6f}\n")
```

---

## Error Handling

### Expected Errors

1. **ORCA Not Found**
   ```python
   if not validate_orca_installation():
       # Handle missing ORCA
       pass
   ```

2. **Calculation Timeout**
   ```python
   def on_error(msg):
       if "timeout" in msg.lower():
           # Large molecule? Try again with modified input
           pass
   ```

3. **Convergence Issues**
   ```python
   def on_done(result):
       if not result.converged:
           print("Warning: SCF did not converge")
           # Try with looser convergence
   ```

4. **Invalid Geometry**
   ```python
   # If atoms too close or bonds invalid:
   # orca_interface automatically detects in validate_orca_installation()
   ```

---

## Performance Tips

1. **Use QThread for UI Responsiveness**
   ```python
   # Good: Non-blocking
   calculator.start()  # Runs in background
   
   # Bad: Blocks UI
   calculator.run()  # Blocks until done
   ```

2. **Batch Similar Calculations**
   ```python
   # Reuse one ORCA process for similar geometries
   # Instead of starting many sequential calculations
   ```

3. **Limit Basis Set for Quick Estimates**
   ```python
   # 6-31G(d) is default - good balance
   # For very large molecules, could use STO-3G (Phase B feature)
   ```

4. **Monitor System Resources**
   ```python
   # Each ORCA process uses ~1-5 GB RAM
   # Don't run too many in parallel
   # Use threading queue for controlled batch processing
   ```

---

## Testing Checklist

Before using in production:

- [ ] ORCA executable verified with `validate_orca_installation()`
- [ ] Test molecule geometry created
- [ ] `create_calculation_workflow()` produces valid input file
- [ ] `OrcaCalculatorThread` signals correctly connected
- [ ] Results parsed correctly (check `on_result()` callback)
- [ ] Coordinate precision maintained (round to 2 decimals)
- [ ] Error messages clear and actionable
- [ ] UI updates smoothly during calculation (QThread working)
- [ ] Large molecules handled without crashes
- [ ] File cleanup after calculation (temp files removed)

---

## Next Phases

### Phase B (Density Visualization)
- Read .gbw density cube files
- Interpolate density values between points
- Create 3D density isosurfaces
- Export for visualization software

### Phase C (Full Integration)
- Embed ORCA in ChemDraw GUI
- Real-time property updates
- Molecular orbital visualization
- Spectroscopy prediction

### Phase D (Extended Chemistry)
- TD-DFT for excited states
- Frequency analysis (IR, Raman)
- Reaction pathway analysis
- Solvation models

---

## Support

For issues:
1. Check log output from calculator.progress signals
2. Verify ORCA installation: `validate_orca_installation()`
3. Check calculation input file in work directory
4. Review ORCA output file (.out) for error messages
5. Check Discord channel for Phase updates

---

## Document Info
- **Created:** 2026-02-06
- **For Version:** Phase A Complete
- **Target User:** ChemDraw Pro Developers
- **Last Updated:** 00:45 GMT+9

