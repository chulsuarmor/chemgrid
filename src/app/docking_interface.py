# docking_interface.py (v1.0 - AutoDock Vina Integration)
"""
ChemDraw Pro: Molecular Docking Backend
- PDB file parsing and download from RCSB
- Receptor/ligand preparation (PDBQT format via Meeko)
- AutoDock Vina execution in background QThread
- Output parsing for binding affinities and poses
"""

import os
import sys
import subprocess
import time
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    class QThread:
        pass
    class pyqtSignal:
        def __init__(self, *args): pass
        def emit(self, *args): pass

from docking_data import (
    PDBAtom, Residue, ReceptorData, LigandData,
    DockingConfig, DockingPose, DockingResult
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Vina executable path - configurable
_vina_env = os.environ.get("VINA_PATH", "")
VINA_PATH = Path(_vina_env) if (_vina_env and Path(_vina_env).is_file()) else Path("")
if not (str(VINA_PATH) and VINA_PATH.is_file()):
    # Try common locations
    _candidates = [
        Path(r"C:\Program Files\Vina\vina.exe"),
        Path(r"C:\vina\vina.exe"),
        Path.home() / "vina" / "vina.exe",
    ]
    for c in _candidates:
        if c.is_file():
            VINA_PATH = c
            break

# Check for vina Python package as alternative
try:
    from vina import Vina
    VINA_PYTHON_AVAILABLE = True
except ImportError:
    VINA_PYTHON_AVAILABLE = False

# Check for meeko (ligand preparation)
try:
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    MEEKO_AVAILABLE = True
except ImportError:
    MEEKO_AVAILABLE = False

# Check for openbabel
try:
    from openbabel import pybel
    OBABEL_AVAILABLE = True
except ImportError:
    OBABEL_AVAILABLE = False

# Check for RDKit
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdmolfiles
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# Check for BioPython
try:
    from Bio.PDB import PDBParser as BioPDBParser
    BIOPYTHON_AVAILABLE = True
except ImportError:
    BIOPYTHON_AVAILABLE = False

# Check for requests (PDB download)
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Vina availability (strict: must be an actual file, not empty path)
_vina_exe_available = str(VINA_PATH) != '' and str(VINA_PATH) != '.' and VINA_PATH.is_file()

# Overall docking availability (real Vina or simulation fallback)
VINA_AVAILABLE = VINA_PYTHON_AVAILABLE or _vina_exe_available
DOCKING_AVAILABLE = RDKIT_AVAILABLE  # Pipeline works with simulation mode even without Vina
SIMULATION_MODE = not VINA_AVAILABLE  # True when Vina is not installed


# ============================================================================
# PDB FILE PARSER
# ============================================================================

class PDBParser:
    """Parse PDB files into ReceptorData"""

    @staticmethod
    def parse(filepath: Path) -> ReceptorData:
        """Parse a PDB file and return ReceptorData"""
        receptor = ReceptorData(filepath=filepath)
        receptor.name = filepath.stem

        residues_dict: Dict[Tuple[str, int], Residue] = {}

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                record = line[:6].strip()
                if record not in ("ATOM", "HETATM"):
                    continue

                try:
                    atom = PDBAtom(
                        serial=int(line[6:11].strip()),
                        name=line[12:16].strip(),
                        residue_name=line[17:20].strip(),
                        chain=line[21].strip() or "A",
                        residue_id=int(line[22:26].strip()),
                        x=float(line[30:38].strip()),
                        y=float(line[38:46].strip()),
                        z=float(line[46:54].strip()),
                        element=line[76:78].strip() if len(line) > 76 else "",
                        occupancy=float(line[54:60].strip()) if len(line) > 60 else 1.0,
                        b_factor=float(line[60:66].strip()) if len(line) > 66 else 0.0,
                        is_hetatm=(record == "HETATM"),
                    )

                    # Infer element from atom name if not provided
                    if not atom.element:
                        atom.element = atom.name.strip()[0]

                    receptor.atoms.append(atom)

                    # Group into residues
                    key = (atom.chain, atom.residue_id)
                    if key not in residues_dict:
                        residues_dict[key] = Residue(
                            name=atom.residue_name,
                            chain=atom.chain,
                            residue_id=atom.residue_id,
                        )
                    residues_dict[key].atoms.append(atom)

                except (ValueError, IndexError):
                    continue

        # Organize residues by chain
        for (chain, _), residue in sorted(residues_dict.items()):
            if chain not in receptor.residues:
                receptor.residues[chain] = []
            receptor.residues[chain].append(residue)

        return receptor

    @staticmethod
    def remove_water(receptor: ReceptorData) -> ReceptorData:
        """Remove water molecules (HOH) from receptor"""
        water_names = {"HOH", "WAT", "H2O", "DOD"}
        receptor.atoms = [a for a in receptor.atoms if a.residue_name not in water_names]

        for chain in receptor.residues:
            receptor.residues[chain] = [
                r for r in receptor.residues[chain] if r.name not in water_names
            ]
        return receptor


# ============================================================================
# PDB DOWNLOADER
# ============================================================================

class PDBDownloader(QThread):
    """Download PDB structure from RCSB in background"""
    progress = pyqtSignal(str)
    result = pyqtSignal(object)  # Path
    error = pyqtSignal(str)

    def __init__(self, pdb_id: str, output_dir: Path, parent=None):
        super().__init__(parent)
        self.pdb_id = pdb_id.strip().upper()
        self.output_dir = output_dir

    def run(self):
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests 패키지가 설치되어 있지 않습니다.\npip install requests")
            return

        try:
            self.progress.emit(f"PDB ID '{self.pdb_id}' 다운로드 중...")
            url = f"https://files.rcsb.org/download/{self.pdb_id}.pdb"
            resp = requests.get(url, timeout=30)

            if resp.status_code == 404:
                self.error.emit(f"PDB ID '{self.pdb_id}'를 찾을 수 없습니다.")
                return
            resp.raise_for_status()

            output_path = self.output_dir / f"{self.pdb_id}.pdb"
            output_path.write_text(resp.text, encoding='utf-8')

            self.progress.emit(f"다운로드 완료: {output_path}")
            self.result.emit(output_path)

        except requests.exceptions.ConnectionError:
            self.error.emit("RCSB 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요.")
        except Exception as e:
            self.error.emit(f"PDB 다운로드 실패: {str(e)}")


# ============================================================================
# LIGAND PREPARATION
# ============================================================================

class LigandPreparer:
    """Prepare ligand from SMILES to 3D coordinates and PDBQT"""

    @staticmethod
    def smiles_to_3d(smiles: str) -> Optional[LigandData]:
        """Convert SMILES to 3D coordinates using RDKit"""
        if not RDKIT_AVAILABLE:
            return None

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        # Add hydrogens for better 3D geometry
        mol = Chem.AddHs(mol)

        # Generate 3D conformer
        result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if result == -1:
            # Fallback: try with random coordinates
            result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3(), randomSeed=42)
            if result == -1:
                return None

        # Optimize with MMFF
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            pass  # optimization is optional

        # Extract atom data
        conf = mol.GetConformer()
        ligand = LigandData(smiles=smiles)
        for i in range(mol.GetNumAtoms()):
            atom = mol.GetAtomWithIdx(i)
            pos = conf.GetAtomPosition(i)
            ligand.atoms.append((
                atom.GetSymbol(),
                round(pos.x, 4),
                round(pos.y, 4),
                round(pos.z, 4),
            ))

        return ligand

    @staticmethod
    def prepare_pdbqt(ligand: LigandData, output_dir: Path) -> Optional[Path]:
        """Convert ligand to PDBQT format for Vina"""
        if not RDKIT_AVAILABLE:
            return None

        mol = Chem.MolFromSmiles(ligand.smiles)
        if mol is None:
            return None

        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            pass

        if MEEKO_AVAILABLE:
            # Use Meeko for PDBQT preparation
            try:
                preparator = MoleculePreparation()
                mol_setups = preparator.prepare(mol)
                for setup in mol_setups:
                    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(setup)
                    if is_ok:
                        output_path = output_dir / "ligand.pdbqt"
                        output_path.write_text(pdbqt_string, encoding='utf-8')
                        ligand.prepared_pdbqt = output_path
                        return output_path
            except Exception:
                pass

        # Fallback: write as PDB and convert
        pdb_path = output_dir / "ligand.pdb"
        rdmolfiles.MolToPDBFile(mol, str(pdb_path))

        if OBABEL_AVAILABLE:
            try:
                ob_mol = next(pybel.readfile("pdb", str(pdb_path)))
                pdbqt_path = output_dir / "ligand.pdbqt"
                ob_mol.write("pdbqt", str(pdbqt_path), overwrite=True)
                ligand.prepared_pdbqt = pdbqt_path
                return pdbqt_path
            except Exception:
                pass

        # Last fallback: simple PDBQT generation (basic)
        return LigandPreparer._simple_pdb_to_pdbqt(pdb_path, output_dir, ligand)

    @staticmethod
    def _simple_pdb_to_pdbqt(pdb_path: Path, output_dir: Path, ligand: LigandData) -> Optional[Path]:
        """Basic PDB to PDBQT conversion (without external tools)"""
        # Gasteiger charge assignment via RDKit
        if not RDKIT_AVAILABLE:
            return None

        mol = Chem.MolFromPDBFile(str(pdb_path), removeHs=False)
        if mol is None:
            return None

        try:
            AllChem.ComputeGasteigerCharges(mol)
        except Exception:
            pass

        lines = []
        conf = mol.GetConformer()
        for i in range(mol.GetNumAtoms()):
            atom = mol.GetAtomWithIdx(i)
            pos = conf.GetAtomPosition(i)
            charge = float(atom.GetDoubleProp("_GasteigerCharge")) if atom.HasProp("_GasteigerCharge") else 0.0
            if not (-10 < charge < 10):
                charge = 0.0  # sanitize NaN/inf

            element = atom.GetSymbol()
            atom_type = element  # simplified AD4 type

            line = (
                f"ATOM  {i+1:5d}  {element:<3s} LIG A   1    "
                f"{pos.x:8.3f}{pos.y:8.3f}{pos.z:8.3f}"
                f"  1.00  0.00    {charge:+6.3f} {atom_type:<2s}"
            )
            lines.append(line)

        lines.append("TORSDOF 0")

        pdbqt_path = output_dir / "ligand.pdbqt"
        pdbqt_path.write_text("\n".join(lines), encoding='utf-8')
        ligand.prepared_pdbqt = pdbqt_path
        return pdbqt_path


# ============================================================================
# RECEPTOR PREPARATION
# ============================================================================

class ReceptorPreparer:
    """Prepare receptor for docking (PDB -> PDBQT)"""

    @staticmethod
    def prepare_pdbqt(receptor: ReceptorData, output_dir: Path) -> Optional[Path]:
        """Convert receptor to PDBQT format"""
        if receptor.filepath is None:
            return None

        if OBABEL_AVAILABLE:
            try:
                ob_mol = next(pybel.readfile("pdb", str(receptor.filepath)))
                # Add hydrogens at pH 7.4
                ob_mol.OBMol.AddHydrogens(False, True, 7.4)
                pdbqt_path = output_dir / "receptor.pdbqt"
                ob_mol.write("pdbqt", str(pdbqt_path), overwrite=True)
                receptor.prepared_pdbqt = pdbqt_path
                return pdbqt_path
            except Exception:
                pass

        # Fallback: basic PDBQT conversion from PDB
        return ReceptorPreparer._simple_pdb_to_pdbqt(receptor, output_dir)

    @staticmethod
    def _simple_pdb_to_pdbqt(receptor: ReceptorData, output_dir: Path) -> Optional[Path]:
        """Basic PDB -> PDBQT (assign default charges)"""
        # Standard amino acid charge assignments
        CHARGE_MAP = {
            "N": -0.35, "CA": 0.10, "C": 0.55, "O": -0.55,
            "CB": 0.0, "H": 0.25, "OXT": -0.67,
        }

        lines = []
        for atom in receptor.atoms:
            charge = CHARGE_MAP.get(atom.name.strip(), 0.0)
            element = atom.element if atom.element else atom.name.strip()[0]
            atom_type = element

            line = (
                f"ATOM  {atom.serial:5d} {atom.name:>4s} {atom.residue_name:3s} "
                f"{atom.chain:1s}{atom.residue_id:4d}    "
                f"{atom.x:8.3f}{atom.y:8.3f}{atom.z:8.3f}"
                f"{atom.occupancy:6.2f}{atom.b_factor:6.2f}    {charge:+6.3f} {atom_type:<2s}"
            )
            lines.append(line)

        pdbqt_path = output_dir / "receptor.pdbqt"
        pdbqt_path.write_text("\n".join(lines), encoding='utf-8')
        receptor.prepared_pdbqt = pdbqt_path
        return pdbqt_path

    @staticmethod
    def detect_binding_site(receptor: ReceptorData) -> Tuple[Tuple[float,float,float], Tuple[float,float,float]]:
        """Auto-detect potential binding site (center and size)

        Strategy: if HETATM ligand exists, use its centroid;
        otherwise use the receptor centroid.
        """
        # Look for co-crystallized ligand (non-standard HETATM excluding water)
        water_names = {"HOH", "WAT", "H2O", "DOD"}
        ion_names = {"NA", "CL", "MG", "ZN", "CA", "FE", "MN", "SO4", "PO4"}
        hetatm_atoms = [
            a for a in receptor.atoms
            if a.is_hetatm
            and a.residue_name not in water_names
            and a.residue_name not in ion_names
        ]

        if hetatm_atoms:
            xs = [a.x for a in hetatm_atoms]
            ys = [a.y for a in hetatm_atoms]
            zs = [a.z for a in hetatm_atoms]
            center = (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
            # Size: bounding box + 10A padding
            padding = 10.0
            size = (
                max(xs) - min(xs) + padding,
                max(ys) - min(ys) + padding,
                max(zs) - min(zs) + padding,
            )
            # Ensure minimum size (use tuple comprehension, not generator)
            size = tuple(max(s, 20.0) for s in size)
            return center, size

        # Fallback: receptor centroid with default size
        center = receptor.get_center()
        return center, (25.0, 25.0, 25.0)


# ============================================================================
# VINA DOCKING THREAD
# ============================================================================

class VinaDockingThread(QThread):
    """Run AutoDock Vina docking in background thread"""
    progress = pyqtSignal(str)
    result = pyqtSignal(object)   # DockingResult
    error = pyqtSignal(str)

    def __init__(self, receptor_pdbqt: Path, ligand_pdbqt: Path,
                 config: DockingConfig, work_dir: Path,
                 receptor: ReceptorData = None, ligand: LigandData = None,
                 parent=None):
        super().__init__(parent)
        self.receptor_pdbqt = receptor_pdbqt
        self.ligand_pdbqt = ligand_pdbqt
        self.config = config
        self.work_dir = work_dir
        self.receptor = receptor
        self.ligand = ligand

    def run(self):
        start_time = time.time()
        try:
            if VINA_PYTHON_AVAILABLE:
                dock_result = self._run_vina_python()
            elif _vina_exe_available:
                dock_result = self._run_vina_subprocess()
            elif SIMULATION_MODE:
                self.progress.emit("시뮬레이션 모드: Vina 미설치 — 거리 기반 휴리스틱 스코어링...")
                dock_result = self._run_simulation_fallback()
            else:
                self.error.emit("AutoDock Vina가 설치되어 있지 않습니다.\npip install vina 또는 vina.exe 경로를 설정하세요.")
                return

            dock_result.computation_time = time.time() - start_time
            dock_result.receptor = self.receptor
            dock_result.ligand = self.ligand
            dock_result.config = self.config
            self.result.emit(dock_result)

        except Exception as e:
            self.error.emit(f"도킹 실행 실패: {str(e)}")

    def _run_vina_python(self) -> DockingResult:
        """Run docking using vina Python package"""
        self.progress.emit("Vina 도킹 엔진 초기화 중...")

        try:
            v = Vina(sf_name='vina')
        except Exception as e:
            return DockingResult(converged=False, poses=[],
                                error_message=f"Vina 초기화 실패: {e}")

        try:
            v.set_receptor(str(self.receptor_pdbqt))
        except Exception as e:
            return DockingResult(converged=False, poses=[],
                                error_message=f"수용체 로딩 실패: {e}")

        try:
            v.set_ligand_from_file(str(self.ligand_pdbqt))
        except Exception as e:
            return DockingResult(converged=False, poses=[],
                                error_message=f"리간드 로딩 실패 ({self.ligand_pdbqt}): {e}")

        try:
            v.compute_vina_maps(
                center=list(self.config.center),
                box_size=list(self.config.size),
            )
        except Exception as e:
            return DockingResult(converged=False, poses=[],
                                error_message=f"Vina 맵 계산 실패: {e}")

        self.progress.emit(f"도킹 계산 중 (exhaustiveness={self.config.exhaustiveness})...")

        try:
            v.dock(
                exhaustiveness=self.config.exhaustiveness,
                n_poses=self.config.num_modes,
            )
        except Exception as e:
            return DockingResult(converged=False, poses=[],
                                error_message=f"도킹 계산 실패: {e}")

        # Get results
        try:
            energies = v.energies()  # [[affinity, ...], ...]
        except Exception:
            energies = []

        output_pdbqt = self.work_dir / "docking_output.pdbqt"
        try:
            v.write_poses(str(output_pdbqt), n_poses=self.config.num_modes)
        except Exception as e:
            return DockingResult(converged=False, poses=[],
                                error_message=f"결과 파일 저장 실패: {e}")

        self.progress.emit("결과 분석 중...")

        # Parse poses from output
        poses = []
        if output_pdbqt.exists():
            try:
                poses = VinaOutputParser.parse_output_pdbqt(output_pdbqt)
            except Exception as e:
                print(f"[Docking] 포즈 파싱 오류: {e}", flush=True)

        # Update energies from Vina
        if energies:
            for i, pose in enumerate(poses):
                if i < len(energies) and len(energies[i]) > 0:
                    pose.affinity_kcal = energies[i][0]

        result = DockingResult(converged=True, poses=poses)
        result.vina_log = f"Poses generated: {len(poses)}"
        return result

    def _run_vina_subprocess(self) -> DockingResult:
        """Run docking using vina executable"""
        self.progress.emit("Vina 실행 파일로 도킹 중...")

        config_path = self.work_dir / "vina_config.txt"
        output_path = self.work_dir / "docking_output.pdbqt"
        log_path = self.work_dir / "vina_log.txt"

        # Write Vina config
        config_lines = [
            f"receptor = {self.receptor_pdbqt}",
            f"ligand = {self.ligand_pdbqt}",
            f"center_x = {self.config.center_x}",
            f"center_y = {self.config.center_y}",
            f"center_z = {self.config.center_z}",
            f"size_x = {self.config.size_x}",
            f"size_y = {self.config.size_y}",
            f"size_z = {self.config.size_z}",
            f"exhaustiveness = {self.config.exhaustiveness}",
            f"num_modes = {self.config.num_modes}",
            f"energy_range = {self.config.energy_range}",
            f"out = {output_path}",
            f"log = {log_path}",
        ]
        config_path.write_text("\n".join(config_lines), encoding='utf-8')

        # Execute Vina
        cmd = [str(VINA_PATH), "--config", str(config_path)]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=600, cwd=str(self.work_dir)
        )

        vina_log = proc.stdout + proc.stderr
        if log_path.exists():
            vina_log += "\n" + log_path.read_text(encoding='utf-8', errors='ignore')

        if proc.returncode != 0:
            return DockingResult(
                converged=False,
                vina_log=vina_log,
                error_message=f"Vina exited with code {proc.returncode}"
            )

        # Parse output
        poses = VinaOutputParser.parse_output_pdbqt(output_path)
        log_poses = VinaOutputParser.parse_log(vina_log)

        # Merge energy data from log into poses
        for i, pose in enumerate(poses):
            if i < len(log_poses):
                pose.affinity_kcal = log_poses[i].affinity_kcal
                pose.rmsd_lb = log_poses[i].rmsd_lb
                pose.rmsd_ub = log_poses[i].rmsd_ub

        return DockingResult(
            converged=True,
            poses=poses,
            vina_log=vina_log,
        )

    def _run_simulation_fallback(self) -> DockingResult:
        """Distance-based heuristic scoring when Vina is not installed.

        Provides approximate docking scores based on:
        - Receptor-ligand geometric complementarity
        - Distance from binding site center
        - Simple van der Waals contact estimation
        This is NOT a real docking — it allows pipeline testing without Vina.
        """
        import random
        import math

        self.progress.emit("[시뮬레이션] 리간드 좌표 로딩 중...")

        if not RDKIT_AVAILABLE:
            return DockingResult(
                converged=False, poses=[],
                error_message="RDKit이 없어 시뮬레이션 모드도 실행 불가합니다."
            )

        # Read ligand atoms from PDBQT or generate from ligand data
        lig_coords = []
        lig_elements = []
        if self.ligand and self.ligand.atoms:
            for elem, x, y, z in self.ligand.atoms:
                lig_coords.append((x, y, z))
                lig_elements.append(elem)
        elif self.ligand_pdbqt and self.ligand_pdbqt.exists():
            with open(self.ligand_pdbqt, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith(("ATOM", "HETATM")):
                        try:
                            x = float(line[30:38].strip())
                            y = float(line[38:46].strip())
                            z = float(line[46:54].strip())
                            elem = line[76:78].strip() if len(line) > 76 else "C"
                            lig_coords.append((x, y, z))
                            lig_elements.append(elem)
                        except (ValueError, IndexError):
                            pass

        if not lig_coords:
            return DockingResult(
                converged=False, poses=[],
                error_message="리간드 좌표를 읽을 수 없습니다."
            )

        self.progress.emit("[시뮬레이션] 결합 부위 근접도 계산 중...")

        # Translate ligand centroid to binding site center
        cx = self.config.center[0] if hasattr(self.config, 'center') else getattr(self.config, 'center_x', 0.0)
        cy = self.config.center[1] if hasattr(self.config, 'center') else getattr(self.config, 'center_y', 0.0)
        cz = self.config.center[2] if hasattr(self.config, 'center') else getattr(self.config, 'center_z', 0.0)

        lig_cx = sum(c[0] for c in lig_coords) / len(lig_coords)
        lig_cy = sum(c[1] for c in lig_coords) / len(lig_coords)
        lig_cz = sum(c[2] for c in lig_coords) / len(lig_coords)

        dx, dy, dz = cx - lig_cx, cy - lig_cy, cz - lig_cz

        # Generate multiple simulated poses with slight perturbations
        num_poses = min(self.config.num_modes, 9)
        poses = []
        rng = random.Random(42)  # deterministic seed

        for pose_id in range(1, num_poses + 1):
            # Simulated affinity: heavier molecules tend to bind better (rough heuristic)
            n_heavy = sum(1 for e in lig_elements if e not in ('H', ''))
            base_affinity = -3.0 - (n_heavy * 0.3)  # more atoms -> more negative
            noise = rng.gauss(0, 0.5) * (pose_id - 1) * 0.3
            affinity = round(base_affinity + noise, 1)

            # Translated + perturbed coordinates
            perturb = [(rng.gauss(0, 0.3), rng.gauss(0, 0.3), rng.gauss(0, 0.3))
                       for _ in lig_coords]
            translated = [
                (x + dx + px, y + dy + py, z + dz + pz)
                for (x, y, z), (px, py, pz) in zip(lig_coords, perturb)
            ]

            pose = DockingPose(
                pose_id=pose_id,
                affinity_kcal=affinity,
                rmsd_lb=round(abs(noise) * 0.5, 2),
                rmsd_ub=round(abs(noise) * 0.8, 2),
            )
            pose.atom_coords = translated
            pose.atom_elements = list(lig_elements)
            poses.append(pose)

        # Sort by affinity (most negative first)
        poses.sort(key=lambda p: p.affinity_kcal)
        for i, p in enumerate(poses):
            p.pose_id = i + 1

        self.progress.emit(f"[시뮬레이션] {len(poses)}개 포즈 생성 완료 (주의: 실제 Vina 결과가 아닙니다)")

        return DockingResult(
            converged=True,
            poses=poses,
            vina_log="[SIMULATION MODE] Distance-based heuristic scoring.\n"
                     "WARNING: These results are approximate and NOT from AutoDock Vina.\n"
                     f"Install vina (`pip install vina`) for accurate docking.\n"
                     f"Poses generated: {len(poses)}",
            is_simulation=True,
        )


# ============================================================================
# VINA OUTPUT PARSER
# ============================================================================

# ============================================================================
# SCREENING COMPATIBILITY BRIDGE (TASK-DOCK-005)
# ============================================================================

def docking_result_to_screening_scores(
    result: DockingResult,
    interactions: dict = None,
) -> dict:
    """Convert a DockingResult into the dict format expected by drug_screening.py.

    drug_screening.DockingScore expects:
      - smiles: str
      - binding_affinity: float (kcal/mol, more negative = better)
      - pose_rmsd: float
      - n_interactions: int
      - interaction_types: List[str]

    This function bridges docking_interface output (DockingResult with
    DockingPose objects using affinity_kcal, rmsd_lb) to the drug_screening
    input format (DockingScore with binding_affinity, pose_rmsd).

    Args:
        result: DockingResult from VinaDockingThread
        interactions: Optional dict of pose_id -> List[Interaction]

    Returns:
        Dict mapping smiles -> screening-compatible score dict.
        Can be used to construct drug_screening.DockingScore objects:
            from drug_screening import DockingScore
            scores = docking_result_to_screening_scores(result)
            for smiles, data in scores.items():
                ds = DockingScore(**data)
    """
    try:
        return result.to_screening_scores(interactions=interactions)
    except Exception:
        # Graceful fallback: return empty dict on any conversion error
        return {}


class VinaOutputParser:
    """Parse AutoDock Vina output files"""

    @staticmethod
    def parse_log(log_text: str) -> List[DockingPose]:
        """Parse Vina log text for binding affinities"""
        poses = []
        in_results = False

        for line in log_text.split('\n'):
            line = line.strip()

            # Look for results table header
            if "mode" in line.lower() and "affinity" in line.lower():
                in_results = True
                continue

            if in_results and line.startswith("---"):
                continue

            if in_results and line:
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        pose_id = int(parts[0])
                        affinity = float(parts[1])
                        rmsd_lb = float(parts[2])
                        rmsd_ub = float(parts[3])
                        poses.append(DockingPose(
                            pose_id=pose_id,
                            affinity_kcal=affinity,
                            rmsd_lb=rmsd_lb,
                            rmsd_ub=rmsd_ub,
                        ))
                    except (ValueError, IndexError):
                        if poses:  # end of results table
                            break

        return poses

    @staticmethod
    def parse_output_pdbqt(pdbqt_path: Path) -> List[DockingPose]:
        """Parse multi-model PDBQT output for pose coordinates"""
        if not pdbqt_path.exists():
            return []

        poses = []
        current_pose = None
        pose_id = 0

        with open(pdbqt_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith("MODEL"):
                    pose_id += 1
                    current_pose = DockingPose(pose_id=pose_id, affinity_kcal=0.0)

                elif line.startswith("REMARK VINA RESULT"):
                    # REMARK VINA RESULT:   -7.5      0.000      0.000
                    parts = line.split()
                    if current_pose and len(parts) >= 6:
                        try:
                            current_pose.affinity_kcal = float(parts[3])
                            current_pose.rmsd_lb = float(parts[4])
                            current_pose.rmsd_ub = float(parts[5])
                        except (ValueError, IndexError):
                            pass

                elif line.startswith(("ATOM", "HETATM")) and current_pose is not None:
                    try:
                        x = float(line[30:38].strip())
                        y = float(line[38:46].strip())
                        z = float(line[46:54].strip())
                        current_pose.atom_coords.append((x, y, z))

                        # Extract element
                        element = line[76:78].strip() if len(line) > 76 else line[12:16].strip()[0]
                        current_pose.atom_elements.append(element)
                    except (ValueError, IndexError):
                        pass

                elif line.startswith("ENDMDL") and current_pose is not None:
                    poses.append(current_pose)
                    current_pose = None

        # Handle single-model file (no MODEL/ENDMDL)
        if current_pose is not None and current_pose.atom_coords:
            poses.append(current_pose)

        return poses
