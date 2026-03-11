import os
import shutil
import glob

BASE_DIR = r"C:\chemgrid"
SAVE_DIR = os.path.join(BASE_DIR, "save")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
BIN_DIR = os.path.join(BASE_DIR, "bin")
SRC_APP_DIR = os.path.join(BASE_DIR, "src", "app")

# Create directories
for d in [SAVE_DIR, TOOLS_DIR, BIN_DIR, SRC_APP_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)
        print(f"Created {d}")

# Move Rules
moves = [
    ("*.log", SAVE_DIR),
    ("*.txt", SAVE_DIR),
    ("*.png", SAVE_DIR),
    ("*.pdf", SAVE_DIR),
    ("*.json", SAVE_DIR),
    ("_*.py", TOOLS_DIR),
    ("*.exe", BIN_DIR),
    ("*.zip", BIN_DIR),
    ("*.bat", TOOLS_DIR), # _launch.bat 제외하고 싶지만 일단 다 옮기고 나중에 복구
]

# Exceptions
EXCEPTIONS = ["_launch.bat", "organize.py", "ChemGrid_Launcher.bat"]

for pattern, dest in moves:
    files = glob.glob(os.path.join(BASE_DIR, pattern))
    for f in files:
        if os.path.basename(f) in EXCEPTIONS:
            continue
        try:
            shutil.move(f, dest)
            print(f"Moved {f} -> {dest}")
        except Exception as e:
            print(f"Error moving {f}: {e}")

# Copy Source Code
source_origin = os.path.join(BASE_DIR, "agents", "10_testing_build", "integrated")
if os.path.exists(source_origin):
    try:
        # Recursive copy if src/app is empty
        if not os.listdir(SRC_APP_DIR):
            shutil.copytree(source_origin, SRC_APP_DIR, dirs_exist_ok=True)
            print(f"Copied source code to {SRC_APP_DIR}")
    except Exception as e:
        print(f"Error copying source: {e}")

print("Organization complete.")
