"""
predict_spectra.py — SMILES 기반 예측 스펙트럼 생성기
=======================================================
ORCA 파일 없이 SMILES/분자 구조로부터 추정 스펙트럼 생성.
spectra_assets/*/explanatory.txt 기준 준수:
  IR:     X=4000→400cm⁻¹, Y=Transmittance%, 피크↓(inverted)
  Raman:  X=0→4000cm⁻¹, Y=Intensity, 피크↑
  1H-NMR: X=12→0ppm, Integration line, Splitting
  13C-NMR: X=220→0ppm, Zone color (aliphatic/aromatic/carbonyl)
  UV-Vis: 듀얼 뷰 (ε linear + log ε), X=200→800nm
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# RDKit 임포트
try:
    from rdkit import Chem
    from rdkit.Chem import (
        Descriptors, rdMolDescriptors, AllChem,
        rdchem
    )
    RDKIT_OK = True
except ImportError:
    RDKIT_OK = False

# ─── 데이터 클래스 ────────────────────────────────────────

@dataclass
class IRPeak:
    wavenumber: float        # cm⁻¹ (4000→400)
    transmittance: float     # % (0~100, 피크는 낮은 값)
    assignment: str          # "C=O str.", "O-H broad", etc.
    width: float = 20.0      # FWHM (cm⁻¹)

@dataclass
class RamanPeak:
    shift: float             # cm⁻¹ (0→4000)
    intensity: float         # 0~1
    assignment: str
    width: float = 15.0

@dataclass
class NMRPeak:
    shift: float             # ppm
    integration: float       # 상대 H 개수 (1H-NMR)
    multiplicity: str        # s/d/t/q/m
    assignment: str          # "CH3", "ArH", etc.
    neighbors: int = 0       # 인접 H 개수 (n+1 rule)

@dataclass
class C13Peak:
    shift: float             # ppm (0~220)
    carbon_type: str         # "CH3"/"CH2"/"CH"/"C" (quaternary)
    zone: str                # "aliphatic"/"aromatic"/"carbonyl"
    assignment: str

@dataclass
class UVVisPeak:
    wavelength: float        # nm (200~800)
    epsilon: float           # L·mol⁻¹·cm⁻¹
    transition_type: str     # "pi→pi*"/"n→pi*"/"sigma→sigma*"
    assignment: str

@dataclass
class PredictedSpectra:
    smiles: str
    formula: str
    ir_peaks: List[IRPeak] = field(default_factory=list)
    raman_peaks: List[RamanPeak] = field(default_factory=list)
    h1_nmr_peaks: List[NMRPeak] = field(default_factory=list)
    c13_peaks: List[C13Peak] = field(default_factory=list)
    uvvis_peaks: List[UVVisPeak] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

# ─── IR 피크 룩업 테이블 (Hooke's Law 근사 + 경험치) ────────

# (wavenumber, transmittance, assignment, width, func_group_check)
IR_LOOKUP: Dict[str, List[Tuple]] = {
    # 작용기: (wavenumber, transmittance_min, assignment, width)
    "O-H_alcohol":  [(3400, 15, "O-H str. (broad)", 300), (1050, 20, "C-O str.", 30)],
    "O-H_carboxyl": [(2700, 20, "O-H str. (carboxylic)", 500), (1710, 5, "C=O str.", 25)],
    "N-H":          [(3350, 25, "N-H str.", 100), (1600, 30, "N-H bend", 30)],
    "C-H_sp3":      [(2960, 40, "C-H str. (sp3)", 20), (2870, 45, "C-H str. (sp3)", 20),
                     (1460, 50, "C-H bend", 25), (1380, 55, "C-H sym. bend", 20)],
    "C-H_sp2":      [(3080, 50, "=C-H str.", 20), (800, 45, "=C-H oop bend", 40)],
    "C-H_aromatic": [(3070, 45, "Ar-H str.", 20), (1600, 55, "C=C ring str.", 30),
                     (1500, 55, "C=C ring str.", 25), (680, 30, "Ar-H oop", 50)],
    "C=O_ketone":   [(1715, 5, "C=O str. (ketone)", 25)],
    "C=O_aldehyde": [(1720, 8, "C=O str. (aldehyde)", 25), (2720, 50, "C-H str. (CHO)", 15)],
    "C=O_ester":    [(1735, 5, "C=O str. (ester)", 25), (1250, 20, "C-O-C str. asym.", 30)],
    "C=O_amide":    [(1660, 8, "C=O str. (amide I)", 30), (1545, 30, "N-H bend + C-N (II)", 35)],
    "C=C":          [(1640, 40, "C=C str.", 25)],
    "C≡C":          [(2100, 30, "C≡C str.", 20)],
    "C≡N":          [(2200, 20, "C≡N str.", 20)],
    "C-O":          [(1080, 25, "C-O str.", 30)],
    "C-N":          [(1200, 45, "C-N str.", 30)],
    "C-F":          [(1100, 10, "C-F str.", 50)],
    "C-Cl":         [(750, 20, "C-Cl str.", 40)],
    "C-Br":         [(650, 20, "C-Br str.", 40)],
    "C-I":          [(500, 25, "C-I str.", 35)],
    "S-H":          [(2550, 35, "S-H str.", 25)],
    "S=O_sulfoxide":[(1050, 10, "S=O str. (sulfoxide)", 30)],
    "S=O_sulfone":  [(1300, 10, "S=O asym. str. (sulfone)", 30),
                     (1150, 12, "S=O sym. str. (sulfone)", 30)],
    "P=O":          [(1250, 15, "P=O str.", 35)],
    "NO2":          [(1540, 8, "N=O asym. str. (NO2)", 30),
                     (1350, 12, "N=O sym. str. (NO2)", 25)],
    "C=N_imine":    [(1660, 30, "C=N str.", 25)],
    "C=N_pyridine": [(1590, 35, "C=N ring str. (pyridine)", 25),
                     (1480, 40, "C=N ring str. (pyridine)", 20)],
    "ring_5":       [(900, 30, "ring breathing", 30)],
    "ring_6":       [(700, 25, "ring C-H oop", 50)],
}

def _detect_functional_groups(mol) -> List[str]:
    """SMARTS 기반 작용기 탐지"""
    if mol is None:
        return []
    groups = []
    smarts_map = {
        "O-H_alcohol":  "[OX2H1][CX4]",
        "O-H_carboxyl": "C(=O)[OH]",
        "N-H":          "[NH]",
        "C=O_ketone":   "[CX3H0](=O)[CX4]",
        "C=O_aldehyde": "[CX3H1](=O)",
        "C=O_ester":    "[CX3](=O)[OX2][#6]",
        "C=O_amide":    "[CX3](=O)[NX3]",
        "C=C":          "[CX3]=[CX3]",
        "C≡C":          "[CX2]#[CX2]",
        "C≡N":          "[CX2]#[NX1]",
        "C-F":          "[CX4][F]",
        "C-Cl":         "[CX4][Cl]",
        "C-Br":         "[CX4][Br]",
        "C-I":          "[CX4][I]",
        "C-O":          "[CX4][OX2]",
        "C-N":          "[CX4][NX3]",
        "S-H":          "[SX2H]",
        "S=O_sulfoxide": "[SX3](=O)",
        "S=O_sulfone":  "[SX4](=O)(=O)",
        "P=O":          "[PX4](=O)",
        "NO2":          "[$([NX3](=O)=O),$([NX3+](=O)[O-])]",
        "C=N_imine":    "[CX3]=[NX2]",
        "C=N_pyridine": "[nX2]",  # aromatic nitrogen in ring
    }
    for name, sma in smarts_map.items():
        try:
            patt = Chem.MolFromSmarts(sma)
            if patt and mol.HasSubstructMatch(patt):
                groups.append(name)
        except Exception:
            pass

    # C-H 판별
    has_aromatic = any(a.GetIsAromatic() for a in mol.GetAtoms())
    has_sp3_ch   = any(a.GetSymbol() == "C" and a.GetHybridization() == rdchem.HybridizationType.SP3
                       for a in mol.GetAtoms())
    # Fix: sp2 C-H should only fire for true alkene C=C, not for C=O carbons
    has_sp2_ch   = any(
        a.GetSymbol() == "C"
        and a.GetHybridization() == rdchem.HybridizationType.SP2
        and not a.GetIsAromatic()
        and a.GetTotalNumHs() > 0  # must have H attached
        and not any(  # exclude carbons in C=O (carbonyl)
            mol.GetAtomWithIdx(b.GetOtherAtomIdx(a.GetIdx())).GetSymbol() == "O"
            and b.GetBondType() == Chem.rdchem.BondType.DOUBLE
            for b in a.GetBonds()
        )
        for a in mol.GetAtoms()
    )

    if has_aromatic:
        groups.append("C-H_aromatic")
    if has_sp3_ch:
        groups.append("C-H_sp3")
    if has_sp2_ch:
        groups.append("C-H_sp2")

    # 고리 크기
    ring_info = mol.GetRingInfo()
    for ring in ring_info.AtomRings():
        if len(ring) == 5:
            groups.append("ring_5")
        elif len(ring) == 6:
            groups.append("ring_6")
        break  # 첫 고리만

    return list(set(groups))

def predict_ir(smiles: str) -> List[IRPeak]:
    """IR 스펙트럼 예측 (Transmittance %, 피크 ↓)"""
    peaks = []
    if not RDKIT_OK:
        # Fallback: C-H stretch 기본 피크만
        return [
            IRPeak(2960, 40, "C-H str. (sp3)", 20),
            IRPeak(1460, 55, "C-H bend", 25),
        ]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return peaks

    groups = _detect_functional_groups(mol)

    # Prioritize specific functional groups over generic C-H types.
    # Specific groups (e.g., C=N_pyridine) should override generic ones
    # (e.g., C-H_aromatic C=C ring str.) when wavenumbers overlap.
    _GENERIC_GROUPS = {"C-H_sp3", "C-H_sp2", "C-H_aromatic", "ring_5", "ring_6"}
    specific_groups = [g for g in groups if g not in _GENERIC_GROUPS]
    generic_groups  = [g for g in groups if g in _GENERIC_GROUPS]
    ordered_groups  = specific_groups + generic_groups

    seen_wn = set()

    for grp in ordered_groups:
        if grp in IR_LOOKUP:
            for (wn, tr_min, asgn, w) in IR_LOOKUP[grp]:
                # 중복 제거 (±50 cm⁻¹ 이내)
                dup = any(abs(wn - s) < 50 for s in seen_wn)
                if not dup:
                    peaks.append(IRPeak(wn, tr_min, asgn, w))
                    seen_wn.add(wn)

    # baseline: 지문 영역(400~1500) 에 복잡한 패턴 추가
    baseline_peaks = [
        IRPeak(1350, 75, "fingerprint region", 15),
        IRPeak(1250, 65, "fingerprint region", 15),
        IRPeak(1100, 60, "fingerprint region", 15),
        IRPeak(900, 70, "fingerprint region", 20),
        IRPeak(600, 65, "fingerprint region", 20),
    ]
    peaks.extend(baseline_peaks)
    return sorted(peaks, key=lambda p: p.wavenumber, reverse=True)

def predict_raman(smiles: str) -> List[RamanPeak]:
    """Raman 스펙트럼 예측 (Intensity, 피크 ↑)"""
    if not RDKIT_OK:
        return [RamanPeak(1000, 0.8, "ring breathing", 15)]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    peaks = []
    groups = _detect_functional_groups(mol)

    raman_groups = {
        "C=C":          (1620, 0.9, "C=C str. (symmetric)"),
        "C≡C":          (2120, 0.95, "C≡C str."),
        "C≡N":          (2230, 0.7, "C≡N str."),
        "C-H_aromatic": (1000, 0.85, "ring breathing"),
        "C-H_sp3":      (2900, 0.5, "C-H str."),
        "ring_6":       (1000, 0.9, "ring breathing (6-membered)"),
        "ring_5":       (900, 0.8, "ring breathing (5-membered)"),
        "C-O":          (1100, 0.4, "C-O str."),
    }
    for grp, (sh, inten, asgn) in raman_groups.items():
        if grp in groups:
            peaks.append(RamanPeak(sh, inten, asgn))

    # D/G band for aromatic carbon systems
    if "C-H_aromatic" in groups:
        peaks.append(RamanPeak(1360, 0.5, "D band (defect)"))
        peaks.append(RamanPeak(1580, 0.9, "G band (sp2 C=C)"))

    return sorted(peaks, key=lambda p: p.shift)

# ─── NMR 예측 ─────────────────────────────────────────────

def _get_h_neighbors(atom, mol) -> int:
    """인접 C에 붙은 H 개수 (coupling partner).
    Works correctly both before and after Chem.AddHs()."""
    n_h = 0
    for nbr in atom.GetNeighbors():
        if nbr.GetSymbol() == "C" and not nbr.GetIsAromatic():
            # After AddHs(), TotalNumHs() returns 0 because H are explicit atoms.
            # Count explicit H neighbors directly.
            h_count = sum(1 for n2 in nbr.GetNeighbors() if n2.GetSymbol() == "H")
            if h_count == 0:
                # Fallback for molecules without explicit H
                h_count = nbr.GetTotalNumHs()
            n_h += h_count
    return n_h

def _multiplicity_str(n_adj_h: int) -> str:
    mapping = {0: "s", 1: "d", 2: "t", 3: "q", 4: "quint"}
    return mapping.get(n_adj_h, "m")

def predict_h1_nmr(smiles: str) -> List[NMRPeak]:
    """¹H-NMR 예측 (Chemical Shift 0~12 ppm, 피크 ↑, Integration)"""
    if not RDKIT_OK:
        return [NMRPeak(1.0, 3, "t", "CH3 (est.)")]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []
    mol = Chem.AddHs(mol)

    groups: Dict[str, NMRPeak] = {}

    for atom in mol.GetAtoms():
        if atom.GetSymbol() != "H":
            continue
        # 부착된 원자
        nbr_list = atom.GetNeighbors()
        if not nbr_list:
            continue
        parent = nbr_list[0]
        ps = parent.GetSymbol()
        is_arom = parent.GetIsAromatic()
        hyb = parent.GetHybridization()

        # Chemical shift 추정
        shift = 1.5  # default (aliphatic)
        asgn  = "C-H (aliphatic)"

        if ps == "O":
            shift = 2.6   # CDCl3 standard; O-H is highly variable (1~5 ppm)
            asgn = "O-H (alcohol)"
            # Check if carboxylic
            for nbr2 in parent.GetNeighbors():
                if nbr2.GetSymbol() == "C":
                    for nbr3 in nbr2.GetNeighbors():
                        if nbr3.GetSymbol() == "O" and nbr3.GetIdx() != parent.GetIdx():
                            shift = 11.5
                            asgn = "O-H (carboxylic)"
        elif ps == "N":
            shift = 2.5
            asgn = "N-H"
        elif ps == "C":
            if is_arom:
                shift = 7.3
                asgn = "Ar-H"
            elif hyb == rdchem.HybridizationType.SP2:
                shift = 5.5
                asgn = "vinyl-H"
            else:
                # Check adjacent electronegative atoms
                shift = 1.2
                for nbr2 in parent.GetNeighbors():
                    s2 = nbr2.GetSymbol()
                    if s2 == "O":
                        shift = max(shift, 3.5); asgn = "OCH"
                    elif s2 == "N":
                        shift = max(shift, 2.5); asgn = "NCH"
                    elif s2 == "Cl" or s2 == "Br":
                        shift = max(shift, 3.8); asgn = "CHX (halide)"
                    elif s2 == "C":
                        for nbr3 in nbr2.GetNeighbors():
                            if nbr3.GetSymbol() == "O" and \
                               nbr2.GetHybridization() == rdchem.HybridizationType.SP2:
                                shift = max(shift, 2.3); asgn = "CH adjacent to C=O"

        # Multiplicity
        if ps == "O" or ps == "N":
            mult = "s"
            n_adj = 0
        else:
            n_adj = _get_h_neighbors(parent, mol)
            mult = _multiplicity_str(n_adj)

        # Group by shift+assignment (round to 0.2 ppm)
        key = f"{round(shift*5)/5:.1f}_{asgn}"
        if key in groups:
            groups[key].integration += 1
        else:
            groups[key] = NMRPeak(
                shift=shift, integration=1, multiplicity=mult,
                assignment=asgn, neighbors=n_adj
            )

    return sorted(groups.values(), key=lambda p: p.shift)

def predict_c13_nmr(smiles: str) -> List[C13Peak]:
    """¹³C-NMR 예측 (Chemical Shift 0~220 ppm)"""
    if not RDKIT_OK:
        return [C13Peak(30, "CH3", "aliphatic", "C (aliphatic)")]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    peaks = []
    seen_shifts = set()

    for atom in mol.GetAtoms():
        if atom.GetSymbol() != "C":
            continue

        is_arom = atom.GetIsAromatic()
        hyb     = atom.GetHybridization()
        n_h     = atom.GetTotalNumHs()

        # C 차수 판별
        if n_h >= 3:
            c_type = "CH3"
        elif n_h == 2:
            c_type = "CH2"
        elif n_h == 1:
            c_type = "CH"
        else:
            c_type = "C"  # quaternary

        # Chemical shift 추정
        shift = 20.0  # default aliphatic
        zone  = "aliphatic"
        asgn  = "C (aliphatic)"

        if is_arom:
            shift = 128.0
            zone  = "aromatic"
            asgn  = f"Ar-C ({c_type})"
        elif hyb == rdchem.HybridizationType.SP2:
            # Check if carbonyl
            is_carbonyl = any(b.GetBondType() == Chem.rdchem.BondType.DOUBLE
                              for b in atom.GetBonds()
                              if mol.GetAtomWithIdx(b.GetOtherAtomIdx(atom.GetIdx())).GetSymbol() == "O")
            if is_carbonyl:
                # Distinguish ester/ketone/amide/aldehyde
                # First, classify all O/N neighbors (skip the =O double-bond oxygen)
                has_single_O_noh = False  # ester -O-R (no H)
                has_single_O_h   = False  # carboxyl -OH
                has_N            = False  # amide
                for nbr in atom.GetNeighbors():
                    s = nbr.GetSymbol()
                    bond = mol.GetBondBetweenAtoms(atom.GetIdx(), nbr.GetIdx())
                    is_double = bond and bond.GetBondType() == Chem.rdchem.BondType.DOUBLE
                    if s == "O" and is_double:
                        continue  # skip the =O itself
                    if s == "O" and nbr.GetTotalNumHs() >= 1:
                        has_single_O_h = True
                    elif s == "O" and nbr.GetTotalNumHs() == 0:
                        has_single_O_noh = True
                    elif s == "N":
                        has_N = True

                if has_single_O_h and has_single_O_noh:
                    # Should not happen (would be carbonate), treat as acid
                    shift = 170.0; asgn = "C=O (carboxylic)"
                elif has_single_O_h:
                    shift = 175.0; asgn = "C=O (carboxylic)"
                elif has_single_O_noh:
                    shift = 170.0; asgn = "C=O (ester)"
                elif has_N:
                    shift = 167.0; asgn = "C=O (amide)"
                elif n_h >= 1:
                    shift = 200.0; asgn = "C=O (aldehyde)"
                else:
                    shift = 205.0; asgn = "C=O (ketone)"
                zone = "carbonyl"
            else:
                shift = 130.0
                zone  = "aromatic"
                asgn  = f"C=C ({c_type})"
        else:
            # sp3 aliphatic: check neighbors
            for nbr in atom.GetNeighbors():
                s = nbr.GetSymbol()
                if s == "O":
                    shift = max(shift, 58.0); asgn = f"C-O ({c_type})"
                elif s == "N":
                    shift = max(shift, 50.0); asgn = f"C-N ({c_type})"
                elif s == "Cl":
                    shift = max(shift, 40.0); asgn = f"C-Cl ({c_type})"
                elif s == "Br":
                    shift = max(shift, 35.0); asgn = f"C-Br ({c_type})"

            # Alpha-carbonyl correction: if neighbor is sp2 C=O, shift >= 30.0
            is_alpha_carbonyl = False
            for nbr in atom.GetNeighbors():
                if nbr.GetSymbol() == "C" and nbr.GetHybridization() == rdchem.HybridizationType.SP2:
                    # Check if this sp2 carbon has a C=O double bond
                    for b in nbr.GetBonds():
                        other_idx = b.GetOtherAtomIdx(nbr.GetIdx())
                        other_atom = mol.GetAtomWithIdx(other_idx)
                        if (other_atom.GetSymbol() == "O"
                                and b.GetBondType() == Chem.rdchem.BondType.DOUBLE):
                            shift = max(shift, 30.0)
                            asgn = f"C alpha-C=O ({c_type})"
                            is_alpha_carbonyl = True
                            break

            # Adjust for CH3 vs CH2 etc.
            # Alpha-carbonyl CH3 uses reduced correction (-2 instead of -5)
            # to match Silverstein: acetone CH3 ~ 30.0 ppm
            if c_type == "CH3":
                if is_alpha_carbonyl:
                    shift = max(10.0, shift - 2)  # 30-2=28, closer to Silverstein 30
                else:
                    shift = max(10.0, shift - 5)
            elif c_type == "CH2":
                shift = max(15.0, shift)
            zone = "aliphatic"

        # Slight jitter to avoid identical shifts
        shift += (atom.GetIdx() % 5) * 0.5

        # Deduplicate (±1 ppm — narrow window to preserve distinct carbons)
        if not any(abs(shift - s) < 1 for s in seen_shifts):
            peaks.append(C13Peak(shift=round(shift, 1), carbon_type=c_type,
                                  zone=zone, assignment=asgn))
            seen_shifts.add(shift)

    return sorted(peaks, key=lambda p: p.shift)

# ─── UV-Vis 예측 ──────────────────────────────────────────

def _count_conjugated_double_bonds(mol) -> int:
    """Count the number of conjugated double bonds (for Woodward-Fieser diene rules)."""
    if mol is None:
        return 0
    # Use RDKit's conjugated bond detection
    conj_doubles = 0
    for bond in mol.GetBonds():
        if bond.GetIsConjugated() and bond.GetBondTypeAsDouble() >= 2.0:
            conj_doubles += 1
    return conj_doubles


def _woodward_fieser_diene(mol) -> Optional[Tuple[float, float]]:
    """
    Woodward-Fieser rules for conjugated dienes.
    Base value: homodiene (s-cis) = 253 nm, (s-trans) = 217 nm
    Returns (lambda_max, epsilon) or None if not a diene.
    """
    if mol is None:
        return None
    # Check for 1,3-butadiene substructure (conjugated diene)
    diene_pat = Chem.MolFromSmarts("C=CC=C")
    if diene_pat is None or not mol.HasSubstructMatch(diene_pat):
        return None

    base_lambda = 217  # s-trans (heteroannular) base
    # Check if homoannular (diene in same ring)
    ring_info = mol.GetRingInfo()
    matches = mol.GetSubstructMatches(diene_pat)
    for match in matches:
        for ring in ring_info.AtomRings():
            if all(idx in ring for idx in match):
                base_lambda = 253  # homoannular diene
                break

    # Substituent increments (simplified Woodward-Fieser)
    increment = 0
    for match in matches[:1]:  # Use first match
        for idx in match:
            atom = mol.GetAtomWithIdx(idx)
            for nbr in atom.GetNeighbors():
                if nbr.GetIdx() not in match:
                    sym = nbr.GetSymbol()
                    # Alkyl substituent: +5 nm
                    if sym == "C" and not nbr.GetIsAromatic():
                        increment += 5
                    # -OR: +6 nm
                    elif sym == "O" and nbr.GetTotalNumHs() == 0:
                        increment += 6
                    # -OH: +0 nm (already in base)
                    # -Cl: +5 nm
                    elif sym == "Cl":
                        increment += 5
                    # -Br: +5 nm
                    elif sym == "Br":
                        increment += 5
                    # -NR2: +5 nm
                    elif sym == "N":
                        increment += 5
        break

    # Exocyclic double bond: +5 nm per
    for bond in mol.GetBonds():
        if bond.GetBondTypeAsDouble() >= 2.0:
            bi = bond.GetBeginAtomIdx()
            ei = bond.GetEndAtomIdx()
            # Check if exocyclic (one atom in ring, bond not in ring)
            in_ring_b = mol.GetAtomWithIdx(bi).IsInRing()
            in_ring_e = mol.GetAtomWithIdx(ei).IsInRing()
            if (in_ring_b or in_ring_e) and not bond.IsInRing():
                increment += 5

    lambda_max = base_lambda + increment
    epsilon = 8000 + increment * 200  # Rough estimate
    return (lambda_max, epsilon)


def _woodward_fieser_enone(mol) -> Optional[Tuple[float, float]]:
    """
    Woodward-Fieser rules for alpha,beta-unsaturated ketones (enones).
    Base value: 215 nm (acyclic), 202 nm (6-membered ring)
    Returns (lambda_max, epsilon) or None.
    """
    if mol is None:
        return None
    enone_pat = Chem.MolFromSmarts("[CX3](=O)C=C")
    if enone_pat is None or not mol.HasSubstructMatch(enone_pat):
        return None

    base_lambda = 215  # acyclic enone
    # Check if cyclic
    matches = mol.GetSubstructMatches(enone_pat)
    for match in matches:
        carbonyl_c = match[0]
        if mol.GetAtomWithIdx(carbonyl_c).IsInRing():
            ring_info = mol.GetRingInfo()
            for ring in ring_info.AtomRings():
                if carbonyl_c in ring:
                    if len(ring) == 6:
                        base_lambda = 202
                    elif len(ring) == 5:
                        base_lambda = 202
                    break
        break

    # Substituent increments
    increment = 0
    for match in matches[:1]:
        # beta carbon is match[2] (C=C), alpha is match[1]
        if len(match) >= 3:
            beta_idx = match[2]
            alpha_idx = match[1] if len(match) > 1 else None
            # Beta substituents
            beta_atom = mol.GetAtomWithIdx(beta_idx)
            for nbr in beta_atom.GetNeighbors():
                if nbr.GetIdx() not in match:
                    sym = nbr.GetSymbol()
                    if sym == "C" and not nbr.GetIsAromatic():
                        increment += 12  # beta-alkyl
                    elif sym == "O":
                        increment += 35  # beta-OR
                    elif sym == "Cl":
                        increment += 15
                    elif sym == "Br":
                        increment += 25
                    elif sym == "N":
                        increment += 25
            # Alpha substituents
            if alpha_idx is not None:
                alpha_atom = mol.GetAtomWithIdx(alpha_idx)
                for nbr in alpha_atom.GetNeighbors():
                    if nbr.GetIdx() not in match:
                        sym = nbr.GetSymbol()
                        if sym == "C" and not nbr.GetIsAromatic():
                            increment += 10  # alpha-alkyl
                        elif sym == "O":
                            increment += 35
        break

    lambda_max = base_lambda + increment
    epsilon = 12000 + increment * 200
    return (lambda_max, epsilon)


def predict_uvvis(smiles: str) -> List[UVVisPeak]:
    """UV-Vis 예측 (듀얼 뷰: ε + logε, X=200~800nm)

    Approach:
    1. Woodward-Fieser rules for conjugated dienes
    2. Woodward-Fieser rules for enones (alpha,beta-unsaturated carbonyls)
    3. Aromatic chromophore estimation
    4. n→pi* for lone pair systems (C=O, N)
    5. Graceful fallback: sigma→sigma* only if no chromophore detected
    """
    if not RDKIT_OK:
        return [UVVisPeak(260, 10000, "pi→pi*", "aromatic")]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    peaks = []

    # 방향족 고리 개수
    n_arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
    # 공액 이중결합 수
    n_conj = sum(1 for b in mol.GetBonds()
                 if b.GetBondTypeAsDouble() >= 2.0 or b.GetBondTypeAsDouble() == 1.5)
    # 헤테로 원자
    n_N = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "N")
    n_O = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "O")
    n_S = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "S")
    # Carbonyl 확인
    has_carbonyl = mol.HasSubstructMatch(Chem.MolFromSmarts("[CX3]=[OX1]"))
    # Halogen count (for auxochrome effects)
    n_halogens = sum(1 for a in mol.GetAtoms() if a.GetSymbol() in ("F", "Cl", "Br", "I"))

    chromophore_found = False

    # ── Woodward-Fieser: Conjugated diene ──
    diene_result = _woodward_fieser_diene(mol)
    if diene_result:
        lam, eps = diene_result
        peaks.append(UVVisPeak(lam, eps, "pi→pi*",
                               f"conjugated diene (Woodward-Fieser, base+subst)"))
        chromophore_found = True

    # ── Woodward-Fieser: Enone (alpha,beta-unsaturated C=O) ──
    enone_result = _woodward_fieser_enone(mol)
    if enone_result:
        lam, eps = enone_result
        peaks.append(UVVisPeak(lam, eps, "pi→pi*",
                               f"enone (Woodward-Fieser, base+subst)"))
        # Enone also has n→pi*
        peaks.append(UVVisPeak(min(lam + 50, 400), 50, "n→pi*",
                               "enone C=O lone pair"))
        chromophore_found = True

    # ── Isolated C=C (no diene/enone) ──
    if n_conj >= 1 and n_arom_rings == 0 and not diene_result and not enone_result:
        lambda_max = 165 + 30 * max(0, n_conj - 1)
        eps = 8000 * n_conj
        peaks.append(UVVisPeak(lambda_max, eps, "pi→pi*", "C=C conjugated"))
        chromophore_found = True

    # ── 벤젠/방향족 고리 ──
    if n_arom_rings >= 1:
        # K-band (primary band)
        lambda_k = 204
        eps_k = 7000
        # Substituent effects on aromatic ring (additive Woodward-Fieser model)
        auxochrome_shift = 0
        seen_substituents = set()
        for atom in mol.GetAtoms():
            if not atom.GetIsAromatic():
                continue
            for nbr in atom.GetNeighbors():
                if nbr.GetIsAromatic():
                    continue
                if nbr.GetIdx() in seen_substituents:
                    continue
                seen_substituents.add(nbr.GetIdx())
                sym = nbr.GetSymbol()
                if sym == "O" and nbr.GetTotalNumHs() >= 1:
                    auxochrome_shift += 11   # -OH
                elif sym == "O" and nbr.GetTotalNumHs() == 0:
                    auxochrome_shift += 7    # -OR / -OCOR
                elif sym == "N":
                    auxochrome_shift += 13   # -NH2/-NR2
                elif sym == "Cl":
                    auxochrome_shift += 6
                elif sym == "Br":
                    auxochrome_shift += 2
                elif sym == "C" and nbr.GetHybridization() == rdchem.HybridizationType.SP2:
                    # C=O directly on ring (e.g. -COOH, -COOR)
                    auxochrome_shift += 10

        lambda_k += auxochrome_shift + 10 * (n_arom_rings - 1)
        eps_k *= n_arom_rings
        peaks.append(UVVisPeak(lambda_k, eps_k, "pi→pi* (K-band)", "aromatic pi system"))

        # B-band (benzene forbidden at ~254nm)
        peaks.append(UVVisPeak(254 + 5 * (n_arom_rings - 1) + auxochrome_shift // 2,
                               200, "pi→pi* (B-band, forbidden)",
                               "aromatic fine structure"))
        chromophore_found = True

    # ── n→pi* (isolated carbonyl, not enone) ──
    if has_carbonyl and not enone_result:
        peaks.append(UVVisPeak(270, 15, "n→pi*", "C=O lone pair"))
        peaks.append(UVVisPeak(200, 1e4, "pi→pi*", "C=O pi system"))
        chromophore_found = True

    # ── N lone pair (amine, not amide) ──
    if n_N > 0 and not mol.HasSubstructMatch(Chem.MolFromSmarts("[NX3][CX3]=O")):
        peaks.append(UVVisPeak(220, 3000, "n→sigma*", "N lone pair"))

    # ── S lone pair ──
    if n_S > 0:
        peaks.append(UVVisPeak(215, 1500, "n→sigma*", "S lone pair"))

    # ── 확장 공액계 (naphthalene, anthracene) ──
    if n_arom_rings >= 2:
        # Naphthalene ~220,275,310; Anthracene ~250,350,375
        if n_arom_rings == 2:
            peaks.append(UVVisPeak(275, 5000, "pi→pi*", "2-ring aromatic (naphthalene-type)"))
            peaks.append(UVVisPeak(310, 300, "pi→pi* (p-band)", "2-ring fine structure"))
        elif n_arom_rings >= 3:
            peaks.append(UVVisPeak(350, 8000, "pi→pi*",
                                   f"{n_arom_rings}-ring aromatic (anthracene-type)"))
            peaks.append(UVVisPeak(375, 6000, "pi→pi* (p-band)",
                                   f"{n_arom_rings}-ring fine structure"))

    # ── Graceful fallback: only sigma→sigma* ──
    if not chromophore_found:
        peaks.append(UVVisPeak(150, 5e4, "sigma→sigma*", "C-C, C-H sigma bonds (no chromophore)"))

    return sorted(peaks, key=lambda p: p.wavelength)

# ─── 통합 예측 함수 ───────────────────────────────────────

def predict_all(smiles: str) -> PredictedSpectra:
    """모든 스펙트럼 예측 통합 함수"""
    warnings = []
    formula = ""

    if RDKIT_OK:
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            formula = rdMolDescriptors.CalcMolFormula(mol)
        else:
            warnings.append(f"유효하지 않은 SMILES: {smiles}")
    else:
        warnings.append("RDKit 미설치 — 기본 예측만 제공")

    return PredictedSpectra(
        smiles=smiles,
        formula=formula,
        ir_peaks=predict_ir(smiles),
        raman_peaks=predict_raman(smiles),
        h1_nmr_peaks=predict_h1_nmr(smiles),
        c13_peaks=predict_c13_nmr(smiles),
        uvvis_peaks=predict_uvvis(smiles),
        warnings=warnings,
    )

# ─── 간단한 테스트 ────────────────────────────────────────

if __name__ == "__main__":
    test_smiles = {
        "benzene": "c1ccccc1",
        "ethanol": "CCO",
        "acetic acid": "CC(=O)O",
        "aniline": "Nc1ccccc1",
    }
    for name, smi in test_smiles.items():
        result = predict_all(smi)
        print(f"\n{'='*50}")
        print(f"{name} ({result.formula})")
        print(f"IR: {len(result.ir_peaks)} peaks")
        print(f"Raman: {len(result.raman_peaks)} peaks")
        print(f"1H-NMR: {len(result.h1_nmr_peaks)} signals")
        print(f"13C-NMR: {len(result.c13_peaks)} signals")
        print(f"UV-Vis: {len(result.uvvis_peaks)} transitions")
        if result.warnings:
            print(f"Warnings: {result.warnings}")
