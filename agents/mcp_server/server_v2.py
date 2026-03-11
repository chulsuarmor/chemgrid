import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import google.generativeai as genai
from PIL import Image
import io
from dotenv import load_dotenv
import time
import win32gui
import win32api
import win32con
import math

# Load environment variables
load_dotenv()

app = FastAPI(title="Gemini MCP Server & ChemGrid Tools V2")

# Configure Gemini
api_key = os.getenv("GOOGLE_API_KEY")

# --- Molecule Complexity Database ---
# 좌표 시스템: Hexagonal Grid
# grid_size = 40
# row_height = 40 * 0.866
# odd_row_offset = 20

COMPLEXITY_LEVELS = {
    1: {
        "type": "linear", "name": "Water", "formula": "H2O", "smiles": "O", 
        "instructions": ["Select Oxygen", "Place on grid"],
        "actions": [
            {"tool": "select", "category": "element", "value": "O"},
            {"tool": "click", "x": 5, "y": 5}
        ]
    },
    2: {
        "type": "linear", "name": "Ethanol", "formula": "C2H6O", "smiles": "CCO", 
        "instructions": ["Draw C-C bond", "Draw C-O bond"],
        "actions": [
            {"tool": "select", "category": "bond", "value": "single"}, # Bond tool first
            {"tool": "select", "category": "element", "value": "C"},
            {"tool": "drag", "start_x": 4, "start_y": 5, "end_x": 5, "end_y": 5}, # C-C
            {"tool": "select", "category": "element", "value": "O"},
            {"tool": "drag", "start_x": 5, "start_y": 5, "end_x": 6, "end_y": 5}  # C-O
        ]
    },
    3: {
        "type": "branch", "name": "Isopropanol", "formula": "C3H8O", "smiles": "CC(O)C", 
        "instructions": ["Draw 3-carbon chain", "Add Oxygen to middle carbon"],
        "actions": [
            {"tool": "select", "category": "bond", "value": "single"},
            {"tool": "select", "category": "element", "value": "C"},
            {"tool": "drag", "start_x": 4, "start_y": 5, "end_x": 5, "end_y": 5}, # C-C
            {"tool": "drag", "start_x": 5, "start_y": 5, "end_x": 6, "end_y": 5}, # C-C
            {"tool": "select", "category": "element", "value": "O"},
            # Hex grid check: (5,5) -> (5,4)
            {"tool": "drag", "start_x": 5, "start_y": 5, "end_x": 5, "end_y": 4}  # C-O (branch)
        ]
    },
    4: {
        "type": "pentagon_radical",
        "name": "Cyclopentadienyl Radical",
        "formula": "C5H5", 
        "smiles": "[C]1C=CC=C1",
        "instructions": ["Draw 5-membered ring manually", "Add double bonds", "Add radical"],
        "actions": [
            {"tool": "select", "category": "bond", "value": "single"},
            {"tool": "select", "category": "element", "value": "C"},
            # 5-membered ring approximation on hex grid
            {"tool": "drag", "start_x": 5, "start_y": 4, "end_x": 4, "end_y": 5},
            {"tool": "drag", "start_x": 4, "start_y": 5, "end_x": 5, "end_y": 6},
            {"tool": "drag", "start_x": 5, "start_y": 6, "end_x": 6, "end_y": 5}, # Adjusted loop
            {"tool": "drag", "start_x": 6, "start_y": 5, "end_x": 5, "end_y": 4},
            
            # Double bonds
            {"tool": "select", "category": "bond", "value": "double"},
            {"tool": "click", "x": 4, "y": 5}, # Bond between 5,4 and 4,5 roughly
            {"tool": "click", "x": 6, "y": 5}, 

            # Radical - MUST CLICK ON ATOM
            {"tool": "select", "category": "radical", "value": "true"},
            {"tool": "click", "x": 5, "y": 4} # Top atom
        ]
    },
    5: {
        "type": "branch_stereo",
        "name": "(S)-Lactic Acid",
        "formula": "C3H6O3", 
        "smiles": "C[C@H](O)C(=O)O",
        "instructions": ["Draw propane backbone", "Add Oxygen atoms", "Add Wedge bond for stereochemistry"],
        "actions": [
            # Backbone: C-C-C
            {"tool": "select", "category": "bond", "value": "single"},
            {"tool": "select", "category": "element", "value": "C"},
            {"tool": "drag", "start_x": 5, "start_y": 5, "end_x": 6, "end_y": 5}, # C1-C2 (Chiral center)
            {"tool": "drag", "start_x": 6, "start_y": 5, "end_x": 7, "end_y": 5}, # C2-C3 (Carboxyl)
            
            # Carboxyl group (C3)
            {"tool": "select", "category": "element", "value": "O"},
            {"tool": "drag", "start_x": 7, "start_y": 5, "end_x": 8, "end_y": 4}, # C-OH
            {"tool": "select", "category": "bond", "value": "double"},
            {"tool": "drag", "start_x": 7, "start_y": 5, "end_x": 8, "end_y": 6}, # C=O
            
            # Chiral center (C2) - OH group with Wedge
            {"tool": "select", "category": "bond", "value": "wedge"},
            {"tool": "select", "category": "element", "value": "O"},
            {"tool": "drag", "start_x": 6, "start_y": 5, "end_x": 6, "end_y": 4}  # C-OH (Wedge)
        ]
    },
    6: {
        "type": "heptagon_charge",
        "name": "Tropylium Ion",
        "formula": "C7H7+", 
        "smiles": "[C+]1=CC=CC=CC1",
        "instructions": ["Draw 7-membered ring manually", "Add double bonds", "Add positive charge"],
        "actions": [
            {"tool": "select", "category": "bond", "value": "single"},
            {"tool": "select", "category": "element", "value": "C"},
            # 7-membered ring on hex grid (approximate)
            {"tool": "drag", "start_x": 5, "start_y": 3, "end_x": 4, "end_y": 4},
            {"tool": "drag", "start_x": 4, "start_y": 4, "end_x": 4, "end_y": 5},
            {"tool": "drag", "start_x": 4, "start_y": 5, "end_x": 5, "end_y": 6},
            {"tool": "drag", "start_x": 5, "start_y": 6, "end_x": 6, "end_y": 6},
            {"tool": "drag", "start_x": 6, "start_y": 6, "end_x": 7, "end_y": 5}, # 7,5
            {"tool": "drag", "start_x": 7, "start_y": 5, "end_x": 7, "end_y": 4},
            {"tool": "drag", "start_x": 7, "start_y": 4, "end_x": 5, "end_y": 3}, # Close

            # Double bonds
            {"tool": "select", "category": "bond", "value": "double"},
            {"tool": "click", "x": 4, "y": 4}, 
            {"tool": "click", "x": 5, "y": 6},
            {"tool": "click", "x": 7, "y": 4},

            # Positive Charge - MUST CLICK ON ATOM (5,3)
            {"tool": "select", "category": "charge", "value": "+1"},
            {"tool": "click", "x": 5, "y": 3}
        ]
    },
    7: {
        "type": "placeholder", "name": "Molecule 7", "actions": []
    },
    8: {
        "type": "placeholder", "name": "Molecule 8", "actions": []
    },
    9: {
        "type": "placeholder", "name": "Molecule 9", "actions": []
    },
    10: {
        "type": "complex", "name": "Hemoglobin (Heme B Core)", 
        "formula": "C34H32FeN4O4",
        "instructions": ["Draw Porphyrin ring", "Add Iron center"],
        "actions": [] # To be implemented
    }
}

# --- Helper Functions ---
def get_chemgrid_window_handle():
    target_hwnd = []
    print("DEBUG: Starting EnumWindows...")
    def enum_handler(hwnd, ctx):
        try:
            title = win32gui.GetWindowText(hwnd)
            if title:
                # Log only potential candidates to reduce noise, or all if desperate
                if "Chem" in title or "Grid" in title or "Python" in title:
                    print(f"DEBUG: Checking window '{title}' ({hwnd})")
                
            if "ChemGrid" in title:
                print(f"DEBUG: Found ChemGrid window '{title}' ({hwnd})")
                target_hwnd.append(hwnd)
        except Exception as e:
            print(f"DEBUG: Enum error: {e}")
            pass
    win32gui.EnumWindows(enum_handler, None)
    
    if not target_hwnd:
        print("DEBUG: No ChemGrid window found!")
        
    return target_hwnd[0] if target_hwnd else None

def get_window_size(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    return rect[2] - rect[0], rect[3] - rect[1]

def make_lparam(x, y):
    return (y << 16) | (x & 0xFFFF)

def send_click_msg(hwnd, x, y):
    lparam = make_lparam(x, y)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)

def send_drag_msg(hwnd, start_x, start_y, end_x, end_y):
    start_lparam = make_lparam(start_x, start_y)
    end_lparam = make_lparam(end_x, end_y)
    
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, start_lparam)
    time.sleep(0.05)
    
    steps = 20 
    for i in range(steps):
        mx = int(start_x + (end_x - start_x) * (i/steps))
        my = int(start_y + (end_y - start_y) * (i/steps))
        win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, make_lparam(mx, my))
        time.sleep(0.01) 
        
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, end_lparam)

def get_toolbar_position(element_type, value=None):
    # tb1 (Main) height approx 50-60px.
    # Icon Y center ~ 40px relative to window client area if toolbar is at top.
    # BUT client area starts below toolbar in some frameworks. 
    # Let's assume absolute client coordinates including toolbar.
    
    y_tb1 = 40
    
    if element_type == "bond":
        if value in ["single", "double", "triple"]: return (100, y_tb1) 
        if value == "wedge": return (330, y_tb1)
        if value == "dash": return (290, y_tb1)
        
    if element_type == "element":
        start_x = 360
        step = 40
        mapping = {
            "H": 0, "R": 1, 
            "O": 6, "N": 7, "P": 8, "S": 9, "F": 10, "Cl": 11, "Br": 12, "I": 13,
            "C": -1 
        }
        idx = mapping.get(value)
        if idx is not None and idx >= 0:
            return (start_x + idx * step, y_tb1)
        if value == "C": return (100, y_tb1) # Carbon uses Bond tool (100)
        
    if element_type == "charge":
        start_x = 360
        step = 40
        # Positive(520), Negative(560)
        if value == "+1" or value == "+": return (start_x + 4 * step, y_tb1) # 520
        if value == "-1" or value == "-": return (start_x + 5 * step, y_tb1) # 560
        
    if element_type == "radical":
        # Radical(480)
        return (360 + 3 * 40, y_tb1) 

    if element_type == "export":
        # tb2 estimated location
        # Reset is at (160, 90), which is likely "Clear All"
        # Export is to the left of Clear All.
        return (120, 90)
    
    return (0, 0)

def get_mode_button_position(hwnd, mode_name):
    try:
        width, height = get_window_size(hwnd)
        vx = width - 265
        vy = height - 75
        if mode_name == "Lewis": return (vx + 55, vy + 20)
        elif mode_name == "Theory": return (vx + 110 + 10 + 55, vy + 20)
    except: pass
    return (0, 0)

def grid_to_client_pixel(grid_x, grid_y):
    # Hexagonal Grid Logic from canvas.py
    # offset_x, offset_y need calibration. 
    # Based on canvas.py: pan_offset is (0,0) initially.
    # We need to account for Toolbar height + Margins.
    # Assuming Toolbar ~60px.
    
    # Calibration Offset (User requested: "study coordinates")
    # This is an estimate. If still off, we need calibration script.
    BASE_OFFSET_X = 50 
    BASE_OFFSET_Y = 100 # Moved down to account for toolbar
    
    GRID_SIZE = 40
    ROW_HEIGHT = GRID_SIZE * 0.866
    
    off = 20 if grid_y % 2 != 0 else 0
    
    pixel_x = int(BASE_OFFSET_X + (grid_x * GRID_SIZE) + off)
    pixel_y = int(BASE_OFFSET_Y + (grid_y * ROW_HEIGHT))
    
    return (pixel_x, pixel_y)

def get_model():
    if not api_key: return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

# --- API Endpoints ---

@app.get("/")
async def root():
    status = "configured" if api_key else "missing_api_key"
    return {"status": "ok", "message": "Gemini MCP Server & ChemGrid Tools Running", "api_status": status}

@app.post("/analyze_image")
async def analyze_image(
    file: UploadFile = File(...), 
    prompt: str = Form("Analyze this chemical structure and provide the SMILES string.")
):
    if not api_key: raise HTTPException(status_code=500, detail="Gemini API key not configured.")
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        model = get_model()
        if not model: raise HTTPException(status_code=500, detail="Failed to initialize Gemini model")
        response = model.generate_content([prompt, image])
        return {"result": response.text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/canvas/reset")
async def reset_canvas():
    hwnd = get_chemgrid_window_handle()
    if not hwnd: return JSONResponse(status_code=404, content={"error": "ChemGrid window not found"})
    # Clear All button in tb2 (approx y=90)
    send_click_msg(hwnd, 160, 90) 
    return {"status": "success"}

@app.post("/draw/click")
async def simulate_click(x: int, y: int):
    hwnd = get_chemgrid_window_handle()
    if not hwnd: return JSONResponse(status_code=404, content={"error": "ChemGrid window not found"})
    px, py = grid_to_client_pixel(x, y)
    send_click_msg(hwnd, px, py)
    return {"status": "success", "grid": (x,y), "pixel": (px, py)}

@app.post("/draw/drag")
async def simulate_drag(start_x: int, start_y: int, end_x: int, end_y: int):
    hwnd = get_chemgrid_window_handle()
    if not hwnd: return JSONResponse(status_code=404, content={"error": "ChemGrid window not found"})
    sp = grid_to_client_pixel(start_x, start_y)
    ep = grid_to_client_pixel(end_x, end_y)
    send_drag_msg(hwnd, sp[0], sp[1], ep[0], ep[1])
    return {"status": "success", "from": (start_x, start_y), "to": (end_x, end_y)}

@app.post("/tools/select")
async def select_tool(category: str, value: str):
    hwnd = get_chemgrid_window_handle()
    if not hwnd: return JSONResponse(status_code=404, content={"error": "ChemGrid window not found"})
    if category == "mode": rx, ry = get_mode_button_position(hwnd, value)
    else: rx, ry = get_toolbar_position(category, value)
    if rx == 0 and ry == 0: return JSONResponse(status_code=400, content={"error": "Unknown tool"})
    send_click_msg(hwnd, rx, ry)
    return {"status": "success", "selected": f"{category}:{value}"}

@app.post("/molecule/generate")
async def generate_molecule(level: int):
    if level not in COMPLEXITY_LEVELS: return JSONResponse(status_code=404, content={"error": f"Level {level} not defined"})
    return {"status": "success", "level": level, "molecule": COMPLEXITY_LEVELS[level]}

@app.post("/validate/smiles")
async def validate_smiles(current_smiles: str, target_smiles: str):
    # Simple validation for now
    norm_c = current_smiles.strip()
    norm_t = target_smiles.strip()
    return {"match": norm_c == norm_t, "current": norm_c, "target": norm_t}

@app.post("/tools/export")
async def export_pdf(mode: str):
    hwnd = get_chemgrid_window_handle()
    if not hwnd: return JSONResponse(status_code=404, content={"error": "ChemGrid window not found"})
    
    # 1. Select Mode
    mx, my = get_mode_button_position(hwnd, mode)
    if mx != 0 and my != 0:
        send_click_msg(hwnd, mx, my)
        time.sleep(0.5) # Wait for mode switch
    
    # 2. Trigger Export via Hotkey (F9)
    # The application has been updated to trigger PDF export on F9.
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_F9, 0)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_F9, 0)
    time.sleep(1.0) # Wait for dialog

    # 4. Handle Save Dialog
    # [Fix] Added more logging and better handling for finding the dialog
    # Sometimes dialog takes time to appear.
    
    print(f"DEBUG: Waiting for save dialog...")
    
    def save_dlg_handler(hwnd_dlg, ctx):
        if win32gui.IsWindowVisible(hwnd_dlg):
            title = win32gui.GetWindowText(hwnd_dlg)
            if "PDF" in title or "저장" in title or "Save" in title:
                print(f"DEBUG: Found dialog '{title}' ({hwnd_dlg})")
                ctx.append(hwnd_dlg)
                return False 
        return True

    found_dlg = False
    for i in range(10): # Try for 5 seconds
        ctx = []
        try:
            win32gui.EnumWindows(save_dlg_handler, ctx)
        except Exception as e:
            print(f"EnumWindows error: {e}")
            
        if ctx:
            dlg = ctx[0]
            # Found save dialog.
            # Send Enter to save with default name.
            print(f"DEBUG: Sending Enter to dialog {dlg}")
            win32api.PostMessage(dlg, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
            time.sleep(0.1)
            win32api.PostMessage(dlg, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
            found_dlg = True
            break
        time.sleep(0.5)
        
    if not found_dlg:
        print("DEBUG: Save dialog NOT found")

    return {"status": "exported", "mode": mode, "path": "Check Default Export Path"}

@app.get("/ping")
async def ping():
    return {"status": "pong", "version": "updated_v2_newfile"}

if __name__ == "__main__":
    print(f"Starting Gemini MCP Server & Tooling... (V2 New File - Port 8000)")
    uvicorn.run(app, host="127.0.0.1", port=8000)
