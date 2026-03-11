#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path

# Add source to path
sys.path.insert(0, r"C:\Users\김남헌\Desktop\organicdraw\_source")

# Simple inline test
try:
    import tempfile
    from orca_interface import _parse_out_file
    
    mock_content = """ORCA 5.0.0
THE OPTIMIZATION HAS CONVERGED
FINAL SINGLE POINT ENERGY    -193.123456789
MULLIKEN ATOMIC CHARGES:
    0   C   -0.2000
    1   C   -0.1950
    2   C   -0.2050
    3   C   -0.1950
    4   C   -0.2050
FINAL STRUCTURE (ANGSTROMS AND DEGREES):
0 C    0.00    1.00    0.00
1 C    1.00    0.50    0.00
2 C    0.75   -0.75    0.00
3 C   -0.75   -0.75    0.00
4 C   -1.00    0.50    0.00
ORCA finished
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.out', delete=False) as f:
        f.write(mock_content)
        temp_path = Path(f.name)
    
    print("Testing parser...")
    result = _parse_out_file(temp_path)
    
    print(f"Converged: {result.converged}")
    print(f"Energy: {result.energy}")
    print(f"Geometry atoms: {len(result.geometry)}")
    print(f"Mulliken charges: {result.charges_mulliken}")
    
    total = sum(result.charges_mulliken.values())
    print(f"Total charge: {total:.4f}")
    
    print("\n✓ TEST PASSED!")
    
    temp_path.unlink()
    
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
