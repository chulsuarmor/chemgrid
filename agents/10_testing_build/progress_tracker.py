# progress_tracker.py (v1.0 - Subagent Progress Tracking)
"""
Track progress of the 100-point completion task
Reports to Discord every 30 minutes with current status
"""

import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import threading


class ProgressTracker:
    """Track task progress with periodic Discord reporting"""
    
    MODULES = {
        "NMR": {"points": 2.0, "status": "pending", "completion": 0},
        "UV-Vis": {"points": 1.5, "status": "pending", "completion": 0},
        "MD Simulation": {"points": 1.0, "status": "pending", "completion": 0},
        "Molecular Orbital": {"points": 1.5, "status": "pending", "completion": 0},
    }
    
    def __init__(self, start_points: float = 94.0, target_points: float = 100.0):
        self.start_points = start_points
        self.current_points = start_points
        self.target_points = target_points
        self.start_time = datetime.now()
        self.last_report_time = datetime.now()
        self.report_interval_seconds = 30 * 60  # 30분
        
        self.history = []
        self.load_state()
    
    def update_module_status(self, module_name: str, completion: float, status: str = "in_progress"):
        """Update module progress"""
        if module_name in self.MODULES:
            self.MODULES[module_name]["completion"] = min(100, max(0, completion))
            self.MODULES[module_name]["status"] = status
            
            # Recalculate total points
            self.recalculate_total_points()
            self.save_state()
    
    def recalculate_total_points(self):
        """Recalculate total points based on module completion"""
        earned_points = self.start_points
        
        for module_name, data in self.MODULES.items():
            module_points = data["points"]
            completion_pct = data["completion"] / 100.0
            earned_points += module_points * completion_pct
        
        self.current_points = earned_points
    
    def get_progress_summary(self) -> str:
        """Generate progress summary for reporting"""
        elapsed = datetime.now() - self.start_time
        elapsed_min = int(elapsed.total_seconds() / 60)
        
        summary = f"""
🔬 **ChemDraw Pro: 94→100점 최종 완성 진행상황**

⏱️ **진행 시간**: {elapsed_min}분
📊 **현재 점수**: {self.current_points:.1f}/100

**모듈 진행상황:**
"""
        
        total_completion = 0
        module_count = 0
        
        for module_name, data in self.MODULES.items():
            completion = data["completion"]
            status = data["status"]
            points = data["points"]
            
            # Status emoji
            if completion >= 100:
                emoji = "✅"
                status_text = "완료"
            elif completion >= 50:
                emoji = "🔄"
                status_text = "진행 중"
            else:
                emoji = "⏳"
                status_text = "대기"
            
            bar_length = int(completion / 10)
            progress_bar = "█" * bar_length + "░" * (10 - bar_length)
            
            summary += f"\n{emoji} **{module_name}** [{progress_bar}] {completion:.0f}% ({points}점)\n   상태: {status_text}"
            
            total_completion += completion
            module_count += 1
        
        overall_pct = total_completion / module_count if module_count > 0 else 0
        summary += f"\n\n📈 **전체 완성도**: {overall_pct:.0f}%"
        summary += f"\n🎯 **목표**: 6개 기능 추가 → 100/100 점"
        summary += f"\n\n**작업중...**"
        
        return summary
    
    def should_report(self) -> bool:
        """Check if it's time to report to Discord"""
        elapsed = (datetime.now() - self.last_report_time).total_seconds()
        return elapsed >= self.report_interval_seconds
    
    def mark_reported(self):
        """Mark that a report was just sent"""
        self.last_report_time = datetime.now()
    
    def save_state(self):
        """Save progress state to file"""
        state = {
            "timestamp": datetime.now().isoformat(),
            "current_points": self.current_points,
            "modules": self.MODULES,
            "elapsed_seconds": (datetime.now() - self.start_time).total_seconds()
        }
        
        filepath = Path("progress_state.json")
        try:
            with open(filepath, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[ProgressTracker] Failed to save state: {e}")
    
    def load_state(self):
        """Load progress state from file if exists"""
        filepath = Path("progress_state.json")
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    state = json.load(f)
                
                self.MODULES = state.get("modules", self.MODULES)
                self.current_points = state.get("current_points", self.current_points)
                print("[ProgressTracker] Loaded previous state")
            except Exception as e:
                print(f"[ProgressTracker] Failed to load state: {e}")


# Global instance
_progress_tracker = None


def get_tracker() -> ProgressTracker:
    """Get global progress tracker"""
    global _progress_tracker
    if _progress_tracker is None:
        _progress_tracker = ProgressTracker()
    return _progress_tracker


def report_to_discord(message: str, channel_name: str = "general"):
    """
    Send progress message to Discord
    This would integrate with the message tool if available
    """
    print(f"\n{'='*60}")
    print(f"[DISCORD REPORT - {datetime.now().strftime('%H:%M:%S')}]")
    print(f"{'='*60}")
    print(message)
    print(f"{'='*60}\n")
    
    # In real integration, this would call the message tool
    # For now, just print to console


def periodic_reporter():
    """Run periodic progress reporting"""
    tracker = get_tracker()
    
    while True:
        if tracker.should_report():
            summary = tracker.get_progress_summary()
            report_to_discord(summary)
            tracker.mark_reported()
        
        time.sleep(30)  # Check every 30 seconds


def start_periodic_reporting():
    """Start background reporting thread"""
    thread = threading.Thread(target=periodic_reporter, daemon=True)
    thread.start()
    return thread
