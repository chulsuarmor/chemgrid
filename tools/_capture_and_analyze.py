import pyautogui, time, ctypes, ctypes.wintypes
import requests
import os
import sys

# 1. Capture Logic
print("Locating ChemGrid window...")
user32 = ctypes.windll.user32
hwnd = user32.FindWindowW(None, 'ChemGrid')

if hwnd == 0:
    print("ChemGrid not found, waiting 3s...")
    time.sleep(3)
    hwnd = user32.FindWindowW(None, 'ChemGrid')

if hwnd == 0:
    print("FAIL: ChemGrid window not found. Please launch ChemGrid first.")
    # For testing purposes, if window not found, we might want to exit or use a dummy image if available
    # But here we exit.
    sys.exit(1)

try:
    user32.SetForegroundWindow(hwnd)
    user32.ShowWindow(hwnd, 9) # SW_RESTORE
    time.sleep(1)
    
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    l,t,r,b = rect.left, rect.top, rect.right, rect.bottom
    print(f'Window found: {l},{t},{r},{b} ({r-l}x{b-t})')

    # Ensure valid coordinates
    width = max(1, r-l)
    height = max(1, b-t)
    left = max(0, l)
    top = max(0, t)

    img_path = r'c:\chemgrid\_screenshot_for_analysis.png'
    img = pyautogui.screenshot(region=(left, top, width, height))
    img.save(img_path)
    print(f'Saved screenshot to {img_path}')

except Exception as e:
    print(f"Error during capture: {e}")
    sys.exit(1)

# 2. Send to MCP Server
server_url = "http://127.0.0.1:8000/analyze_image"
print(f"Sending to MCP server: {server_url}")

try:
    with open(img_path, 'rb') as f:
        files = {'file': (os.path.basename(img_path), f, 'image/png')}
        # Prompt designed to extract structure info
        prompt_text = """
        Analyze this chemical drawing interface. 
        1. Identify the chemical structure drawn in the canvas area.
        2. Provide the SMILES representation if possible.
        3. Describe the drawing state (e.g., incomplete bonds, selected atoms).
        4. Return the result as a JSON object with keys: "structure_name", "smiles", "drawing_state", "suggestions".
        """
        data = {'prompt': prompt_text}
        
        response = requests.post(server_url, files=files, data=data)
        
    if response.status_code == 200:
        print("\n--- Analysis Result ---")
        result = response.json()
        print(result.get('result', result))
        print("-----------------------")
    else:
        print(f"Server returned error: {response.status_code}")
        try:
            print(response.json())
        except:
            print(response.text)

except requests.exceptions.ConnectionError:
    print("\n[ERROR] Could not connect to MCP server.")
    print("Please ensure the server is running:")
    print("  python agents/mcp_server/server.py")
except Exception as e:
    print(f"\n[ERROR] An unexpected error occurred: {e}")
