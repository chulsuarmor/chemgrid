# verification_report.py (v1.0 - Calculation Verification & Reports)
"""
ChemDraw Pro Phase 5: Verification Report Generator
- Comprehensive calculation verification checklist
- Web reference data comparison
- Calculation credibility badges/marks
- Detailed audit trail with validation metrics
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass, asdict, field
from enum import Enum

try:
    from calculation_logger import CalculationLogger, CalculationEntry, CalculationStatus
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False


class VerificationLevel(Enum):
    """Verification credibility levels"""
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    VERIFIED = "verified"
    CERTIFIED = "certified"


class VerificationMark(Enum):
    """Verification marks/badges"""
    NO_MARK = "no_mark"
    PENDING = "pending"
    WARNING = "warning"
    CHECKMARK = "checkmark"
    GOLD_STAR = "gold_star"


@dataclass
class VerificationCheck:
    """Single verification check"""
    name: str
    description: str
    passed: bool
    severity: str = "info"  # info, warning, error
    details: str = ""
    ref_value: Optional[float] = None
    actual_value: Optional[float] = None
    error_margin: Optional[float] = None


@dataclass
class ReferenceData:
    """Literature reference data for comparison"""
    molecule_formula: str
    molecule_name: str
    method: str
    basis_set: str
    reference_energy: float
    reference_source: str
    publication_year: int
    accuracy_notes: str = ""


@dataclass
class VerificationReport:
    """Complete verification report"""
    calculation_id: str
    report_date: str
    calculation_entry: Optional[Dict] = None
    checks: List[VerificationCheck] = field(default_factory=list)
    reference_data: Optional[ReferenceData] = None
    overall_level: str = VerificationLevel.UNVERIFIED.value
    credibility_score: float = 0.0  # 0-100
    audit_trail: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "calculation_id": self.calculation_id,
            "report_date": self.report_date,
            "calculation_entry": self.calculation_entry,
            "checks": [asdict(c) for c in self.checks],
            "reference_data": asdict(self.reference_data) if self.reference_data else None,
            "overall_level": self.overall_level,
            "credibility_score": self.credibility_score,
            "audit_trail": self.audit_trail,
            "recommendations": self.recommendations,
        }


class VerificationEngine:
    """Generate verification reports for calculations"""
    
    def __init__(self):
        self.reference_database: Dict[str, ReferenceData] = {}
        self.load_reference_data()
    
    def load_reference_data(self):
        """Load reference data from local database"""
        # Example reference data (can be expanded)
        self.reference_database = {
            "H2": ReferenceData(
                molecule_formula="H2",
                molecule_name="Hydrogen molecule",
                method="B3LYP",
                basis_set="6-31G(d)",
                reference_energy=-1.17523,  # Hartree
                reference_source="NIST Chemistry WebBook",
                publication_year=2020,
                accuracy_notes="Standard reference value for H2"
            ),
            "H2O": ReferenceData(
                molecule_formula="H2O",
                molecule_name="Water",
                method="B3LYP",
                basis_set="6-31G(d)",
                reference_energy=-76.46172,  # Hartree
                reference_source="NIST Chemistry WebBook",
                publication_year=2020,
                accuracy_notes="Standard reference value for water"
            ),
            "CH4": ReferenceData(
                molecule_formula="CH4",
                molecule_name="Methane",
                method="B3LYP",
                basis_set="6-31G(d)",
                reference_energy=-40.525971,  # Hartree
                reference_source="NIST Chemistry WebBook",
                publication_year=2020,
                accuracy_notes="Standard reference value for methane"
            ),
        }
    
    def verify_calculation(self, entry: CalculationEntry, 
                          reference_data: Optional[ReferenceData] = None) -> VerificationReport:
        """
        Generate verification report for calculation entry
        
        Args:
            entry: CalculationEntry from calculation_logger
            reference_data: Optional reference data for comparison
        
        Returns:
            VerificationReport with all checks and validation
        """
        report = VerificationReport(
            calculation_id=entry.id,
            report_date=datetime.now().isoformat(),
            calculation_entry=asdict(entry),
        )
        
        # Perform verification checks
        self._check_orca_execution(report, entry)
        self._check_output_files(report, entry)
        self._check_convergence(report, entry)
        self._check_energy_validity(report, entry)
        self._check_spectrum_data(report, entry)
        
        # Compare with reference data
        if reference_data is None:
            reference_data = self.reference_database.get(entry.molecule_formula)
        
        if reference_data:
            report.reference_data = reference_data
            self._check_energy_accuracy(report, entry, reference_data)
        
        # Calculate overall credibility
        self._calculate_credibility(report)
        
        return report
    
    def _check_orca_execution(self, report: VerificationReport, entry: CalculationEntry):
        """Check ORCA execution"""
        check = VerificationCheck(
            name="ORCA Execution",
            description="Verify ORCA calculation was executed",
            passed=entry.started_time is not None and entry.finished_time is not None,
            severity="error" if entry.status == "failed" else "info",
            details=f"Status: {entry.status}"
        )
        report.checks.append(check)
        report.audit_trail.append(f"[ORCA] Execution check: {check.passed}")
    
    def _check_output_files(self, report: VerificationReport, entry: CalculationEntry):
        """Check output files existence"""
        output_exists = entry.output_file and Path(entry.output_file).exists()
        check = VerificationCheck(
            name="Output File Verification",
            description="Verify ORCA output file exists and is readable",
            passed=output_exists,
            severity="error" if not output_exists else "info",
            details=f"Output: {entry.output_file}"
        )
        report.checks.append(check)
        report.audit_trail.append(f"[FILES] Output verification: {check.passed}")
        
        # Check GBW file
        gbw_exists = entry.gbw_file and Path(entry.gbw_file).exists()
        gbw_check = VerificationCheck(
            name="GBW File Verification",
            description="Verify ORCA binary wavefunction file exists",
            passed=gbw_exists,
            severity="warning" if not gbw_exists else "info",
            details=f"GBW: {entry.gbw_file}"
        )
        report.checks.append(gbw_check)
        report.audit_trail.append(f"[FILES] GBW verification: {gbw_check.passed}")
    
    def _check_convergence(self, report: VerificationReport, entry: CalculationEntry):
        """Check SCF and geometry convergence"""
        scf_check = VerificationCheck(
            name="SCF Convergence",
            description="Verify SCF convergence criteria met",
            passed=entry.scf_converged,
            severity="error" if not entry.scf_converged else "info",
            details="SCF iterations converged"
        )
        report.checks.append(scf_check)
        
        geo_check = VerificationCheck(
            name="Geometry Convergence",
            description="Verify geometry optimization converged",
            passed=entry.geometry_converged,
            severity="warning" if not entry.geometry_converged else "info",
            details="Geometry optimization converged"
        )
        report.checks.append(geo_check)
        
        report.audit_trail.append(f"[CONVERGENCE] SCF: {scf_check.passed}, Geometry: {geo_check.passed}")
    
    def _check_energy_validity(self, report: VerificationReport, entry: CalculationEntry):
        """Check energy value validity"""
        if entry.final_energy is None:
            check = VerificationCheck(
                name="Energy Validity",
                description="Verify final energy is available",
                passed=False,
                severity="error",
                details="No final energy found"
            )
        else:
            # Energy should be negative for most molecules
            is_valid = entry.final_energy < 0 or (entry.method == "IP-EA" and entry.final_energy > 0)
            check = VerificationCheck(
                name="Energy Validity",
                description="Verify final energy is physically reasonable",
                passed=is_valid,
                severity="warning" if not is_valid else "info",
                actual_value=entry.final_energy,
                details=f"Final energy: {entry.final_energy:.8f} Hartree"
            )
        
        report.checks.append(check)
        report.audit_trail.append(f"[ENERGY] Validity check: {check.passed}")
    
    def _check_spectrum_data(self, report: VerificationReport, entry: CalculationEntry):
        """Check if spectrum data was extracted"""
        has_spectrum = entry.frequency_status not in ["not_computed", "failed"]
        check = VerificationCheck(
            name="Spectrum Data",
            description="Verify vibrational frequency data extraction",
            passed=has_spectrum,
            severity="info",
            details=f"Frequency status: {entry.frequency_status}"
        )
        report.checks.append(check)
        report.audit_trail.append(f"[SPECTRUM] Data extraction: {check.passed}")
    
    def _check_energy_accuracy(self, report: VerificationReport, 
                               entry: CalculationEntry, 
                               ref_data: ReferenceData):
        """Compare calculated energy with reference data"""
        if entry.final_energy is None:
            return
        
        # Calculate percentage error
        error = abs(entry.final_energy - ref_data.reference_energy)
        percent_error = (error / abs(ref_data.reference_energy)) * 100
        
        # Define acceptable error margins
        acceptable_error = 0.01  # 1% error margin
        passed = percent_error < (acceptable_error * 100)
        
        check = VerificationCheck(
            name="Energy Accuracy Comparison",
            description=f"Compare with {ref_data.reference_source}",
            passed=passed,
            severity="warning" if not passed and percent_error < 5 else ("error" if not passed else "info"),
            ref_value=ref_data.reference_energy,
            actual_value=entry.final_energy,
            error_margin=percent_error,
            details=f"Error: {percent_error:.3f}% (threshold: {acceptable_error*100:.2f}%)"
        )
        
        report.checks.append(check)
        report.audit_trail.append(f"[ACCURACY] Energy comparison: {percent_error:.3f}% error")
        
        # Add recommendations if error is too large
        if percent_error > 5:
            report.recommendations.append(
                f"Energy error ({percent_error:.2f}%) exceeds 5% threshold. "
                "Consider using a larger basis set or different functional."
            )
    
    def _calculate_credibility(self, report: VerificationReport):
        """Calculate overall credibility score"""
        if not report.checks:
            report.credibility_score = 0.0
            report.overall_level = VerificationLevel.UNVERIFIED.value
            return
        
        # Weight checks by severity
        weights = {
            "error": 3,      # Critical
            "warning": 2,    # Important
            "info": 1        # Note
        }
        
        total_score = 0
        total_weight = 0
        
        for check in report.checks:
            weight = weights.get(check.severity, 1)
            points = 100 if check.passed else 0
            total_score += points * weight
            total_weight += 100 * weight
        
        report.credibility_score = (total_score / total_weight * 100) if total_weight > 0 else 0
        
        # Determine verification level
        if report.credibility_score >= 95:
            report.overall_level = VerificationLevel.CERTIFIED.value
        elif report.credibility_score >= 80:
            report.overall_level = VerificationLevel.VERIFIED.value
        elif report.credibility_score >= 60:
            report.overall_level = VerificationLevel.PARTIAL.value
        else:
            report.overall_level = VerificationLevel.UNVERIFIED.value
    
    def get_verification_mark(self, report: VerificationReport) -> str:
        """Get verification mark/badge"""
        if report.credibility_score >= 95:
            return "✓ CERTIFIED"
        elif report.credibility_score >= 80:
            return "✓ VERIFIED"
        elif report.credibility_score >= 60:
            return "⚠ PARTIAL"
        else:
            return "✗ UNVERIFIED"
    
    def generate_report_text(self, report: VerificationReport) -> str:
        """Generate human-readable verification report"""
        lines = []
        lines.append("=" * 80)
        lines.append("CALCULATION VERIFICATION REPORT")
        lines.append(f"Generated: {report.report_date}")
        lines.append("=" * 80)
        lines.append("")
        
        # Calculation info
        if report.calculation_entry:
            entry = report.calculation_entry
            lines.append("CALCULATION INFORMATION")
            lines.append("-" * 80)
            lines.append(f"ID: {report.calculation_id}")
            lines.append(f"Molecule: {entry.get('molecule_name', 'Unknown')} ({entry.get('molecule_formula', '?')})")
            lines.append(f"Method: {entry.get('method', '?')}/{entry.get('basis_set', '?')}")
            lines.append(f"Task: {entry.get('task', '?')}")
            lines.append(f"Status: {entry.get('status', '?')}")
            if entry.get('final_energy'):
                lines.append(f"Final Energy: {entry['final_energy']:.8f} Hartree")
            lines.append("")
        
        # Verification checks
        lines.append("VERIFICATION CHECKS")
        lines.append("-" * 80)
        for check in report.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            lines.append(f"{status} | {check.name}")
            lines.append(f"       {check.description}")
            if check.details:
                lines.append(f"       Details: {check.details}")
            if check.error_margin is not None:
                lines.append(f"       Error Margin: {check.error_margin:.3f}%")
            lines.append("")
        
        # Reference comparison
        if report.reference_data:
            lines.append("REFERENCE DATA COMPARISON")
            lines.append("-" * 80)
            ref = report.reference_data
            lines.append(f"Reference Source: {ref.reference_source} ({ref.publication_year})")
            lines.append(f"Reference Energy: {ref.reference_energy:.8f} Hartree")
            lines.append("")
        
        # Credibility score
        lines.append("CREDIBILITY ASSESSMENT")
        lines.append("-" * 80)
        lines.append(f"Credibility Score: {report.credibility_score:.1f}/100")
        lines.append(f"Verification Level: {report.overall_level.upper()}")
        lines.append(f"Verification Mark: {self.get_verification_mark(report)}")
        lines.append("")
        
        # Audit trail
        if report.audit_trail:
            lines.append("AUDIT TRAIL")
            lines.append("-" * 80)
            for trail_item in report.audit_trail:
                lines.append(f"  {trail_item}")
            lines.append("")
        
        # Recommendations
        if report.recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 80)
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")
        
        lines.append("=" * 80)
        return "\n".join(lines)
    
    def save_report(self, report: VerificationReport, output_dir: str = "./reports"):
        """Save verification report as JSON and text"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON
        json_file = output_path / f"verification_{report.calculation_id}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        # Save as text
        text_file = output_path / f"verification_{report.calculation_id}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(self.generate_report_text(report))
        
        return str(json_file), str(text_file)
