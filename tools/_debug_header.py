
print("DEBUG: Script Loaded")
try:
    with open("_early_debug.txt", "w") as f:
        f.write("Script started\n")
except Exception as e:
    print(f"DEBUG: File write failed: {e}")
