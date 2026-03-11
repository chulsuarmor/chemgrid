import requests
try:
    print("Testing MCP Server...")
    # Generate Molecule
    resp = requests.post("http://127.0.0.1:8000/molecule/generate?level=6")
    print(f"Generate Level 6: {resp.json()}")
    
    # Click Test
    resp = requests.post("http://127.0.0.1:8000/draw/click?x=5&y=3")
    print(f"Click (5,3): {resp.json()}")
except Exception as e:
    print(f"Error: {e}")
