import subprocess
import os

def kill_process_by_name(process_name):
    try:
        # Use taskkill on Windows
        subprocess.run(["taskkill", "/F", "/IM", process_name], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Killed {process_name}")
    except Exception as e:
        print(f"Failed to kill {process_name}: {e}")

if __name__ == "__main__":
    print("Cleaning up previous instances...")
    # Kill ChemGrid app (draw.py is python.exe, so we can't easily kill just that script without psutil)
    # But user specifically asked to terminate existing validation program.
    # If the app is compiled exe, it's ChemGrid.exe. If python script, it's python.exe.
    # Killing python.exe is dangerous.
    
    # Try to find python processes with specific command line args using wmic
    try:
        cmd = "wmic process where \"name='python.exe' and commandline like '%draw.py%'\" call terminate"
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        cmd = "wmic process where \"name='python.exe' and commandline like '%server.py%'\" call terminate"
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    except Exception as e:
        pass

    print("Cleanup complete.")
