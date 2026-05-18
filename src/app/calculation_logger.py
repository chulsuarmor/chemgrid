# calculation_logger.py (v1.0 - Calculation History & Logging)
"""
ChemGrid Pro Phase 5: Calculation Logger
- JSON-based ORCA calculation history tracking
- Real-time computation status monitoring
- Output file validation and hash verification
- Calculation time and resource tracking
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict, field
from enum import Enum


class CalculationStatus(Enum):
    """Calculation status codes"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CONVERGED = "converged"
    UNCONVERGED = "unconverged"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CalculationEntry:
    """Single calculation entry"""
    id: str
    timestamp: str
    molecule_name: str
    molecule_formula: str
    smiles: str = ""
    
    # Calculation settings
    method: str = "B3LYP"
    basis_set: str = "6-31G(d)"
    task: str = "SinglePoint"  # SinglePoint, Opt, Freq, OptFreq
    multiplicity: int = 1
    charge: int = 0
    
    # Calculation status
    status: str = "pending"
    started_time: str = None
    finished_time: str = None
    computation_time: float = 0.0  # seconds
    
    # Results
    final_energy: float = None
    zero_point_energy: float = None
    enthalpy: float = None
    gibbs_free_energy: float = None
    
    # Convergence info
    scf_converged: bool = False
    geometry_converged: bool = False
    frequency_status: str = "not_computed"
    
    # File tracking
    input_file: str = None
    output_file: str = None
    output_file_hash: str = None
    gbw_file: str = None
    gbw_file_hash: str = None
    
    # Metadata
    software_version: str = "ORCA 5.0+"
    chemgrid_version: str = "ChemGrid Pro v2.0"
    error_message: str = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CalculationEntry':
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CalculationLogger:
    """Log and manage ORCA calculations"""
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize logger
        
        Args:
            log_file: Path to JSON log file (default: ./calculation_history.json)
        """
        if log_file is None:
            log_file = Path.cwd() / "calculation_history.json"
        else:
            log_file = Path(log_file)
        
        self.log_file = log_file
        self.entries: Dict[str, CalculationEntry] = {}
        self.load_history()
    
    def load_history(self):
        """Load calculation history from JSON file"""
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for entry_id, entry_data in data.items():
                        self.entries[entry_id] = CalculationEntry.from_dict(entry_data)
            except Exception as e:
                print(f"Warning: Could not load calculation history: {e}")
    
    def save_history(self):
        """Save calculation history to JSON file"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                data = {k: v.to_dict() for k, v in self.entries.items()}
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error: Could not save calculation history: {e}")
    
    def create_entry(self, 
                    molecule_name: str,
                    molecule_formula: str,
                    method: str = "B3LYP",
                    basis_set: str = "6-31G(d)",
                    task: str = "SinglePoint",
                    **kwargs) -> str:
        """
        Create new calculation entry
        
        Returns:
            Entry ID (timestamp-based)
        """
        entry_id = self._generate_id()
        
        entry = CalculationEntry(
            id=entry_id,
            timestamp=datetime.now().isoformat(),
            molecule_name=molecule_name,
            molecule_formula=molecule_formula,
            method=method,
            basis_set=basis_set,
            task=task,
            **kwargs
        )
        
        self.entries[entry_id] = entry
        self.save_history()
        return entry_id
    
    def start_calculation(self, entry_id: str, input_file: str):
        """Mark calculation as started"""
        if entry_id not in self.entries:
            raise ValueError(f"Entry {entry_id} not found")
        
        entry = self.entries[entry_id]
        entry.status = CalculationStatus.RUNNING.value
        entry.started_time = datetime.now().isoformat()
        entry.input_file = str(input_file)
        self.save_history()
    
    def finish_calculation(self, entry_id: str, 
                          output_file: str,
                          converged: bool = False,
                          final_energy: float = None,
                          scf_converged: bool = False,
                          geometry_converged: bool = False,
                          error_message: str = None):
        """Mark calculation as finished and log results"""
        if entry_id not in self.entries:
            raise ValueError(f"Entry {entry_id} not found")
        
        entry = self.entries[entry_id]
        entry.finished_time = datetime.now().isoformat()
        entry.output_file = str(output_file)
        entry.computation_time = self._calculate_computation_time(entry)
        
        # Verify output file exists and create hash
        output_path = Path(output_file)
        if output_path.exists():
            entry.output_file_hash = self._file_hash(output_path)
        
        # Set convergence and energy info
        entry.scf_converged = scf_converged
        entry.geometry_converged = geometry_converged
        entry.final_energy = final_energy
        
        if converged:
            entry.status = CalculationStatus.CONVERGED.value
        elif error_message:
            entry.status = CalculationStatus.FAILED.value
            entry.error_message = error_message
        else:
            entry.status = CalculationStatus.UNCONVERGED.value
        
        self.save_history()
    
    def update_entry(self, entry_id: str, **kwargs):
        """Update entry fields"""
        if entry_id not in self.entries:
            raise ValueError(f"Entry {entry_id} not found")
        
        entry = self.entries[entry_id]
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        
        self.save_history()
    
    def get_entry(self, entry_id: str) -> Optional[CalculationEntry]:
        """Get single entry"""
        return self.entries.get(entry_id)
    
    def get_all_entries(self) -> List[CalculationEntry]:
        """Get all entries"""
        return list(self.entries.values())
    
    def get_entries_by_molecule(self, molecule_formula: str) -> List[CalculationEntry]:
        """Get all entries for specific molecule"""
        return [e for e in self.entries.values() 
                if e.molecule_formula == molecule_formula]
    
    def get_entries_by_status(self, status: CalculationStatus) -> List[CalculationEntry]:
        """Get entries by status"""
        status_str = status.value if isinstance(status, CalculationStatus) else status
        return [e for e in self.entries.values() if e.status == status_str]
    
    def get_statistics(self) -> Dict:
        """Get calculation statistics"""
        entries = list(self.entries.values())
        if not entries:
            return {}
        
        completed = [e for e in entries if e.status in [
            CalculationStatus.COMPLETED.value,
            CalculationStatus.CONVERGED.value
        ]]
        
        return {
            "total_calculations": len(entries),
            "completed": len(completed),
            "success_rate": len(completed) / len(entries) if entries else 0,
            "total_computation_time": sum(e.computation_time for e in entries),
            "average_computation_time": sum(e.computation_time for e in entries) / len(entries) if entries else 0,
            "unique_molecules": len(set(e.molecule_formula for e in entries)),
            "methods_used": list(set(e.method for e in entries)),
            "basis_sets_used": list(set(e.basis_set for e in entries)),
        }
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """
        Generate human-readable calculation report
        
        Returns:
            Report text (and optionally saves to file)
        """
        lines = []
        lines.append("=" * 70)
        lines.append("CALCULATION HISTORY REPORT")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("=" * 70)
        lines.append("")
        
        # Statistics
        stats = self.get_statistics()
        lines.append("STATISTICS")
        lines.append("-" * 70)
        lines.append(f"Total Calculations: {stats.get('total_calculations', 0)}")
        lines.append(f"Completed: {stats.get('completed', 0)}")
        lines.append(f"Success Rate: {stats.get('success_rate', 0):.1%}")
        lines.append(f"Total Computation Time: {stats.get('total_computation_time', 0):.2f} s")
        lines.append(f"Average Computation Time: {stats.get('average_computation_time', 0):.2f} s")
        lines.append(f"Unique Molecules: {stats.get('unique_molecules', 0)}")
        lines.append("")
        
        # Detailed entries
        lines.append("DETAILED ENTRIES")
        lines.append("-" * 70)
        for entry in sorted(self.entries.values(), key=lambda e: e.timestamp, reverse=True):
            lines.append(f"ID: {entry.id}")
            lines.append(f"  Molecule: {entry.molecule_name} ({entry.molecule_formula})")
            lines.append(f"  Method: {entry.method}/{entry.basis_set}")
            lines.append(f"  Task: {entry.task}")
            lines.append(f"  Status: {entry.status}")
            if entry.started_time:
                lines.append(f"  Started: {entry.started_time}")
            if entry.finished_time:
                lines.append(f"  Finished: {entry.finished_time}")
                lines.append(f"  Computation Time: {entry.computation_time:.2f} s")
            if entry.final_energy is not None:
                lines.append(f"  Final Energy: {entry.final_energy:.8f} Hartree")
            if entry.error_message:
                lines.append(f"  Error: {entry.error_message}")
            lines.append("")
        
        report = "\n".join(lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        
        return report
    
    def _generate_id(self) -> str:
        """Generate unique entry ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        counter = 1
        base_id = timestamp
        while base_id in self.entries:
            counter += 1
            base_id = f"{timestamp}_{counter}"
        return base_id
    
    def _calculate_computation_time(self, entry: CalculationEntry) -> float:
        """Calculate computation time from timestamps"""
        if not entry.started_time or not entry.finished_time:
            return 0.0
        
        try:
            start = datetime.fromisoformat(entry.started_time)
            finish = datetime.fromisoformat(entry.finished_time)
            return (finish - start).total_seconds()
        except (ValueError, TypeError):
            return 0.0
    
    @staticmethod
    def _file_hash(file_path: Path, algorithm: str = 'sha256') -> str:
        """Calculate file hash"""
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    
    def verify_calculation(self, entry_id: str) -> Dict[str, bool]:
        """
        Verify calculation integrity
        
        Returns:
            Dict of verification checks
        """
        if entry_id not in self.entries:
            return {"exists": False}
        
        entry = self.entries[entry_id]
        checks = {
            "exists": True,
            "output_file_exists": False,
            "gbw_file_exists": False,
            "output_hash_matches": False,
            "gbw_hash_matches": False,
            "scf_converged": entry.scf_converged,
            "geometry_converged": entry.geometry_converged,
            "energy_reasonable": entry.final_energy is not None and entry.final_energy < 0,
        }
        
        # Check output file
        if entry.output_file and Path(entry.output_file).exists():
            checks["output_file_exists"] = True
            current_hash = self._file_hash(Path(entry.output_file))
            checks["output_hash_matches"] = (current_hash == entry.output_file_hash)
        
        # Check GBW file
        if entry.gbw_file and Path(entry.gbw_file).exists():
            checks["gbw_file_exists"] = True
            current_hash = self._file_hash(Path(entry.gbw_file))
            checks["gbw_hash_matches"] = (current_hash == entry.gbw_file_hash)
        
        return checks
    
    def cleanup_old_entries(self, days: int = 30):
        """Remove entries older than specified days"""
        cutoff_date = datetime.now().timestamp() - (days * 86400)
        
        to_remove = []
        for entry_id, entry in self.entries.items():
            entry_time = datetime.fromisoformat(entry.timestamp).timestamp()
            if entry_time < cutoff_date:
                to_remove.append(entry_id)
        
        for entry_id in to_remove:
            del self.entries[entry_id]
        
        if to_remove:
            self.save_history()
        
        return len(to_remove)
