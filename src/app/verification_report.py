# verification_report.py (v1.0 - Calculation Verification & Reporting)
"""
ChemGrid Pro: Verification Report Module
- Verifies ORCA calculation results for consistency
- Generates structured text and JSON reports
- Checks convergence, energy bounds, and frequency sanity

Exports: VerificationEngine, VerificationReport
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class VerificationCheck:
    """Single verification check result"""
    name: str
    passed: bool
    message: str
    severity: str = "info"  # info, warning, error


@dataclass
class VerificationReport:
    """Complete verification report for a calculation"""
    calculation_id: str
    timestamp: str
    molecule_name: str
    molecule_formula: str
    smiles: str
    method: str
    basis_set: str
    checks: List[Dict] = field(default_factory=list)
    overall_pass: bool = True
    summary: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class VerificationEngine:
    """
    Engine that verifies calculation entries and produces reports.

    Usage:
        engine = VerificationEngine()
        report = engine.verify_calculation(entry)
        text = engine.generate_report_text(report)
        engine.save_report(report, output_dir)
    """

    # Reasonable energy bounds (Hartree) for common organic molecules
    ENERGY_LOWER_BOUND = -10000.0
    ENERGY_UPPER_BOUND = 0.0

    # Maximum acceptable computation time (seconds) before warning
    MAX_REASONABLE_TIME = 86400  # 24 hours

    def verify_calculation(self, entry) -> VerificationReport:
        """
        Run all verification checks on a CalculationEntry.

        Args:
            entry: A CalculationEntry (from calculation_logger.py) or dict-like object

        Returns:
            VerificationReport with all check results
        """
        # Support both dataclass and dict inputs
        if hasattr(entry, 'to_dict'):
            d = entry.to_dict()
        elif isinstance(entry, dict):
            d = entry
        else:
            d = vars(entry) if hasattr(entry, '__dict__') else {}

        # N-code type guard: ensure d is dict before .get() calls
        if not isinstance(d, dict):
            logger.warning("verify_calculation: entry converted to non-dict type=%s, using empty dict", type(d).__name__)
            d = {}

        report = VerificationReport(
            calculation_id=d.get('id', 'unknown'),
            timestamp=datetime.now().isoformat(),
            molecule_name=d.get('molecule_name', d.get('formula', 'Unknown')),
            molecule_formula=d.get('molecule_formula', d.get('formula', '')),
            smiles=d.get('smiles', ''),
            method=d.get('method', 'Unknown'),
            basis_set=d.get('basis_set', 'Unknown'),
        )

        checks = []

        # 1. Status check
        checks.append(self._check_status(d))

        # 2. Energy sanity check
        checks.append(self._check_energy(d))

        # 3. SCF convergence check
        checks.append(self._check_scf_convergence(d))

        # 4. Geometry convergence check (if optimization)
        checks.append(self._check_geometry_convergence(d))

        # 5. Frequency check (imaginary frequencies)
        checks.append(self._check_frequencies(d))

        # 6. Computation time check
        checks.append(self._check_computation_time(d))

        # 7. Output file existence check
        checks.append(self._check_output_files(d))

        report.checks = [asdict(c) for c in checks]
        report.overall_pass = all(c.passed for c in checks if c.severity == "error")

        # Build summary
        n_pass = sum(1 for c in checks if c.passed)
        n_fail = sum(1 for c in checks if not c.passed)
        n_warn = sum(1 for c in checks if not c.passed and c.severity == "warning")
        n_err = sum(1 for c in checks if not c.passed and c.severity == "error")

        report.summary = (
            f"Verification complete: {n_pass} passed, {n_fail} issues "
            f"({n_err} errors, {n_warn} warnings)"
        )

        return report

    def _check_status(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_status: expected dict, got %s", type(d).__name__)
            return VerificationCheck("Status", False, "Invalid entry data type", severity="error")
        status = d.get('status', 'unknown')
        if not isinstance(status, str):
            status = str(status) if status is not None else 'unknown'
        if status in ('completed', 'converged'):
            return VerificationCheck("Status", True, f"Calculation status: {status}")
        elif status in ('unconverged', 'failed'):
            return VerificationCheck("Status", False,
                f"Calculation status: {status}", severity="error")
        else:
            return VerificationCheck("Status", True,
                f"Calculation status: {status} (non-critical)", severity="info")

    def _check_energy(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_energy: expected dict, got %s", type(d).__name__)
            return VerificationCheck("Energy", False, "Invalid entry data type", severity="error")
        energy = d.get('final_energy')
        if energy is None:
            return VerificationCheck("Energy", True,
                "No energy data available (skipped)", severity="info")
        try:
            e = float(energy)
            if self.ENERGY_LOWER_BOUND <= e <= self.ENERGY_UPPER_BOUND:
                return VerificationCheck("Energy", True,
                    f"Energy {e:.6f} Ha within reasonable bounds")
            else:
                return VerificationCheck("Energy", False,
                    f"Energy {e:.6f} Ha outside expected range "
                    f"[{self.ENERGY_LOWER_BOUND}, {self.ENERGY_UPPER_BOUND}]",
                    severity="warning")
        except (ValueError, TypeError):
            return VerificationCheck("Energy", False,
                f"Invalid energy value: {energy}", severity="error")

    def _check_scf_convergence(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_scf_convergence: expected dict, got %s", type(d).__name__)
            return VerificationCheck("SCF Convergence", False, "Invalid entry data type", severity="error")
        scf = d.get('scf_converged')
        if scf is None:
            return VerificationCheck("SCF Convergence", True,
                "SCF convergence data not available (skipped)", severity="info")
        if scf:
            return VerificationCheck("SCF Convergence", True, "SCF converged")
        return VerificationCheck("SCF Convergence", False,
            "SCF did NOT converge", severity="error")

    def _check_geometry_convergence(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_geometry_convergence: expected dict, got %s", type(d).__name__)
            return VerificationCheck("Geometry Convergence", False, "Invalid entry data type", severity="error")
        task = d.get('task', '')
        if not isinstance(task, str):
            task = str(task) if task is not None else ''
        geo = d.get('geometry_converged')
        if 'opt' not in task.lower():
            return VerificationCheck("Geometry Convergence", True,
                "Not an optimization task (skipped)", severity="info")
        if geo is None:
            return VerificationCheck("Geometry Convergence", True,
                "Geometry convergence data not available", severity="info")
        if geo:
            return VerificationCheck("Geometry Convergence", True,
                "Geometry converged")
        return VerificationCheck("Geometry Convergence", False,
            "Geometry did NOT converge", severity="error")

    def _check_frequencies(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_frequencies: expected dict, got %s", type(d).__name__)
            return VerificationCheck("Frequencies", False, "Invalid entry data type", severity="error")
        freq_status = d.get('frequency_status', 'not_computed')
        if not isinstance(freq_status, str):
            freq_status = str(freq_status) if freq_status is not None else 'not_computed'
        if freq_status == 'not_computed':
            return VerificationCheck("Frequencies", True,
                "Frequencies not computed (skipped)", severity="info")
        if freq_status == 'all_positive':
            return VerificationCheck("Frequencies", True,
                "All frequencies positive (true minimum)")
        if freq_status == 'imaginary_present':
            return VerificationCheck("Frequencies", False,
                "Imaginary frequencies detected (not a true minimum)",
                severity="warning")
        return VerificationCheck("Frequencies", True,
            f"Frequency status: {freq_status}", severity="info")

    def _check_computation_time(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_computation_time: expected dict, got %s", type(d).__name__)
            return VerificationCheck("Computation Time", False, "Invalid entry data type", severity="error")
        t = d.get('computation_time', 0)
        try:
            t = float(t)
        except (ValueError, TypeError):
            t = 0
        if t <= 0:
            return VerificationCheck("Computation Time", True,
                "No timing data available", severity="info")
        if t > self.MAX_REASONABLE_TIME:
            return VerificationCheck("Computation Time", False,
                f"Computation took {t:.0f}s (>{self.MAX_REASONABLE_TIME}s)",
                severity="warning")
        return VerificationCheck("Computation Time", True,
            f"Computation time: {t:.1f}s")

    def _check_output_files(self, d: Dict) -> VerificationCheck:
        if not isinstance(d, dict):
            logger.warning("_check_output_files: expected dict, got %s", type(d).__name__)
            return VerificationCheck("Output File", False, "Invalid entry data type", severity="error")
        out = d.get('output_file')
        if not isinstance(out, str):
            out = str(out) if out is not None else None
        if not out:
            return VerificationCheck("Output File", True,
                "No output file path recorded (skipped)", severity="info")
        if os.path.isfile(out):
            return VerificationCheck("Output File", True,
                f"Output file exists: {out}")
        return VerificationCheck("Output File", False,
            f"Output file missing: {out}", severity="warning")

    def generate_report_text(self, report: VerificationReport) -> str:
        """
        Generate a human-readable text report.

        Args:
            report: VerificationReport from verify_calculation()

        Returns:
            Formatted text string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("ChemGrid Verification Report")
        lines.append("=" * 70)
        lines.append(f"Generated: {report.timestamp}")
        lines.append(f"Calculation ID: {report.calculation_id}")
        lines.append("")
        lines.append(f"Molecule: {report.molecule_name}")
        lines.append(f"Formula:  {report.molecule_formula}")
        if report.smiles:
            lines.append(f"SMILES:   {report.smiles}")
        lines.append(f"Method:   {report.method} / {report.basis_set}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("Verification Checks")
        lines.append("-" * 70)

        for check in report.checks:
            status = "PASS" if check['passed'] else "FAIL"
            icon = "[+]" if check['passed'] else "[-]"
            sev = f" ({check['severity']})" if not check['passed'] else ""
            lines.append(f"  {icon} {check['name']}: {status}{sev}")
            lines.append(f"      {check['message']}")

        lines.append("")
        lines.append("-" * 70)
        lines.append(f"Overall: {'PASS' if report.overall_pass else 'FAIL'}")
        lines.append(report.summary)
        lines.append("=" * 70)

        return "\n".join(lines)

    def save_report(self, report: VerificationReport, output_dir: Path) -> Tuple[str, str]:
        """
        Save the report as both JSON and text files.

        Args:
            report: VerificationReport to save
            output_dir: Directory to write the files

        Returns:
            Tuple of (json_path, text_path)
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"verification_report_{ts}"

        json_path = output_dir / f"{base}.json"
        text_path = output_dir / f"{base}.txt"

        # JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # Text
        text = self.generate_report_text(report)
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)

        return str(json_path), str(text_path)
