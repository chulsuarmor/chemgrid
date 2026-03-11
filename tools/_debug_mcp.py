print("Hello World")
try:
    import fastapi
    print("FastAPI found")
    import uvicorn
    print("Uvicorn found")
    import rdkit
    print("RDKit found")
    import pyautogui
    print("PyAutoGUI found")
except ImportError as e:
    print(f"Import Error: {e}")
