import pyautogui, ctypes, ctypes.wintypes, time
user32 = ctypes.windll.user32
hwnd = user32.FindWindowW(None, 'ChemGrid V5')
if not hwnd:
    print("ChemGrid V5 not found!"); exit(1)
user32.SetForegroundWindow(hwnd)
time.sleep(0.5)
rect = ctypes.wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
L,T,R,B = rect.left, rect.top, rect.right, rect.bottom
print(f'Window: ({L},{T}) {R-L}x{B-T}')

# Arrow button at index 3 (Select=0, Hand=1, Bond=2, Arrow=3)
TITLEBAR = 32; ICON_W = 38
TB_Y = T + TITLEBAR + 24
ARROW_X = L + 8 + int(ICON_W * 3.5)
print(f'Clicking Arrow at ({ARROW_X}, {TB_Y})')
pyautogui.click(ARROW_X, TB_Y)
time.sleep(0.5)

img = pyautogui.screenshot(region=(max(0,L),max(0,T),R-L,B-T))
img.save(r'c:\chemgrid\_screenshot_arrow_selected.png')
print('Arrow selected screenshot saved')

# Draw arrow
CY = T + (B - T) // 2; CX1 = L + 200; CX2 = L + 600
print(f'Drawing: ({CX1},{CY}) -> ({CX2},{CY})')
pyautogui.moveTo(CX1, CY); time.sleep(0.2)
pyautogui.mouseDown(button='left'); time.sleep(0.1)
for step in range(10):
    sx = CX1 + (CX2 - CX1) * (step + 1) // 10
    pyautogui.moveTo(sx, CY, duration=0.05)
time.sleep(0.1)
pyautogui.mouseUp(button='left'); time.sleep(0.5)

img2 = pyautogui.screenshot(region=(max(0,L),max(0,T),R-L,B-T))
img2.save(r'c:\chemgrid\_screenshot_arrow_drawn.png')
print('Arrow drawn screenshot saved')
print('DONE - no crash!')
