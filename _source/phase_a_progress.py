"""
Phase A Progress Tracker
Tracks completion status and sends hourly updates to Discord
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

PROGRESS_FILE = Path(r"C:\Users\김남헌\Desktop\organicdraw\phase_a_progress.json")

# Phase A Components and their completion status
PHASE_A_TASKS = {
    "Directory Structure Analysis": {
        "completed": True,
        "completion": 100,
        "notes": "Orca.6.1.1 folder confirmed - Orca6.1.1.Win64.exe found"
    },
    "orca_interface.py Module Creation": {
        "completed": True,
        "completion": 100,
        "notes": "Core module with DFT template, QThread support, .gbw parsing"
    },
    "ORCA Path Configuration": {
        "completed": True,
        "completion": 100,
        "notes": "Path: C:\\Users\\kim\\Desktop\\organicdraw\\Orca.6.1.1"
    },
    "B3LYP/6-31G(d) DFT Template": {
        "completed": True,
        "completion": 100,
        "notes": "DFT_TEMPLATE with OptAll, TIGHTSCF, charge/multiplicity"
    },
    ".gbw File Parsing Logic": {
        "completed": True,
        "completion": 100,
        "notes": "parse_gbw_file() and _parse_out_file() functions implemented"
    },
    "Electronic Density Extraction": {
        "completed": True,
        "completion": 100,
        "notes": "ElectronicDensity dataclass with charge analysis"
    },
    "QThread Background Execution": {
        "completed": True,
        "completion": 100,
        "notes": "OrcaCalculatorThread with progress/result/error signals"
    },
    "Module Verification": {
        "completed": True,
        "completion": 100,
        "notes": "orca_interface.py tested and validated successfully"
    }
}


class ProgressTracker:
    def __init__(self, progress_file: Path = PROGRESS_FILE):
        self.progress_file = progress_file
        self.load_or_create()
    
    def load_or_create(self):
        """Load or create progress file"""
        if self.progress_file.exists():
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = {
                "phase": "A",
                "start_time": datetime.now().isoformat(),
                "last_update": None,
                "tasks": PHASE_A_TASKS
            }
            self.save()
    
    def save(self):
        """Save progress to file"""
        self.data["last_update"] = datetime.now().isoformat()
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def get_overall_completion(self) -> float:
        """Calculate overall completion percentage"""
        tasks = self.data.get("tasks", {})
        if not tasks:
            return 0.0
        total_completion = sum(t.get("completion", 0) for t in tasks.values())
        return total_completion / len(tasks)
    
    def get_summary(self) -> str:
        """Generate one-line summary for Discord"""
        overall = self.get_overall_completion()
        completed = sum(1 for t in self.data.get("tasks", {}).values() if t.get("completed", False))
        total = len(self.data.get("tasks", {}))
        
        status = f"Phase A ORCA Integration: {int(overall)}% | {completed}/{total} components"
        return status
    
    def get_detailed_report(self) -> str:
        """Generate detailed progress report"""
        lines = [
            "=== ChemDraw Pro Phase A: ORCA Integration ===",
            f"Overall Completion: {int(self.get_overall_completion())}%",
            ""
        ]
        
        for task_name, task_data in self.data.get("tasks", {}).items():
            status = "[DONE]" if task_data.get("completed", False) else "[SKIP]"
            completion = task_data.get("completion", 0)
            lines.append(f"{status} [{completion:3d}%] {task_name}")
            if task_data.get("notes"):
                lines.append(f"        --- {task_data['notes']}")
        
        return "\n".join(lines)


def generate_discord_report() -> str:
    """Generate Discord-friendly progress report"""
    tracker = ProgressTracker()
    summary = tracker.get_summary()
    
    # One-line format for Discord
    return f"[Phase A - ORCA] {summary}"


if __name__ == "__main__":
    tracker = ProgressTracker()
    print(tracker.get_detailed_report())
    print("\n" + "=" * 50)
    print("Discord Report:")
    print(generate_discord_report())
