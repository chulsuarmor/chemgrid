import pyautogui, ctypes, ctypes.wintypes, time, os, json, math

pyautogui.FAILSAFE = False
RESULTS = {}

def find_window():
    user32 = ctypes.windll.user32
    # The title in toolbar_setup.py is "ChemGrid V5"
    hwnd = user32.FindWindowW(None, 'ChemGrid V5')
    if not hwnd:
        hwnd = user32.FindWindowW(None, 'ChemGrid')
    if not hwnd:
        print("FATAL: ChemGrid window not found!")
        return None, 0, 0, 0, 0
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, rect.left, rect.top, rect.right, rect.bottom

def screenshot(name):
    hwnd, L, T, R, B = find_window()
    if not hwnd: return ""
    # Capture the whole window
    img = pyautogui.screenshot(region=(max(0,L),max(0,T),R-L,B-T))
    path = rf'c:\chemgrid\_benzene_nitro_{name}.png'
    img.save(path)
    print(f'  📸 {name} saved to {path}')
    return path

def click_toolbar(index, row=1):
    hwnd, L, T, R, B = find_window()
    if not hwnd: return
    TITLEBAR = 32
    ICON_W = 34 if row == 1 else 20 # based on toolbar_setup sizes
    # Based on _full_verification.py logic
    if row == 1:
        y = T + TITLEBAR + 24
        x = L + 40 + int(34 * index) # Adjusted for setup_toolbars logic
    else:
        y = T + TITLEBAR + 58 + 14
        x = L + 8 + int(ICON_W * (index + 0.5))
    pyautogui.click(x, y)
    time.sleep(0.3)

def get_canvas_rect():
    hwnd, L, T, R, B = find_window()
    TOOLBAR_H = 100 
    canvas_top = T + TOOLBAR_H
    canvas_h = B - canvas_top - 60
    canvas_w = R - L
    return L, T, R, B, canvas_top, canvas_w, canvas_h

def canvas_to_abs(rel_x, rel_y):
    L, T, R, B, ct, cw, ch = get_canvas_rect()
    return L + int(cw * rel_x), ct + int(ch * rel_y)

def drag_rel(x1, y1, x2, y2):
    ax1, ay1 = canvas_to_abs(x1, y1)
    ax2, ay2 = canvas_to_abs(x2, y2)
    pyautogui.moveTo(ax1, ay1)
    pyautogui.mouseDown()
    pyautogui.moveTo(ax2, ay2, duration=0.2)
    pyautogui.mouseUp()
    time.sleep(0.2)

def click_rel(rx, ry):
    ax, ay = canvas_to_abs(rx, ry)
    pyautogui.click(ax, ay)
    time.sleep(0.2)

def click_bottom_button(name):
    hwnd, L, T, R, B = find_window()
    if name == "lewis":
        x, y = R - 200, B - 30
    elif name == "theory":
        x, y = R - 80, B - 30
    elif name == "cloud":
        x, y = L + 60, B - 30
    else:
        return
    pyautogui.click(x, y)
    time.sleep(1.0)

# Main Script
print("Starting Benzene Nitration Verification...")
hwnd, L, T, R, B = find_window()
if not hwnd:
    exit(1)

# Ensure blank canvas
pyautogui.hotkey('ctrl', 'a')
pyautogui.press('delete')
time.sleep(0.5)

# 1. Draw Benzene Ring (6 bonds)
print("Drawing Benzene...")
click_toolbar(2) # Bond tool
cx, cy = 0.5, 0.4
r = 0.1 # radius
points = []
for i in range(6):
    angle = math.radians(i * 60 - 30)
    points.append((cx + r * math.cos(angle), cy + r * math.sin(angle) * 1.5)) # Adjust for aspect

for i in range(6):
    p1 = points[i]
    p2 = points[(i+1)%6]
    drag_rel(p1[0], p1[1], p2[0], p2[1])
    # For benzene, add double bonds to every second bond
    if i % 2 == 0:
        # Repeat drag to make it double if the app supports it, 
        # but usually you just drag again slightly inside.
        # Let's just draw the single ring first.
        pass

# Add double bonds
for i in [0, 2, 4]:
    p1 = points[i]
    p2 = points[(i+1)%6]
    # draw slightly inside
    in_r = r * 0.8
    angle1 = math.radians(i * 60 - 30)
    angle2 = math.radians((i+1) * 60 - 30)
    ip1 = (cx + in_r * math.cos(angle1), cy + in_r * math.sin(angle1) * 1.5)
    ip2 = (cx + in_r * math.cos(angle2), cy + in_r * math.sin(angle2) * 1.5)
    drag_rel(ip1[0], ip1[1], ip2[0], ip2[1])

screenshot("01_benzene_drawn")

# 2. Add Nitro Group (NO2)
print("Adding Nitro Group...")
# N is index 10 in chem_tools: H(0), R(1), LP(2), Rad(3), +(4), -(5), O(6), N(7)...
# Wait, toolbar_setup: "H", "R", "LonePair", "Radical", "Positive", "Negative", "O", "N", "P", "S"...
# 0:H, 1:R, 2:LP, 3:Radical, 4:Pos, 5:Neg, 6:O, 7:N
# chem_tools start after Bond(2), Arrow(3), Pen(4), Text(5), Eraser(6), Dash, Wedge
# Let's count properly:
# Select(0), Hand(1), Bond(2), Arrow(3), Pen(4), Text(5), Eraser(6), Sep(internal), Dash(7), Wedge(8), Sep, H(9), R(10)... N is 16?
# No, let's use the click_toolbar precisely.
# Setup: window.tb.addAction(grp actions...)
# Select, Hand, Bond, Arrow, Pen, Text, Eraser, Dash, Wedge, H, R, LonePair, Radical, Positive, Negative, O, N
# Indices: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
# N = 16, O = 15

# Click Top vertex to add N
click_toolbar(16) 
click_rel(points[1][0], points[1][1]) # point index 1 is top-right-ish if starting from -30deg

# Extend to O
click_toolbar(2) # Bond
drag_rel(points[1][0], points[1][1], points[1][0], points[1][1] - 0.1) # N-O bond
drag_rel(points[1][0], points[1][1], points[1][0] + 0.05, points[1][1] - 0.08) # N-O bond

# Set atoms to O
click_toolbar(15) # O
click_rel(points[1][0], points[1][1] - 0.1)
click_rel(points[1][0] + 0.05, points[1][1] - 0.08)

screenshot("02_nitro_added")

# 3. Verify Layers
print("Verifying Layers...")
click_bottom_button("lewis")
screenshot("03_lewis")

click_bottom_button("theory")
screenshot("04_theory")

# Back to drawing
click_bottom_button("theory") # Toggle back
time.sleep(0.5)

print("Verification script finished.")
