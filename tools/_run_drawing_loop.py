import requests
import time
import subprocess
import os
import sys
from PIL import ImageGrab

BASE_URL = "http://127.0.0.1:8000"

def run_action(action):
    tool = action.get("tool")
    try:
        if tool == "select":
            cat = action.get("category")
            val = action.get("value")
            resp = requests.post(f"{BASE_URL}/tools/select", params={"category": cat, "value": val})
            print(f"  Select {cat}:{val} -> {resp.status_code}")
            
        elif tool == "click":
            x = action.get("x")
            y = action.get("y")
            resp = requests.post(f"{BASE_URL}/draw/click", params={"x": x, "y": y})
            print(f"  Click ({x},{y}) -> {resp.status_code}")
            
        elif tool == "drag":
            sx, sy = action.get("start_x"), action.get("start_y")
            ex, ey = action.get("end_x"), action.get("end_y")
            resp = requests.post(f"{BASE_URL}/draw/drag", params={"start_x": sx, "start_y": sy, "end_x": ex, "end_y": ey})
            print(f"  Drag ({sx},{sy})->({ex},{ey}) -> {resp.status_code}")
            
        time.sleep(0.5) # Action delay
    except Exception as e:
        print(f"  Action failed: {e}")

def capture_screen(filename):
    try:
        # Capture entire screen or active window logic needs to be robust
        # Simple fullscreen capture for now
        screenshot = ImageGrab.grab()
        screenshot.save(filename)
        print(f"  Saved screenshot: {filename}")
    except Exception as e:
        print(f"  Capture failed: {e}")

def main():
    # Wait for server to be ready
    print("Waiting for MCP server...")
    for _ in range(10):
        try:
            requests.get(BASE_URL)
            break
        except:
            time.sleep(1)
            
    # Levels to test
    levels = [1, 2, 6] 
    
    for level in levels:
        print(f"\n=== Starting Level {level} ===")
        
        # 1. Reset Canvas
        requests.post(f"{BASE_URL}/canvas/reset")
        time.sleep(1)
        
        # 2. Get Molecule Data
        resp = requests.post(f"{BASE_URL}/molecule/generate", params={"level": level})
        if resp.status_code != 200:
            print(f"Failed to get level {level} data")
            continue
            
        data = resp.json()
        mol = data.get("molecule", {})
        actions = mol.get("actions", [])
        print(f"Target: {mol.get('name')} ({mol.get('formula')}) - {len(actions)} actions")
        
        # 3. Execute Actions
        for i, action in enumerate(actions):
            print(f"Action {i+1}/{len(actions)}: {action}")
            run_action(action)
            
        # 4. Wait for rendering
        time.sleep(2)
        
        # 5. Capture Result
        capture_screen(f"level_{level}_result.png")
        
        # 6. Validate (Placeholder)
        print(f"Level {level} completed. Check level_{level}_result.png")
        time.sleep(2)

if __name__ == "__main__":
    main()
