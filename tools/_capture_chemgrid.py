import pyautogui, time, ctypes, ctypes.wintypes
user32 = ctypes.windll.user32
hwnd = user32.FindWindowW(None, 'ChemGrid')
if hwnd == 0:
    print("ChemGrid not found, waiting 3s...")
    time.sleep(3)
    hwnd = user32.FindWindowW(None, 'ChemGrid')
if hwnd == 0:
    print("FAIL: ChemGrid window not found")
else:
    user32.SetForegroundWindow(hwnd)
    user32.ShowWindow(hwnd, 9)
    time.sleep(1)
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    l,t,r,b = rect.left, rect.top, rect.right, rect.bottom
    print(f'Window: {l},{t},{r},{b} ({r-l}x{b-t})')
    img = pyautogui.screenshot(region=(max(0,l), max(0,t), r-l, b-t))
    img.save(r'c:\chemgrid\_screenshot_v5_focused.png')
    print('Saved')
