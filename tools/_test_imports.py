"""Quick import test for chemgrid conda environment"""
print("=== ChemGrid Import Test ===")

try:
    import PyQt6.QtCore
    print(f"[OK] PyQt6: {PyQt6.QtCore.PYQT_VERSION_STR}")
except Exception as e:
    print(f"[FAIL] PyQt6: {e}")

try:
    import rdkit
    print(f"[OK] RDKit: {rdkit.__version__}")
except Exception as e:
    print(f"[FAIL] RDKit: {e}")

try:
    import OpenGL
    print(f"[OK] PyOpenGL: {OpenGL.__version__}")
except Exception as e:
    print(f"[FAIL] PyOpenGL: {e}")

try:
    import matplotlib
    print(f"[OK] matplotlib: {matplotlib.__version__}")
except Exception as e:
    print(f"[FAIL] matplotlib: {e}")

try:
    import numpy
    print(f"[OK] numpy: {numpy.__version__}")
except Exception as e:
    print(f"[FAIL] numpy: {e}")

try:
    import google.generativeai
    print(f"[OK] google-generativeai: available")
except Exception as e:
    print(f"[FAIL] google-generativeai: {e}")

try:
    import requests
    print(f"[OK] requests: {requests.__version__}")
except Exception as e:
    print(f"[FAIL] requests: {e}")

print("\n=== All tests complete ===")
