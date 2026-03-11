import subprocess
import time
import requests
import sys
import os
def run_test():
    # 1. Cleanup
    print("Step 1: Cleanup...")
    # Call _kill_chemgrid.py logic directly or via subprocess
    subprocess.run([sys.executable, "_kill_chemgrid.py"])
    time.sleep(2)

    # 2. Start MCP Server
    print("Step 2: Starting MCP Server...")
    env = os.environ.copy()
    # Redirect output to file for debugging
    server_log = open("server_log.txt", "w")
    server_process = subprocess.Popen(
        [sys.executable, "agents/mcp_server/server.py"],
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT
    )
    
    # 3. Start ChemGrid
    print("Step 3: Starting ChemGrid...")
    chemgrid_process = subprocess.Popen(
        [sys.executable, "agents/10_testing_build/integrated/draw.py"],
        env=env
    )
    
    print("Waiting for services to start (10s)...")
    time.sleep(10)
    
    # 4. Test MCP Endpoints
    print("Step 4: Testing MCP Endpoints...")
    try:
        # 4.1 Check Root
        resp = requests.get("http://127.0.0.1:8000/")
        print(f"Root Status: {resp.status_code}")
        print(f"Root Response: {resp.json()}")
        
        # 4.2 Generate Molecule Level 6 (Tropylium)
        resp = requests.post("http://127.0.0.1:8000/molecule/generate?level=6")
        print(f"Level 6 Info: {resp.json()}")
        
        # 4.3 Test Click (Coordinates Check)
        # Tropylium Charge Position (5, 3)
        # Using query params for POST as defined in server.py (or JSON body if FastAPI infers)
        # FastAPI defaults to query params for simple types unless Body is used
        resp = requests.post("http://127.0.0.1:8000/draw/click?x=5&y=3")
        print(f"Click Test (5,3): {resp.json()}")
        
        if resp.status_code == 200:
            print("\n[SUCCESS] MCP Server and ChemGrid communication verified.")
            print("Check ChemGrid window for cursor movement or click effect.")
        else:
            print("\n[FAILURE] Click test failed.")
            print(resp.text)
            
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        # Check if server is running
        if server_process.poll() is not None:
             print("Server process exited unexpectedly.")
    
    print("\nProcesses are left running for user interaction.")
    print(f"MCP Server PID: {server_process.pid}")
    print(f"ChemGrid PID: {chemgrid_process.pid}")

if __name__ == "__main__":
    run_test()
