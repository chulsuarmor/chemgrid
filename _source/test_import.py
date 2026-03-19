#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import traceback

try:
    print("Attempting to import orca_interface...")
    from orca_interface import _parse_out_file
    print("✓ Successfully imported _parse_out_file")
    print(f"Function: {_parse_out_file}")
except Exception as e:
    print(f"✗ Failed to import: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n✓ Import test passed!")
