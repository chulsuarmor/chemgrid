#!/usr/bin/env python
# Test script for orca_interface.py
import sys
sys.path.insert(0, r'C:\Users\김남헌\Desktop\organicdraw')

try:
    import orca_interface
    print("[OK] orca_interface.py loaded successfully")
    print(f"[OK] ORCA Path: {orca_interface.ORCA_PATH}")
    print(f"[OK] ORCA Exe: {orca_interface.ORCA_EXE}")
    valid = orca_interface.validate_orca_installation()
    print(f"[OK] ORCA validation: {valid}")
except ImportError as e:
    print(f"[ERROR] Import Error: {e}")
except Exception as e:
    print(f"[ERROR] Error: {e}")
