#!/usr/bin/env python3
"""
reaction_animation_engine.py -- 3D 반응 메커니즘 애니메이션 엔진
========================================================
반응물 SMILES + 생성물 SMILES -> 프레임별 3D 좌표/결합 보간
-> ReactionTrajectory 생성 (popup_reaction_animation.py가 소비)

지원 반응 유형:
  1) 일반 보간 (MCS 기반 원자 매핑)
  2) SN2 (배면공격 + Walden 반전)
  3) 양성자 전달 (산-염기)
  4) 의자형 뒤집기 (Chair Flip)

핵심 기술:
  - RDKit EmbedMolecule + MMFF 최적화
  - MCS (Maximum Common Substructure) 기반 원자 매핑
  - 선형/ease-in-out 좌표 보간
  - 포물선 에너지 프로파일
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# RDKit import guard
# ============================================================
RDKIT_AVAILABLE = False
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdFMCS, rdMolAlign, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    logger.warning("RDKit not available - ReactionAnimationEngine disabled")


# ============================================================
# Section 1: Data Classes
# ============================================================

@dataclass
class BondChange:
    """프레임 구간 내 결합 변화 기술자."""
    frame_start: int    # 결합 변화 시작 프레임
    frame_end: int      # 결합 변화 완료 프레임
    atom_i: int         # 원자 인덱스 1
    atom_j: int         # 원자 인덱스 2
    change_type: str    # "break" | "form" | "weaken"


@dataclass
class ChargeLabel:
    """프레임별 특정 원자에 표시할 전하 라벨."""
    atom_idx: int       # 대상 원자 인덱스
    text: str           # 표시 텍스트: "δ+", "δ-", "+", "-", "‡" 등
    frame_start: int    # 표시 시작 프레임
    frame_end: int      # 표시 종료 프레임


@dataclass
class ArrowAnnotation:
    """프레임별 화살표 (접근 궤적, 이탈 방향 등)."""
    from_atom: int          # 시작 원자 (또는 -1이면 from_pos 사용)
    to_atom: int            # 끝 원자 (또는 -1이면 to_pos 사용)
    from_pos: Optional[Tuple[float, float, float]] = None
    to_pos: Optional[Tuple[float, float, float]] = None
    frame_start: int = 0
    frame_end: int = 0
    style: str = "solid"    # "solid" | "dashed" | "dotted"
    color: str = "yellow"   # "yellow" | "green" | "red"


@dataclass
class ReactionTrajectory:
    """반응 애니메이션 전체 궤적 데이터."""
    frames: List[Dict[int, Tuple[float, float, float]]]         # 프레임별 atom_idx -> (x, y, z)
    atom_symbols: Dict[int, str]                                 # atom_idx -> element symbol
    bonds_per_frame: List[Dict[Tuple[int, int], float]]          # 프레임별 (i,j) -> bond_order
    energies: List[float]                                        # 프레임별 상대 에너지 (kcal/mol)
    bond_changes: List[BondChange]                               # 결합 변화 목록
    labels: List[str]                                            # 프레임별 라벨 ("reactant" / "transition_state" / "product")
    n_frames: int                                                # 총 프레임 수
    charge_labels: List[ChargeLabel] = field(default_factory=list)  # 전하 라벨 목록
    arrows: List[ArrowAnnotation] = field(default_factory=list)     # 화살표 주석
    bond_styles: List[Dict[Tuple[int, int], str]] = field(default_factory=list)
    # 프레임별 (i,j) -> "solid" | "dashed" | "dotted"


# ============================================================
# Section 2: Helper Utilities
# ============================================================

def _ease_in_out(t: float) -> float:
    """Smoothstep ease-in-out: 0->0, 0.5->0.5, 1->1."""
    return 3 * t * t - 2 * t * t * t


def _cosine_interp(t: float) -> float:
    """Cosine interpolation: smoother than linear, 0->0, 0.5->0.5, 1->1.
    Uses half-cosine curve for natural ease-in/ease-out motion."""
    return 0.5 * (1.0 - math.cos(math.pi * t))


def _lerp_coords(
    c1: Tuple[float, float, float],
    c2: Tuple[float, float, float],
    t: float,
    smooth: bool = True,
) -> Tuple[float, float, float]:
    """두 3D 좌표 간 보간. smooth=True 시 코사인 보간 사용."""
    s = _cosine_interp(t) if smooth else t
    return (
        c1[0] + (c2[0] - c1[0]) * s,
        c1[1] + (c2[1] - c1[1]) * s,
        c1[2] + (c2[2] - c1[2]) * s,
    )


def _parabolic_energy(t: float, barrier: float = 15.0) -> float:
    """포물선 에너지: E(t) = barrier * 4*t*(1-t).  최대값 = barrier at t=0.5."""
    return barrier * 4.0 * t * (1.0 - t)


def _gaussian_energy(t: float, barrier: float = 50.0, sigma: float = 0.2) -> float:
    """Gaussian 에너지 프로파일: 전이상태(t=0.5)에서 피크.
    더 현실적인 활성화 에너지 장벽 모델링.
    Args:
        t: 프레임 진행 비율 (0~1)
        barrier: 활성화 에너지 장벽 (kcal/mol)
        sigma: 가우시안 폭 (0.2 = 비교적 좁은 장벽)
    """
    # E = barrier * exp(-((t - 0.5)^2) / (2 * sigma^2))
    return barrier * math.exp(-((t - 0.5) ** 2) / (2.0 * sigma * sigma))


def _frame_label(t: float) -> str:
    """프레임 위치에 따른 라벨."""
    if t < 0.25:
        return "reactant"
    elif t > 0.75:
        return "product"
    else:
        return "transition_state"


def _embed_3d(mol):
    """RDKit 분자에 3D 좌표 부여 + MMFF 최적화. 실패 시 None 반환."""
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    if AllChem.EmbedMolecule(mol, params) != 0:
        # 폴백: 기본 임베딩
        if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
            logger.warning("_embed_3d: EmbedMolecule 2회 연속 실패 (ETKDGv3 + fallback)")
            return None
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    except Exception as e:
        logger.warning("MMFF optimization failed for embedded molecule: %s", e)
    return mol


def _get_coords_dict(mol) -> Dict[int, Tuple[float, float, float]]:
    """RDKit 분자 -> {atom_idx: (x,y,z)} 딕셔너리."""
    conf = mol.GetConformer()
    coords = {}
    for i in range(mol.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        coords[i] = (round(pos.x, 4), round(pos.y, 4), round(pos.z, 4))
    return coords


def _get_symbols_dict(mol) -> Dict[int, str]:
    """RDKit 분자 -> {atom_idx: element_symbol}."""
    return {a.GetIdx(): a.GetSymbol() for a in mol.GetAtoms()}


def _get_bonds_dict(mol) -> Dict[Tuple[int, int], float]:
    """RDKit 분자 -> {(i,j): bond_order}."""
    bonds = {}
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        bo = bond.GetBondTypeAsDouble()
        key = (min(i, j), max(i, j))
        bonds[key] = bo
    return bonds


def _centroid(coords: Dict[int, Tuple[float, float, float]]) -> np.ndarray:
    """좌표 딕셔너리의 무게중심."""
    pts = np.array(list(coords.values()))
    return pts.mean(axis=0)


def _translate_coords(
    coords: Dict[int, Tuple[float, float, float]],
    offset: np.ndarray,
) -> Dict[int, Tuple[float, float, float]]:
    """모든 좌표를 offset만큼 평행이동."""
    return {k: (v[0] + offset[0], v[1] + offset[1], v[2] + offset[2])
            for k, v in coords.items()}


def _norm(v: np.ndarray) -> np.ndarray:
    """단위 벡터."""
    n = np.linalg.norm(v)
    return v / n if n > 1e-8 else np.array([0.0, 0.0, 1.0])


# ============================================================
# Section 3: MCS-based Atom Mapping
# ============================================================

def _map_atoms_mcs(mol_r, mol_p) -> Optional[Dict[int, int]]:
    """MCS(Maximum Common Substructure)로 reactant->product 원자 매핑.

    Returns:
        {reactant_atom_idx: product_atom_idx} 또는 None
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_map_atoms_mcs: RDKit 미사용 상태 — MCS 매핑 불가")
        return None
    try:
        mcs = rdFMCS.FindMCS(
            [mol_r, mol_p],
            timeout=5,
            bondCompare=rdFMCS.BondCompare.CompareAny,
            atomCompare=rdFMCS.AtomCompare.CompareElements,
        )
        if mcs.numAtoms == 0:
            logger.warning("_map_atoms_mcs: MCS numAtoms=0 — 공통 부분구조 없음")
            return None
        patt = Chem.MolFromSmarts(mcs.smartsString)
        if patt is None:
            logger.warning("_map_atoms_mcs: SMARTS 패턴 파싱 실패 — smartsString=%s", mcs.smartsString)
            return None
        match_r = mol_r.GetSubstructMatch(patt)
        match_p = mol_p.GetSubstructMatch(patt)
        if not match_r or not match_p or len(match_r) != len(match_p):
            logger.warning("_map_atoms_mcs: 매치 불일치 — match_r=%d, match_p=%d", len(match_r) if match_r else 0, len(match_p) if match_p else 0)
            return None
        return {match_r[i]: match_p[i] for i in range(len(match_r))}
    except Exception as e:
        logger.warning(f"MCS atom mapping failed: {e}")
        return None


def _map_atoms_substructure(mol_r, mol_p) -> Optional[Dict[int, int]]:
    """GetSubstructMatch 폴백 매핑."""
    try:
        match = mol_p.GetSubstructMatch(mol_r)
        if match and len(match) == mol_r.GetNumAtoms():
            return {i: match[i] for i in range(len(match))}
        match = mol_r.GetSubstructMatch(mol_p)
        if match and len(match) == mol_p.GetNumAtoms():
            return {match[i]: i for i in range(len(match))}
    except Exception as e:
        logger.warning("Substructure atom mapping failed: %s", e)
    return None


# ============================================================
# Section 4: ReactionAnimationEngine
# ============================================================

class ReactionAnimationEngine:
    """반응 애니메이션 프레임 생성 엔진.

    사용법:
        engine = ReactionAnimationEngine()
        traj = engine.generate_frames("CCO", "CC=O", n_frames=40)
        # traj.frames[i] -> {atom_idx: (x,y,z)}
    """

    # -- 전이 구간 (결합 부분 형성/절단) --
    TRANSITION_START = 0.30
    TRANSITION_END = 0.70

    def __init__(self):
        if not RDKIT_AVAILABLE:
            logger.error("RDKit 미설치 — ReactionAnimationEngine 사용 불가")

    # --------------------------------------------------------
    # 4-1. 범용 프레임 생성
    # --------------------------------------------------------
    def generate_frames(
        self,
        reactant_smiles: str,
        product_smiles: str,
        n_frames: int = 40,
        barrier_kcal: float = 15.0,
    ) -> Optional[ReactionTrajectory]:
        """범용 반응 애니메이션 프레임 생성 (자동 특수경로 감지).

        1. 반응 유형 자동 감지 → 특수 애니메이션 경로 우선
        2. SMILES -> RDKit mol + 3D 좌표
        3. MCS 원자 매핑
        4. 프레임별 좌표 보간 + 결합 차수 전이
        5. 에너지 프로파일 (포물선)
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드: 외부 입력 검증
        if not isinstance(reactant_smiles, str) or not reactant_smiles.strip():
            logger.warning(f"generate_frames: reactant_smiles 타입/값 불일치 ({type(reactant_smiles).__name__})")
            return None
        if not isinstance(product_smiles, str) or not product_smiles.strip():
            logger.warning(f"generate_frames: product_smiles 타입/값 불일치 ({type(product_smiles).__name__})")
            return None
        if not isinstance(n_frames, int) or n_frames < 2:
            logger.warning(f"generate_frames: n_frames 값 불일치 ({n_frames})")
            n_frames = 40  # 기본값 폴백
        try:
            # ── 자동 특수경로 감지 (Smart Dispatch) ──
            traj = self._try_specialized_dispatch(
                reactant_smiles, product_smiles, n_frames, barrier_kcal
            )
            if traj is not None:
                return traj
            # ── 범용 경로 ──
            return self._generate_frames_impl(
                reactant_smiles, product_smiles, n_frames, barrier_kcal
            )
        except Exception as e:
            logger.error(f"generate_frames 실패: {e}", exc_info=True)
            return None

    def _try_specialized_dispatch(
        self,
        reactant_smi: str,
        product_smi: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        """반응 유형 자동 감지 → 특수 애니메이션 경로 시도."""
        mol_r = Chem.MolFromSmiles(reactant_smi)
        mol_p = Chem.MolFromSmiles(product_smi)
        if mol_r is None or mol_p is None:
            return None

        def _canon_smiles(smiles: str) -> str:
            mol = Chem.MolFromSmiles(smiles)
            return Chem.MolToSmiles(mol) if mol is not None else ""

        aspirin_product = _canon_smiles("CC(=O)Oc1ccccc1C(=O)O")
        salicylic_acid = _canon_smiles("O=C(O)c1ccccc1O")
        acetic_anhydride = _canon_smiles("CC(=O)OC(C)=O")
        product_canon = Chem.MolToSmiles(mol_p)
        reactant_parts = {
            _canon_smiles(part)
            for part in reactant_smi.split(".")
            if isinstance(part, str) and part.strip()
        }
        if (
            product_canon == aspirin_product
            and salicylic_acid in reactant_parts
            and acetic_anhydride in reactant_parts
        ):
            result = self.generate_aspirin_o_acetylation_animation(
                n_frames=n_frames,
                barrier_kcal=barrier_kcal,
            )
            if result is not None:
                return result

        alkene = Chem.MolFromSmarts('[C]=[C]')
        br2 = Chem.MolFromSmarts('Br-Br')
        product_cbr = Chem.MolFromSmarts('[C]-[Br]')
        if (
            alkene is not None
            and br2 is not None
            and product_cbr is not None
            and mol_r.HasSubstructMatch(alkene)
            and mol_r.HasSubstructMatch(br2)
            and len(mol_p.GetSubstructMatches(product_cbr)) >= 2
        ):
            result = self.generate_bromination_addition_animation(
                n_frames=n_frames,
                barrier_kcal=barrier_kcal,
            )
            if result is not None:
                return result

        # Detect leaving group (halide in reactant, not in product)
        _halides = {'F', 'Cl', 'Br', 'I'}
        r_atoms = {a.GetSymbol() for a in mol_r.GetAtoms()}
        p_atoms = {a.GetSymbol() for a in mol_p.GetAtoms()}
        leaving = r_atoms & _halides - p_atoms

        # ── (1) SN2 / E2: halide leaving group detected ──
        _HALIDE_PRIORITY = {'I': 0, 'Br': 1, 'Cl': 2, 'F': 3}  # isinstance(dict) guaranteed - literal
        if leaving:
            lg = sorted(leaving, key=lambda x: _HALIDE_PRIORITY.get(x, 4))[0]
            entering = (p_atoms - r_atoms) & {'O', 'N', 'S'}

            # E2-like: halide leaves AND double bond count increases
            r_dbl = sum(1 for b in mol_r.GetBonds() if b.GetBondTypeAsDouble() >= 2.0)
            p_dbl = sum(1 for b in mol_p.GetBonds() if b.GetBondTypeAsDouble() >= 2.0)
            if p_dbl > r_dbl:
                # E2 elimination dispatch — use [OH-] as default base
                result = self.generate_e2_elimination(
                    reactant_smi, '[OH-]', n_frames, barrier_kcal
                )
                if result is not None:
                    return result

            if entering:
                # SN2 dispatch — use nucleophile from product
                nuc = '[OH-]' if 'O' in entering else '[NH2-]' if 'N' in entering else '[SH-]'
                result = self.generate_sn2_animation(
                    reactant_smi, nuc, lg, n_frames, barrier_kcal
                )
                if result is not None:
                    return result

        # ── (2) Diels-Alder: butadiene + alkene → cyclohexene ──
        # Detect by ring count increase AND both reactant having C=C
        r_ring_count = Chem.GetSSSR(Chem.RWMol(mol_r))  # returns int
        p_ring_count = Chem.GetSSSR(Chem.RWMol(mol_p))
        # GetSSSR may return vector or int depending on version; force int
        if not isinstance(r_ring_count, int):
            r_ring_count = len(r_ring_count)
        if not isinstance(p_ring_count, int):
            p_ring_count = len(p_ring_count)
        r_dbl_total = sum(1 for b in mol_r.GetBonds() if b.GetBondTypeAsDouble() >= 2.0)
        if p_ring_count > r_ring_count and r_dbl_total >= 2:
            # Could be [4+2] — already handled by Diels-Alder in generate_frames
            # via the existing code, but let's try explicit dispatch
            pass  # Diels-Alder is detected elsewhere via product matching

        # ── (3) Suzuki coupling: Ar-Br → Ar-Ar (biaryl) ──
        if leaving and any(a.GetIsAromatic() for a in mol_r.GetAtoms()):
            # Check if product has more aromatic C-C bonds (biaryl formation)
            p_aromatic_count = sum(1 for a in mol_p.GetAtoms() if a.GetIsAromatic())
            r_aromatic_count = sum(1 for a in mol_r.GetAtoms() if a.GetIsAromatic())
            if p_aromatic_count > r_aromatic_count:
                # Suzuki-like cross-coupling — use generic with enhanced detection
                pass  # fall through to generic with improved _detect_bond_changes

        # ── (4) Sigmatropic rearrangement: Claisen / Cope ──
        # Claisen: allyl vinyl ether → γ,δ-unsaturated carbonyl
        # Cope: 1,5-diene → shifted 1,5-diene
        # Detect: reactant has O in ether position + C=C, product has C=O (Claisen)
        #         or both are dienes with same formula (Cope)
        r_formula = Chem.rdMolDescriptors.CalcMolFormula(mol_r)
        p_formula = Chem.rdMolDescriptors.CalcMolFormula(mol_p)

        r_has_ether_vinyl = (
            mol_r.HasSubstructMatch(Chem.MolFromSmarts('[C]=[C]-[O]-[C]=[C]'))
            if Chem.MolFromSmarts('[C]=[C]-[O]-[C]=[C]') else False
        )
        p_has_carbonyl = (
            mol_p.HasSubstructMatch(Chem.MolFromSmarts('[C]=[O]'))
            if Chem.MolFromSmarts('[C]=[O]') else False
        )
        if r_has_ether_vinyl and p_has_carbonyl:
            result = self._generate_pericyclic_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="claisen"
            )
            if result is not None:
                return result

        # Cope: 1,5-hexadiene isomerization (same formula, both have C=C-C-C=C)
        r_diene_patt = Chem.MolFromSmarts('[C]=[C]-[C]-[C]=[C]')
        if (r_formula == p_formula and r_diene_patt
                and mol_r.HasSubstructMatch(r_diene_patt)
                and mol_p.HasSubstructMatch(r_diene_patt)):
            result = self._generate_pericyclic_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="cope"
            )
            if result is not None:
                return result

        # ── (5) Carbonyl addition / rearrangement reactions ──
        # Beckmann: oxime → amide (N-O break, C-N migration)
        r_has_oxime = mol_r.HasSubstructMatch(Chem.MolFromSmarts('[C]=[N]-[O]'))
        p_has_amide = mol_p.HasSubstructMatch(Chem.MolFromSmarts('[C](=[O])-[N]'))
        if r_has_oxime and p_has_amide:
            result = self._generate_carbonyl_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="beckmann"
            )
            if result is not None:
                return result

        # Baeyer-Villiger: ketone → ester (O insertion next to C=O)
        r_has_ketone = mol_r.HasSubstructMatch(Chem.MolFromSmarts('[C]-[C](=[O])-[C]'))
        p_has_ester = mol_p.HasSubstructMatch(Chem.MolFromSmarts('[C](=[O])-[O]-[C]'))
        if r_has_ketone and p_has_ester:
            result = self._generate_carbonyl_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="baeyer_villiger"
            )
            if result is not None:
                return result

        # Aldol: ketone/aldehyde → β-hydroxy carbonyl
        r_has_co = mol_r.HasSubstructMatch(Chem.MolFromSmarts('[C](=[O])'))
        p_has_oh = mol_p.HasSubstructMatch(Chem.MolFromSmarts('[OH]'))  # implicit H SMARTS
        p_has_co = mol_p.HasSubstructMatch(Chem.MolFromSmarts('[C](=[O])'))
        if r_has_co and p_has_oh and p_has_co and mol_p.GetNumHeavyAtoms() > mol_r.GetNumHeavyAtoms():
            result = self._generate_carbonyl_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="aldol"
            )
            if result is not None:
                return result

        # Wittig: aldehyde/ketone → alkene (C=O replaced by C=C)
        p_has_alkene = mol_p.HasSubstructMatch(Chem.MolFromSmarts('[C]=[C]'))
        if (r_has_co and p_has_alkene
                and not p_has_carbonyl
                and mol_p.GetNumHeavyAtoms() >= mol_r.GetNumHeavyAtoms()):
            result = self._generate_carbonyl_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="wittig"
            )
            if result is not None:
                return result

        # Pinacol: vicinal diol → ketone (1,2-shift)
        r_has_diol = mol_r.HasSubstructMatch(Chem.MolFromSmarts('[C]([O])-[C]([O])'))
        p_has_ketone2 = mol_p.HasSubstructMatch(Chem.MolFromSmarts('[C](=[O])'))
        if r_has_diol and p_has_ketone2:
            result = self._generate_carbonyl_rearrangement(
                reactant_smi, product_smi, n_frames, barrier_kcal,
                rearrangement_type="pinacol"
            )
            if result is not None:
                return result

        return None

    def _generate_frames_impl(
        self,
        reactant_smiles: str,
        product_smiles: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        # N 타입 가드: SMILES 문자열 검증
        if not isinstance(reactant_smiles, str) or not reactant_smiles.strip():
            logger.warning(f"_generate_frames_impl: reactant_smiles 타입/값 불일치 ({type(reactant_smiles).__name__})")
            return None
        if not isinstance(product_smiles, str) or not product_smiles.strip():
            logger.warning(f"_generate_frames_impl: product_smiles 타입/값 불일치 ({type(product_smiles).__name__})")
            return None

        # 1) SMILES -> Mol + 3D
        mol_r = Chem.MolFromSmiles(reactant_smiles)
        mol_p = Chem.MolFromSmiles(product_smiles)
        if mol_r is None or mol_p is None:
            logger.warning("SMILES 파싱 실패")
            return None

        mol_r3d = _embed_3d(Chem.RWMol(mol_r))
        mol_p3d = _embed_3d(Chem.RWMol(mol_p))
        if mol_r3d is None or mol_p3d is None:
            logger.warning("3D 임베딩 실패")
            return None

        # 2) 원자 매핑
        atom_map = _map_atoms_mcs(mol_r3d, mol_p3d)
        if atom_map is None:
            atom_map = _map_atoms_substructure(mol_r3d, mol_p3d)
        if atom_map is None:
            logger.warning("원자 매핑 실패 — 인덱스 순서 폴백 사용")
            n_common = min(mol_r3d.GetNumAtoms(), mol_p3d.GetNumAtoms())
            atom_map = {i: i for i in range(n_common)}

        # 3) 좌표 & 심벌
        coords_r = _get_coords_dict(mol_r3d)
        coords_p = _get_coords_dict(mol_p3d)
        symbols_r = _get_symbols_dict(mol_r3d)
        symbols_p = _get_symbols_dict(mol_p3d)
        bonds_r = _get_bonds_dict(mol_r3d)
        bonds_p = _get_bonds_dict(mol_p3d)

        # [FIX-BLACKHOLE] Fragment-aware centering to prevent "collapse to single point"
        # When reactant SMILES contains multiple fragments (e.g. "A.B"),
        # center each fragment independently and spread them apart.
        # Previous: single centroid for all atoms => all fragments pile up at origin.

        # Detect reactant fragments
        r_frags = Chem.GetMolFrags(mol_r3d, asMols=False)  # tuple of atom-index tuples
        if not isinstance(r_frags, (list, tuple)) or len(r_frags) == 0:
            r_frags = [tuple(range(mol_r3d.GetNumAtoms()))]

        # Center the overall reactant to origin
        centroid_r = _centroid(coords_r)
        coords_r = _translate_coords(coords_r, -centroid_r)

        # Product alignment and centering
        try:
            rdMolAlign.AlignMol(mol_p3d, mol_r3d)
            coords_p = _get_coords_dict(mol_p3d)
        except Exception as e:
            logger.warning("Product alignment to reactant failed: %s", e)
        centroid_p = _centroid(coords_p)
        coords_p = _translate_coords(coords_p, -centroid_p)

        # Separate reactant fragments spatially so they approach from different directions
        initial_sep = 4.0  # Angstrom -- initial separation distance
        n_frags = len(r_frags)
        if n_frags >= 2:
            # Multi-fragment: spread fragments radially around origin
            for fi_idx, frag_indices in enumerate(r_frags):
                # Compute per-fragment centroid (in already-centered coords)
                frag_coords = {i: coords_r[i] for i in frag_indices if i in coords_r}
                if not frag_coords:
                    continue
                frag_cent = _centroid(frag_coords)
                # Assign radial direction: first fragment goes -x, second +x, etc.
                angle = math.pi * (2.0 * fi_idx / n_frags + 0.5)  # spread evenly
                direction = np.array([math.cos(angle), math.sin(angle), 0.0])
                # Move fragment: center it at its own centroid, then offset outward
                target_offset = direction * initial_sep - frag_cent
                for aidx in frag_indices:
                    if aidx in coords_r:
                        c = coords_r[aidx]
                        coords_r[aidx] = (c[0] + target_offset[0],
                                          c[1] + target_offset[1],
                                          c[2] + target_offset[2])
            # Product: offset to +x for separation
            coords_p = _translate_coords(coords_p, np.array([initial_sep, 0.0, 0.0]))
        else:
            # Single fragment: original left/right separation
            coords_r = _translate_coords(coords_r, np.array([-initial_sep / 2, 0.0, 0.0]))
            coords_p = _translate_coords(coords_p, np.array([initial_sep / 2, 0.0, 0.0]))

        # 4) 매핑된 원자 + 미매핑 원자 통합 인덱스
        all_symbols = dict(symbols_r)
        # 생성물에만 있는 원자 추가
        max_idx = max(all_symbols.keys()) if all_symbols else -1
        reverse_map = {v: k for k, v in atom_map.items()}
        p_only_remap = {}  # product_idx -> unified_idx
        for pidx in range(mol_p3d.GetNumAtoms()):
            if pidx not in reverse_map:
                max_idx += 1
                p_only_remap[pidx] = max_idx
                if not isinstance(symbols_p, dict):  # Rule N: type guard
                    symbols_p = {}
                all_symbols[max_idx] = symbols_p.get(pidx, "X")

        # 5) 결합 변화 탐지 — 3D mol 기반 + SMILES 기반 폴백
        bond_changes = self._detect_bond_changes(
            bonds_r, bonds_p, atom_map, p_only_remap, n_frames
        )
        # 3D 기반 탐지가 빈 결과면 SMILES 기반 경량 탐지로 보충
        if not bond_changes:
            bond_changes = self._detect_bond_changes_from_smiles(
                reactant_smiles, product_smiles, n_frames
            )

        # 6) 프레임 생성
        frames = []
        bonds_per_frame = []
        energies = []
        labels = []

        # 3단계 모델: 접근(0~0.3) → 전이상태(0.3~0.7) → 분리(0.7~1.0)
        phase1_end = 0.30  # 접근 단계 끝
        phase2_end = 0.70  # 전이상태 끝

        # [FIX-BLACKHOLE] "Centered" positions = where atoms are at end of approach phase.
        # For multi-fragment: each fragment's centroid moves to origin;
        # for single-fragment: undo the left/right separation offset.
        if n_frags >= 2:
            # Multi-fragment: compute per-atom centered position by removing
            # each fragment's offset (atoms move toward origin while keeping
            # internal fragment geometry)
            coords_r_centered = {}
            for fi_idx, frag_indices in enumerate(r_frags):
                frag_coords = {i: coords_r[i] for i in frag_indices if i in coords_r}
                if not frag_coords:
                    continue
                frag_cent = _centroid(frag_coords)
                for aidx in frag_indices:
                    if aidx in coords_r:
                        c = coords_r[aidx]
                        coords_r_centered[aidx] = (
                            c[0] - frag_cent[0], c[1] - frag_cent[1], c[2] - frag_cent[2]
                        )
            # Product centered = product at origin (undo +x offset)
            coords_p_centered = _translate_coords(coords_p, np.array([-initial_sep, 0.0, 0.0]))
        else:
            # Single fragment: undo left/right offset
            coords_p_centered = _translate_coords(coords_p, np.array([-initial_sep / 2, 0.0, 0.0]))
            coords_r_centered = _translate_coords(coords_r, np.array([initial_sep / 2, 0.0, 0.0]))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            frame_coords = {}
            frame_bonds = {}

            # 단계별 보간 계수 계산
            if t < phase1_end:
                # Phase 1: 접근 — 분자들이 서로 가까워짐
                phase_t = t / phase1_end  # 0→1
                approach = _ease_in_out(phase_t)
                bond_t = 0.0  # 결합 변화 없음
                for r_idx, p_idx in atom_map.items():
                    if not isinstance(coords_r, dict):  # Rule N: type guard
                        coords_r = {}
                    c_r = coords_r.get(r_idx, (0, 0, 0))
                    if not isinstance(coords_r_centered, dict):  # Rule N: type guard
                        coords_r_centered = {}
                    c_r_center = coords_r_centered.get(r_idx, (0, 0, 0))
                    # 반응물: 초기 위치 → 중앙으로 이동
                    frame_coords[r_idx] = _lerp_coords(c_r, c_r_center, approach, smooth=False)
            elif t < phase2_end:
                # Phase 2: 전이상태 — 결합 변화 발생
                phase_t = (t - phase1_end) / (phase2_end - phase1_end)  # 0→1
                morph = _ease_in_out(phase_t)
                bond_t = morph  # 결합 변화 진행
                for r_idx, p_idx in atom_map.items():
                    c_r = coords_r_centered.get(r_idx, (0, 0, 0))
                    if not isinstance(coords_p_centered, dict):  # Rule N: type guard
                        coords_p_centered = {}
                    c_p = coords_p_centered.get(p_idx, (0, 0, 0))
                    # 반응물 위치 → 생성물 위치로 모핑
                    frame_coords[r_idx] = _lerp_coords(c_r, c_p, morph, smooth=False)
            else:
                # Phase 3: 분리 — 생성물이 완성되고 이탈기 분리
                phase_t = (t - phase2_end) / (1.0 - phase2_end)  # 0→1
                separate = _ease_in_out(phase_t)
                bond_t = 1.0  # 결합 변화 완료
                for r_idx, p_idx in atom_map.items():
                    c_p_center = coords_p_centered.get(p_idx, (0, 0, 0))
                    if not isinstance(coords_p, dict):  # Rule N: type guard
                        coords_p = {}
                    c_p_final = coords_p.get(p_idx, (0, 0, 0))
                    # 중앙 → 최종 생성물 위치로 분리
                    frame_coords[r_idx] = _lerp_coords(c_p_center, c_p_final, separate, smooth=False)

            # 반응물에만 있는 원자: Phase 1은 그대로, 이후 이탈
            for r_idx in coords_r:
                if r_idx not in atom_map and r_idx not in frame_coords:
                    if not isinstance(coords_r, dict):  # Rule N: type guard
                        coords_r = {}
                    c = coords_r.get(r_idx, (0, 0, 0))
                    if t < phase1_end:
                        # 접근 중: 반응물과 함께 이동
                        phase_t = t / phase1_end
                        if not isinstance(coords_r_centered, dict):  # Rule N: type guard
                            coords_r_centered = {}
                        c_center = coords_r_centered.get(r_idx, c)
                        frame_coords[r_idx] = _lerp_coords(c, c_center, _ease_in_out(phase_t), smooth=False)
                    else:
                        # 이탈: 반대 방향으로 멀어짐
                        leave_t = (t - phase1_end) / (1.0 - phase1_end)
                        c_center = coords_r_centered.get(r_idx, c)
                        offset = 5.0 * _ease_in_out(leave_t)  # 5Å 이탈
                        frame_coords[r_idx] = (c_center[0] - offset, c_center[1], c_center[2])

            # 생성물에만 있는 원자: Phase 2 중반부터 등장
            for p_idx, unified_idx in p_only_remap.items():
                if not isinstance(coords_p, dict):  # Rule N: type guard
                    coords_p = {}
                c = coords_p.get(p_idx, (0, 0, 0))
                if not isinstance(coords_p_centered, dict):  # Rule N: type guard
                    coords_p_centered = {}
                c_center = coords_p_centered.get(p_idx, (0, 0, 0))
                if t < phase1_end:
                    # 아직 등장 안 함 — 멀리 배치
                    frame_coords[unified_idx] = (c[0] + 5.0, c[1], c[2])
                elif t < phase2_end:
                    # 점차 등장
                    phase_t = (t - phase1_end) / (phase2_end - phase1_end)
                    far = (c[0] + 5.0, c[1], c[2])
                    frame_coords[unified_idx] = _lerp_coords(far, c_center, _ease_in_out(phase_t), smooth=False)
                else:
                    # 생성물과 함께 분리
                    phase_t = (t - phase2_end) / (1.0 - phase2_end)
                    frame_coords[unified_idx] = _lerp_coords(c_center, c, _ease_in_out(phase_t), smooth=False)

            # 결합 차수 보간 — bond_t 기반
            frame_bonds = self._interpolate_bonds(
                bonds_r, bonds_p, atom_map, p_only_remap, bond_t
            )

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            energies.append(_gaussian_energy(t, barrier_kcal))
            labels.append(_frame_label(t))

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels,
            n_frames=n_frames,
        )

    # --------------------------------------------------------
    # 4-2. SN2 반응 애니메이션
    # --------------------------------------------------------
    def generate_aspirin_o_acetylation_animation(
        self,
        n_frames: int = 48,
        barrier_kcal: float = 18.0,
    ) -> Optional[ReactionTrajectory]:
        """Target-bond-only aspirin O-acetylation trajectory.

        Curated nucleophilic acyl substitution for salicylic acid + acetic
        anhydride -> aspirin. The aromatic scaffold stays fixed; the phenoxy O
        attacks the acyl carbon, the O-acyl bond forms, and the acyl-O leaving
        bond breaks. This prevents generic whole-molecule morphing.
        """
        if not isinstance(n_frames, int) or n_frames < 24:
            n_frames = 48

        symbols = {
            0: "C", 1: "C", 2: "C", 3: "C", 4: "C", 5: "C",
            6: "C", 7: "O", 8: "O", 9: "O",
            10: "C", 11: "O", 12: "C", 13: "O", 14: "C", 15: "O", 16: "C",
            17: "H", 18: "H", 19: "H", 20: "H", 21: "H", 22: "H",
        }
        reactant_coords = {
            0: (-2.55, 1.05, 0.05), 1: (-1.28, 1.78, -0.08),
            2: (0.02, 1.08, 0.06), 3: (0.04, -0.38, -0.05),
            4: (-1.22, -1.12, 0.08), 5: (-2.52, -0.42, -0.06),
            6: (-3.86, 1.72, 0.22), 7: (-4.96, 1.05, 0.60),
            8: (-3.88, 3.02, -0.08), 9: (-1.28, 3.08, 0.18),
            10: (2.15, 3.22, 0.85), 11: (2.34, 4.42, 1.20),
            12: (2.96, 2.26, 1.52), 13: (0.98, 2.96, 0.62),
            14: (0.18, 3.88, -0.28), 15: (0.62, 5.04, -0.54),
            16: (-1.20, 3.54, -0.72),
            17: (0.92, 1.66, 0.16), 18: (0.98, -0.94, -0.10),
            19: (-1.20, -2.20, 0.14), 20: (-3.42, -0.98, -0.14),
            21: (3.95, 2.60, 1.78), 22: (-1.92, 3.92, -1.04),
        }
        ts_coords = dict(reactant_coords)
        ts_coords.update({
            9: (-1.02, 2.78, 0.22),
            10: (0.74, 2.88, 0.52), 11: (0.96, 4.10, 0.92),
            12: (1.34, 1.86, 1.16), 13: (0.12, 3.52, -0.10),
            14: (-0.84, 4.46, -0.70), 15: (-0.40, 5.62, -1.00),
            16: (-2.14, 4.02, -1.10), 21: (2.30, 2.18, 1.48),
            22: (-2.92, 4.22, -1.40),
        })
        product_coords = dict(reactant_coords)
        product_coords.update({
            9: (-1.18, 2.86, 0.16),
            10: (0.16, 2.92, 0.30), 11: (0.42, 4.10, 0.64),
            12: (0.98, 1.86, 0.92), 13: (1.98, 3.96, -0.72),
            14: (3.04, 4.84, -1.18), 15: (2.70, 6.04, -1.48),
            16: (4.38, 4.32, -1.54), 21: (1.88, 2.20, 1.16),
            22: (5.08, 4.76, -1.90),
        })
        fixed_bonds = {
            (0, 1): 1.5, (1, 2): 1.5, (2, 3): 1.5, (3, 4): 1.5,
            (4, 5): 1.5, (0, 5): 1.5, (0, 6): 1.0, (6, 7): 2.0,
            (6, 8): 1.0, (1, 9): 1.0, (10, 11): 2.0, (10, 12): 1.0,
            (13, 14): 1.0, (14, 15): 2.0, (14, 16): 1.0,
            (2, 17): 1.0, (3, 18): 1.0, (4, 19): 1.0, (5, 20): 1.0,
            (12, 21): 1.0, (16, 22): 1.0,
        }

        form_start = max(6, int(n_frames * 0.26))
        form_end = max(form_start + 6, int(n_frames * 0.64))
        break_start = max(form_start + 2, int(n_frames * 0.34))
        break_end = max(break_start + 6, int(n_frames * 0.76))
        bond_changes = [
            BondChange(form_start, form_end, 9, 10, "form"),
            BondChange(break_start, break_end, 10, 13, "break"),
            BondChange(form_start, break_end, 10, 11, "weaken"),
        ]
        charge_labels = [
            ChargeLabel(9, "delta-", 0, form_end),
            ChargeLabel(10, "delta+", 0, break_end),
            ChargeLabel(13, "leaving O", break_start, n_frames),
        ]
        arrows = [
            ArrowAnnotation(9, 10, frame_start=0, frame_end=form_end, style="dashed", color="green"),
            ArrowAnnotation(10, 13, frame_start=break_start, frame_end=break_end, style="dotted", color="yellow"),
        ]

        frames: List[Dict[int, Tuple[float, float, float]]] = []
        bonds_per_frame: List[Dict[Tuple[int, int], float]] = []
        bond_styles: List[Dict[Tuple[int, int], str]] = []
        energies: List[float] = []
        labels: List[str] = []

        def _seg(fi: int, start: int, end: int) -> float:
            return max(0.0, min(1.0, (fi - start) / max(end - start, 1)))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            approach = _ease_in_out(min(t / 0.62, 1.0))
            leave = _ease_in_out(_seg(fi, break_start, n_frames - 1))
            frame = {}
            for idx in symbols:
                if idx in {10, 11, 12, 13, 14, 15, 16, 21, 22}:
                    mid = _lerp_coords(reactant_coords[idx], ts_coords[idx], approach, smooth=False)
                    coord = _lerp_coords(mid, product_coords[idx], leave, smooth=False)
                else:
                    coord = _lerp_coords(reactant_coords[idx], product_coords[idx], min(t * 0.25, 1.0), smooth=False)
                frame[idx] = coord

            form_order = _ease_in_out(_seg(fi, form_start, form_end))
            break_order = 1.0 - _ease_in_out(_seg(fi, break_start, break_end))
            carbonyl_order = 2.0 - 0.45 * math.sin(math.pi * _seg(fi, form_start, break_end))
            bonds = dict(fixed_bonds)
            bonds[(10, 11)] = max(1.35, carbonyl_order)
            if form_order > 0.05:
                bonds[(9, 10)] = max(0.08, form_order)
            if break_order > 0.05:
                bonds[(10, 13)] = max(0.08, break_order)

            styles: Dict[Tuple[int, int], str] = {}
            if 0.05 < form_order < 0.96:
                styles[(9, 10)] = "dashed"
            if 0.05 < break_order < 0.96:
                styles[(10, 13)] = "dotted"
            if form_start <= fi <= break_end:
                styles[(10, 11)] = "dotted"

            frames.append(frame)
            bonds_per_frame.append({(min(i, j), max(i, j)): bo for (i, j), bo in bonds.items()})
            bond_styles.append({(min(i, j), max(i, j)): style for (i, j), style in styles.items()})
            energies.append(_gaussian_energy(t, barrier_kcal, sigma=0.18))
            labels.append("reactant" if fi < form_start else "transition_state" if fi < break_end else "product")

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels,
            n_frames=n_frames,
            charge_labels=charge_labels,
            arrows=arrows,
            bond_styles=bond_styles,
        )

    def generate_chain_growth_polymerization_animation(
        self,
        monomer_smiles: str,
        n_frames: int = 60,
        barrier_kcal: float = 12.0,
    ) -> Optional[ReactionTrajectory]:
        """Vinyl chain-growth polymerization using the shared 3D reaction viewer.

        The generic MCS interpolator is a poor fit for polymerization because the
        product is not a single small-molecule endpoint. This trajectory models the
        teachable event: a growing radical chain end approaches a vinyl monomer,
        the C=C pi bond weakens, a new C-C sigma bond forms, and the radical moves
        to the new chain end.
        """
        if not isinstance(n_frames, int) or n_frames < 20:
            n_frames = 60
        if not isinstance(monomer_smiles, str) or not monomer_smiles.strip():
            logger.warning("chain_growth: invalid monomer_smiles type/value: %r", monomer_smiles)
            return None

        has_substituent = False
        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(monomer_smiles)
            if mol is None:
                logger.warning("[Rule L] chain_growth MolFromSmiles failed: %r", monomer_smiles)
                return None
            vinyl = Chem.MolFromSmarts("[C]=[C]")
            if vinyl is None or not mol.HasSubstructMatch(vinyl):
                logger.warning("chain_growth: vinyl C=C motif not found: %r", monomer_smiles)
                return None
            match = mol.GetSubstructMatch(vinyl)
            vinyl_atoms = set(match)
            has_substituent = any(
                nbr.GetIdx() not in vinyl_atoms and nbr.GetAtomicNum() > 1
                for atom_idx in vinyl_atoms
                for nbr in mol.GetAtomWithIdx(atom_idx).GetNeighbors()
            )

        # Atom model:
        # 0-1-2 = existing chain with radical end at 2.
        # 3=vinyl alpha carbon, 4=vinyl beta carbon, 5=visible substituent/R group.
        # 6-12 = hydrogens for orientation and scale.
        symbols = {
            0: "C", 1: "C", 2: "C", 3: "C", 4: "C", 5: "C",
            6: "H", 7: "H", 8: "H", 9: "H", 10: "H", 11: "H", 12: "H",
        }
        if not has_substituent:
            symbols[5] = "H"

        reactant_coords = {
            0: (-4.15, -0.10, 0.00), 1: (-2.72, 0.10, 0.05),
            2: (-1.28, -0.05, -0.05),
            3: (2.65, 0.38, 0.12), 4: (4.00, 0.38, -0.12),
            5: (5.05, 1.18, 0.15),
            6: (-4.80, 0.78, 0.12), 7: (-4.76, -0.98, -0.12),
            8: (-2.70, 1.05, 0.55), 9: (-2.68, -0.90, -0.50),
            10: (-1.16, -1.02, 0.10), 11: (2.45, 1.30, 0.30),
            12: (4.20, -0.58, -0.35),
        }
        ts_coords = {
            0: (-4.00, -0.05, 0.00), 1: (-2.62, 0.05, 0.04),
            2: (-1.18, 0.00, -0.03),
            3: (0.38, 0.12, 0.02), 4: (1.76, 0.18, -0.08),
            5: (2.90, 0.92, 0.15),
            6: (-4.62, 0.82, 0.12), 7: (-4.68, -0.92, -0.12),
            8: (-2.58, 1.00, 0.52), 9: (-2.62, -0.88, -0.48),
            10: (-1.10, -1.00, 0.08), 11: (0.24, 1.05, 0.24),
            12: (1.96, -0.76, -0.30),
        }
        product_coords = {
            0: (-4.08, -0.02, 0.00), 1: (-2.68, 0.04, 0.04),
            2: (-1.28, -0.02, -0.03), 3: (0.12, 0.04, 0.02),
            4: (1.54, 0.02, -0.08), 5: (2.58, 0.88, 0.15),
            6: (-4.70, 0.86, 0.12), 7: (-4.72, -0.90, -0.12),
            8: (-2.68, 0.98, 0.52), 9: (-2.68, -0.90, -0.48),
            10: (-1.18, -0.98, 0.08), 11: (0.00, 0.98, 0.24),
            12: (1.72, -0.90, -0.30),
        }
        reactant_bonds = {
            (0, 1): 1.0, (1, 2): 1.0, (3, 4): 2.0,
            (4, 5): 1.0, (0, 6): 1.0, (0, 7): 1.0,
            (1, 8): 1.0, (1, 9): 1.0, (2, 10): 1.0,
            (3, 11): 1.0, (4, 12): 1.0,
        }
        ts_bonds = dict(reactant_bonds)
        ts_bonds[(2, 3)] = 0.55
        ts_bonds[(3, 4)] = 1.35
        product_bonds = dict(reactant_bonds)
        product_bonds[(2, 3)] = 1.0
        product_bonds[(3, 4)] = 1.0

        p1_end = max(6, int(n_frames * 0.34))
        p2_end = max(p1_end + 6, int(n_frames * 0.72))
        bond_changes = [
            BondChange(p1_end, p2_end, 2, 3, "form"),
            BondChange(p1_end, p2_end, 3, 4, "weaken"),
        ]
        charge_labels = [
            ChargeLabel(2, "radical", 0, p2_end),
            ChargeLabel(4, "radical", p2_end, n_frames),
        ]
        if has_substituent:
            charge_labels.append(ChargeLabel(5, "R", 0, n_frames))
        arrows = [
            ArrowAnnotation(
                from_atom=2, to_atom=3,
                frame_start=0, frame_end=p2_end,
                style="dashed", color="green",
            ),
            ArrowAnnotation(
                from_atom=-1, to_atom=4,
                from_pos=(3.28, 0.54, 0.05),
                frame_start=p1_end, frame_end=p2_end,
                style="dotted", color="yellow",
            ),
        ]

        frames: List[Dict[int, Tuple[float, float, float]]] = []
        bonds_per_frame: List[Dict[Tuple[int, int], float]] = []
        bond_styles: List[Dict[Tuple[int, int], str]] = []
        energies: List[float] = []
        labels: List[str] = []

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            if fi < p1_end:
                local_t = fi / max(p1_end - 1, 1)
                s = _ease_in_out(local_t)
                frame = {
                    idx: _lerp_coords(reactant_coords[idx], ts_coords[idx], 0.72 * s, smooth=False)
                    for idx in symbols
                }
                bonds = dict(reactant_bonds)
                styles = {(3, 4): "solid"}
                label = "reactant"
            elif fi < p2_end:
                local_t = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                s = _ease_in_out(local_t)
                frame = {
                    idx: _lerp_coords(ts_coords[idx], product_coords[idx], 0.45 * s, smooth=False)
                    for idx in symbols
                }
                bonds = dict(ts_bonds)
                bonds[(2, 3)] = 0.30 + 0.70 * s
                bonds[(3, 4)] = 1.35 - 0.35 * s
                styles = {(2, 3): "dashed", (3, 4): "dotted"}
                label = "transition_state"
            else:
                local_t = (fi - p2_end) / max(n_frames - p2_end - 1, 1)
                s = _ease_in_out(local_t)
                frame = {
                    idx: _lerp_coords(ts_coords[idx], product_coords[idx], s, smooth=False)
                    for idx in symbols
                }
                bonds = dict(product_bonds)
                styles = {}
                label = "product"

            frames.append(frame)
            bonds_per_frame.append({(min(i, j), max(i, j)): bo for (i, j), bo in bonds.items()})
            bond_styles.append({(min(i, j), max(i, j)): style for (i, j), style in styles.items()})
            energies.append(_gaussian_energy(t, barrier_kcal, sigma=0.22))
            labels.append(label)

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels,
            n_frames=n_frames,
            charge_labels=charge_labels,
            arrows=arrows,
            bond_styles=bond_styles,
        )

    def generate_bromination_addition_animation(
        self,
        n_frames: int = 40,
        barrier_kcal: float = 18.0,
    ) -> Optional[ReactionTrajectory]:
        """Ethene + Br2 -> 1,2-dibromoethane valid-collision trajectory."""
        if not isinstance(n_frames, int) or n_frames < 12:
            n_frames = 40

        symbols = {
            0: "C", 1: "C",
            2: "H", 3: "H", 4: "H", 5: "H",
            6: "Br", 7: "Br",
        }
        reactant_coords = {
            0: (-0.72, 0.0, 0.0), 1: (0.72, 0.0, 0.0),
            2: (-1.30, 0.92, 0.0), 3: (-1.30, -0.92, 0.0),
            4: (1.30, 0.92, 0.0), 5: (1.30, -0.92, 0.0),
            6: (0.0, 4.35, 1.75), 7: (0.0, 6.45, 1.95),
        }
        ts_coords = {
            0: (-0.78, -0.10, -0.08), 1: (0.78, -0.10, -0.08),
            2: (-1.42, 0.84, -0.12), 3: (-1.30, -1.02, -0.04),
            4: (1.42, 0.84, -0.12), 5: (1.30, -1.02, -0.04),
            6: (0.0, 1.12, 0.92), 7: (0.0, 3.12, 1.55),
        }
        product_coords = {
            0: (-0.78, 0.0, 0.0), 1: (0.78, 0.0, 0.0),
            2: (-1.28, 0.93, 0.18), 3: (-1.30, -0.86, -0.58),
            4: (1.30, 0.86, 0.58), 5: (1.28, -0.93, -0.18),
            6: (-1.62, 1.25, 0.82), 7: (1.62, -1.25, -0.82),
        }

        reactant_bonds = {
            (0, 1): 2.0, (0, 2): 1.0, (0, 3): 1.0,
            (1, 4): 1.0, (1, 5): 1.0, (6, 7): 1.0,
        }
        product_bonds = {
            (0, 1): 1.0, (0, 2): 1.0, (0, 3): 1.0,
            (1, 4): 1.0, (1, 5): 1.0, (0, 6): 1.0, (1, 7): 1.0,
        }
        ts_bonds = {
            (0, 1): 1.35, (0, 2): 1.0, (0, 3): 1.0,
            (1, 4): 1.0, (1, 5): 1.0,
            (0, 6): 0.55, (1, 6): 0.55, (6, 7): 0.35,
        }

        p1_end = max(3, int(n_frames * 0.30))
        p2_end = max(p1_end + 3, int(n_frames * 0.68))
        bond_changes = [
            BondChange(p1_end, p2_end, 0, 1, "weaken"),
            BondChange(p1_end, p2_end, 6, 7, "break"),
            BondChange(p1_end, p2_end, 0, 6, "form"),
            BondChange(p1_end, p2_end, 1, 6, "weaken"),
            BondChange(p1_end, p2_end, 1, 7, "form"),
        ]
        charge_labels = [
            ChargeLabel(6, "d+", 0, p2_end),
            ChargeLabel(7, "d-", 0, n_frames),
            ChargeLabel(0, "d+", p1_end, p2_end),
            ChargeLabel(1, "d+", p1_end, p2_end),
        ]
        arrows = [
            ArrowAnnotation(
                from_atom=-1, to_atom=6,
                from_pos=(0.0, 0.12, 0.25),
                frame_start=0, frame_end=p1_end,
                style="dashed", color="green",
            ),
            ArrowAnnotation(
                from_atom=-1, to_atom=7,
                from_pos=(0.0, 4.75, 1.82),
                frame_start=p1_end, frame_end=p2_end,
                style="dashed", color="red",
            ),
            ArrowAnnotation(
                from_atom=7, to_atom=1,
                frame_start=max(0, p2_end - 4), frame_end=n_frames,
                style="dashed", color="green",
            ),
        ]

        frames: List[Dict[int, Tuple[float, float, float]]] = []
        bonds_per_frame: List[Dict[Tuple[int, int], float]] = []
        bond_styles: List[Dict[Tuple[int, int], str]] = []
        energies: List[float] = []
        labels: List[str] = []

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            if fi < p1_end:
                local_t = fi / max(p1_end - 1, 1)
                s = _ease_in_out(local_t)
                frame = {
                    idx: _lerp_coords(reactant_coords[idx], ts_coords[idx], s, smooth=False)
                    for idx in symbols
                }
                bonds = dict(reactant_bonds)
                styles = {(6, 7): "solid"}
                label = "reactant"
            elif fi < p2_end:
                local_t = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                s = _ease_in_out(local_t)
                frame = {
                    idx: _lerp_coords(ts_coords[idx], product_coords[idx], s * 0.35, smooth=False)
                    for idx in symbols
                }
                cbr = 0.30 + 0.70 * s
                brbr = max(0.05, 0.35 * (1.0 - s))
                ccd = 1.35 - 0.35 * s
                bonds = dict(ts_bonds)
                bonds[(0, 1)] = ccd
                bonds[(0, 6)] = max(0.45, cbr)
                bonds[(1, 6)] = max(0.10, 0.55 * (1.0 - s))
                bonds[(6, 7)] = brbr
                bonds[(1, 7)] = max(0.08, 0.65 * s)
                styles = {
                    (0, 6): "dashed", (1, 6): "dotted",
                    (6, 7): "dotted", (1, 7): "dashed",
                }
                label = "transition_state"
            else:
                local_t = (fi - p2_end) / max(n_frames - p2_end - 1, 1)
                s = _ease_in_out(local_t)
                frame = {
                    idx: _lerp_coords(ts_coords[idx], product_coords[idx], s, smooth=False)
                    for idx in symbols
                }
                bonds = dict(product_bonds)
                styles = {}
                label = "product"

            frames.append(frame)
            bonds_per_frame.append({(min(i, j), max(i, j)): bo for (i, j), bo in bonds.items()})
            bond_styles.append({(min(i, j), max(i, j)): style for (i, j), style in styles.items()})
            energies.append(_gaussian_energy(t, barrier_kcal, sigma=0.18))
            labels.append(label)

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels,
            n_frames=n_frames,
            charge_labels=charge_labels,
            arrows=arrows,
            bond_styles=bond_styles,
        )

    def generate_sn2_animation(
        self,
        substrate_smi: str,
        nucleophile_smi: str,
        leaving_group: str = "Br",
        n_frames: int = 40,
        barrier_kcal: float = 20.0,
    ) -> Optional[ReactionTrajectory]:
        """SN2 배면공격 + Walden 반전 애니메이션.

        1. 기질 + 친핵체 3D 좌표 생성
        2. 친핵체를 이탈기 반대편 배치 (180도)
        3. 프레임별: 친핵체 접근 -> 오탄소 전이상태 -> 반전 + 이탈기 이탈
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(substrate_smi, str) or not substrate_smi.strip():
            logger.warning(f"generate_sn2_animation: substrate_smi 타입/값 불일치 ({type(substrate_smi).__name__})")
            return None
        if not isinstance(nucleophile_smi, str) or not nucleophile_smi.strip():
            logger.warning(f"generate_sn2_animation: nucleophile_smi 타입/값 불일치 ({type(nucleophile_smi).__name__})")
            return None
        if not isinstance(leaving_group, str):
            logger.warning(f"generate_sn2_animation: leaving_group 타입 불일치 ({type(leaving_group).__name__})")
            return None
        try:
            return self._generate_sn2_impl(
                substrate_smi, nucleophile_smi, leaving_group, n_frames, barrier_kcal
            )
        except Exception as e:
            logger.error(f"SN2 animation 실패: {e}", exc_info=True)
            return None

    def _generate_sn2_impl(
        self,
        substrate_smi: str,
        nucleophile_smi: str,
        leaving_group: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        """SN2 4-phase animation:
        Phase 1 (0-25%): Nucleophile approaches from backside
        Phase 2 (25-50%): Transition state - dotted bonds, partial charges
        Phase 3 (50-75%): Bond breaks, leaving group departs with charge
        Phase 4 (75-100%): Walden inversion completes, new bond formed
        """
        # 기질 3D
        mol_sub = Chem.MolFromSmiles(substrate_smi)
        if mol_sub is None:
            return None
        mol_sub3d = _embed_3d(Chem.RWMol(mol_sub))
        if mol_sub3d is None:
            return None

        coords_sub = _get_coords_dict(mol_sub3d)
        symbols_sub = _get_symbols_dict(mol_sub3d)
        bonds_sub = _get_bonds_dict(mol_sub3d)

        # 이탈기 원자 & 중심 탄소 찾기
        lg_idx = None
        c_center = None
        for atom in mol_sub3d.GetAtoms():
            if atom.GetSymbol() == leaving_group:
                lg_idx = atom.GetIdx()
                for nbr in atom.GetNeighbors():
                    if nbr.GetSymbol() == "C":
                        c_center = nbr.GetIdx()
                        break
                break

        if lg_idx is None or c_center is None:
            logger.warning(f"SN2: 이탈기({leaving_group}) 또는 중심 탄소를 찾을 수 없음")
            return self.generate_frames(substrate_smi, nucleophile_smi, n_frames, barrier_kcal)

        # 친핵체 3D (단일 원자 또는 소분자)
        mol_nuc = Chem.MolFromSmiles(nucleophile_smi)
        if mol_nuc is None:
            return None
        mol_nuc3d = _embed_3d(Chem.RWMol(mol_nuc))
        if mol_nuc3d is None:
            return None

        coords_nuc = _get_coords_dict(mol_nuc3d)
        symbols_nuc = _get_symbols_dict(mol_nuc3d)

        # 친핵 원자 = 친핵체의 첫 번째 비-수소 원자
        nuc_atom_idx = 0
        for a in mol_nuc3d.GetAtoms():
            if a.GetSymbol() != "H":
                nuc_atom_idx = a.GetIdx()
                break

        # 배면공격 방향 계산 (C-LG 방향의 반대)
        c_pos = np.array(coords_sub[c_center])
        lg_pos = np.array(coords_sub[lg_idx])
        attack_dir = _norm(c_pos - lg_pos)  # C -> 반대쪽 (배면)
        lg_dir = _norm(lg_pos - c_pos)       # C -> LG 방향 (이탈 방향)

        # 거리 매개변수
        nuc_start_dist = 6.0    # Phase 1 시작 거리 (A)
        nuc_ts_dist = 2.2       # Phase 2 전이상태 거리 (A)
        nuc_bond_dist = 1.5     # Phase 4 최종 결합 거리 (A)
        lg_bond_len = np.linalg.norm(lg_pos - c_pos)  # 원래 C-LG 결합 길이
        lg_ts_stretch = 2.2     # Phase 2 전이상태 C-LG 거리
        lg_depart_dist = 6.0    # Phase 3-4 이탈 거리

        # 통합 원자 인덱스: 기질 유지, 친핵체는 오프셋
        nuc_offset = mol_sub3d.GetNumAtoms()
        all_symbols = dict(symbols_sub)
        for nidx, sym in symbols_nuc.items():
            all_symbols[nidx + nuc_offset] = sym

        # 프레임 경계
        p1_end = int(n_frames * 0.25)   # Phase 1 끝
        p2_end = int(n_frames * 0.50)   # Phase 2 끝
        p3_end = int(n_frames * 0.75)   # Phase 3 끝

        # 결합 변화 기록 (Phase 2-3에 걸쳐 발생)
        bond_changes = [
            BondChange(
                frame_start=p1_end,
                frame_end=p3_end,
                atom_i=c_center,
                atom_j=lg_idx,
                change_type="break",
            ),
            BondChange(
                frame_start=p1_end,
                frame_end=p3_end,
                atom_i=c_center,
                atom_j=nuc_atom_idx + nuc_offset,
                change_type="form",
            ),
        ]

        # 전하 라벨 정의
        nuc_unified = nuc_atom_idx + nuc_offset
        charge_labels = [
            # Phase 2: 부분 전하 (전이상태)
            ChargeLabel(c_center, "δ+", p1_end, p3_end),
            ChargeLabel(nuc_unified, "δ-", p1_end, p3_end),
            ChargeLabel(lg_idx, "δ-", p1_end, p3_end),
            # Phase 3-4: 이탈기 완전 음전하
            ChargeLabel(lg_idx, "-", p3_end, n_frames),
        ]

        # 접근 궤적 화살표 (Phase 1)
        arrows = [
            ArrowAnnotation(
                from_atom=nuc_unified, to_atom=c_center,
                frame_start=0, frame_end=p1_end,
                style="dashed", color="green",
            ),
        ]

        frames = []
        bonds_per_frame = []
        bond_styles_per_frame = []
        energies = []
        labels_list = []

        clg_bond_key = (min(c_center, lg_idx), max(c_center, lg_idx))
        nuc_bond_key = (min(c_center, nuc_unified), max(c_center, nuc_unified))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)

            frame_coords = {}
            frame_bonds = {}
            frame_bstyles = {}

            # ---- Phase-dependent parameters ----
            if fi < p1_end:
                # Phase 1: Nucleophile approach (6A -> 2.2A), no bond change
                local_t = fi / max(p1_end - 1, 1)
                s = _ease_in_out(local_t)
                nuc_dist = nuc_start_dist + (nuc_ts_dist - nuc_start_dist) * s
                lg_offset = 0.0
                inversion_frac = 0.0
                clg_bo = 1.0
                cnuc_bo = 0.0
                clg_style = "solid"
                cnuc_style = "solid"
                phase_label = "reactant"
            elif fi < p2_end:
                # Phase 2: Transition state - both bonds partial
                local_t = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                s = _ease_in_out(local_t)
                nuc_dist = nuc_ts_dist
                lg_stretch = lg_bond_len + (lg_ts_stretch - lg_bond_len) * s
                lg_offset = lg_stretch - lg_bond_len
                inversion_frac = s * 0.5  # 반전 시작 (50%까지)
                clg_bo = 0.5              # 부분 결합 (dotted)
                cnuc_bo = 0.5             # 부분 결합 (dotted)
                clg_style = "dotted"      # 전이상태: 끊어지는 결합 점선
                cnuc_style = "dotted"     # 전이상태: 형성되는 결합 점선
                phase_label = "transition_state"
            elif fi < p3_end:
                # Phase 3: Bond breaks, LG departs
                local_t = (fi - p2_end) / max(p3_end - p2_end - 1, 1)
                s = _ease_in_out(local_t)
                nuc_dist = nuc_ts_dist + (nuc_bond_dist - nuc_ts_dist) * s
                lg_offset = (lg_ts_stretch - lg_bond_len) + s * (lg_depart_dist - lg_ts_stretch)
                inversion_frac = 0.5 + s * 0.4  # 반전 진행 (50->90%)
                clg_bo = 0.5 * (1.0 - s)     # 결합 소멸
                cnuc_bo = 0.5 + 0.5 * s       # 결합 형성
                clg_style = "dotted" if clg_bo > 0.05 else "solid"
                cnuc_style = "dashed"         # 형성 중
                phase_label = "transition_state" if local_t < 0.5 else "product"
            else:
                # Phase 4: Walden inversion complete, new bond formed
                local_t = (fi - p3_end) / max(n_frames - 1 - p3_end, 1)
                s = _ease_in_out(local_t)
                nuc_dist = nuc_bond_dist
                lg_offset = lg_depart_dist + s * 2.0  # 더 멀리 이탈
                inversion_frac = 0.9 + s * 0.1  # 반전 완료 (90->100%)
                clg_bo = 0.0
                cnuc_bo = 1.0
                clg_style = "solid"
                cnuc_style = "solid"
                phase_label = "product"

            # ---- 친핵체 위치 ----
            nuc_center = c_pos + attack_dir * nuc_dist
            nuc_ref = np.array(coords_nuc[nuc_atom_idx])
            nuc_shift = nuc_center - nuc_ref
            for nidx, nc in coords_nuc.items():
                shifted = np.array(nc) + nuc_shift
                frame_coords[nidx + nuc_offset] = tuple(shifted)

            # ---- 기질 원자 위치 ----
            for aidx, acoords in coords_sub.items():
                ac = np.array(acoords)
                if aidx == lg_idx:
                    # 이탈기: 원래 위치 + 이탈 방향 오프셋
                    new_pos = lg_pos + lg_dir * lg_offset
                    frame_coords[aidx] = tuple(new_pos)
                elif aidx == c_center:
                    frame_coords[aidx] = tuple(c_pos)
                else:
                    # 치환기: Walden 반전 (공격축 성분 반전)
                    vec = ac - c_pos
                    proj = np.dot(vec, attack_dir) * attack_dir
                    perp = vec - proj
                    inverted_vec = -proj + perp
                    inv_s = _ease_in_out(inversion_frac)
                    final_vec = vec * (1 - inv_s) + inverted_vec * inv_s
                    frame_coords[aidx] = tuple(c_pos + final_vec)

            # ---- 결합 차수 ----
            for bkey, bo in bonds_sub.items():
                bi, bj = bkey
                if bkey == clg_bond_key or (bi == lg_idx and bj == c_center) or (bi == c_center and bj == lg_idx):
                    if clg_bo > 0.05:
                        frame_bonds[clg_bond_key] = clg_bo
                        frame_bstyles[clg_bond_key] = clg_style
                else:
                    frame_bonds[bkey] = bo
                    frame_bstyles[bkey] = "solid"

            # C-Nuc 결합
            if cnuc_bo > 0.05:
                frame_bonds[nuc_bond_key] = cnuc_bo
                frame_bstyles[nuc_bond_key] = cnuc_style

            # ---- 에너지 (비대칭 프로파일: TS at ~40%) ----
            energy = barrier_kcal * math.sin(math.pi * t) if t <= 1.0 else 0.0

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            bond_styles_per_frame.append(frame_bstyles)
            energies.append(energy)
            labels_list.append(phase_label)

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels_list,
            n_frames=n_frames,
            charge_labels=charge_labels,
            arrows=arrows,
            bond_styles=bond_styles_per_frame,
        )

    # --------------------------------------------------------
    # 4-3. 양성자 전달
    # --------------------------------------------------------
    def generate_proton_transfer(
        self,
        acid_smi: str,
        base_smi: str,
        n_frames: int = 40,
        barrier_kcal: float = 8.0,
    ) -> Optional[ReactionTrajectory]:
        """산-염기 양성자 전달 애니메이션.

        1. 산의 해리성 H 식별
        2. 염기의 수용 원자(N, O 등) 식별
        3. H가 산에서 떨어져 염기로 이동
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(acid_smi, str) or not acid_smi.strip():
            logger.warning(f"generate_proton_transfer: acid_smi 타입/값 불일치 ({type(acid_smi).__name__})")
            return None
        if not isinstance(base_smi, str) or not base_smi.strip():
            logger.warning(f"generate_proton_transfer: base_smi 타입/값 불일치 ({type(base_smi).__name__})")
            return None
        try:
            return self._generate_proton_transfer_impl(
                acid_smi, base_smi, n_frames, barrier_kcal
            )
        except Exception as e:
            logger.error(f"양성자 전달 animation 실패: {e}", exc_info=True)
            return None

    def _generate_proton_transfer_impl(
        self,
        acid_smi: str,
        base_smi: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        """Proton transfer with 4 phases:
        Phase 1 (0-20%): Separated molecules, base approaches with lone pair direction
        Phase 2 (20-45%): H-bond transition state (dotted bonds to both donor and acceptor)
        Phase 3 (45-70%): Proton transfers, donor-H breaks, acceptor-H forms
        Phase 4 (70-100%): Products separate with charge labels
        """
        mol_acid = Chem.MolFromSmiles(acid_smi)
        mol_base = Chem.MolFromSmiles(base_smi)
        if mol_acid is None or mol_base is None:
            return None

        mol_acid3d = _embed_3d(Chem.RWMol(mol_acid))
        mol_base3d = _embed_3d(Chem.RWMol(mol_base))
        if mol_acid3d is None or mol_base3d is None:
            return None

        coords_acid = _get_coords_dict(mol_acid3d)
        symbols_acid = _get_symbols_dict(mol_acid3d)
        bonds_acid = _get_bonds_dict(mol_acid3d)

        coords_base = _get_coords_dict(mol_base3d)
        symbols_base = _get_symbols_dict(mol_base3d)

        # 해리성 수소 찾기 (O-H, N-H, S-H)
        h_idx = None
        donor_idx = None
        for atom in mol_acid3d.GetAtoms():
            if atom.GetSymbol() in ("O", "N", "S"):
                for nbr in atom.GetNeighbors():
                    if nbr.GetSymbol() == "H":
                        h_idx = nbr.GetIdx()
                        donor_idx = atom.GetIdx()
                        break
            if h_idx is not None:
                break

        if h_idx is None:
            logger.warning("양성자 전달: 해리성 H를 찾을 수 없음")
            return self.generate_frames(acid_smi, base_smi, n_frames, barrier_kcal)

        # 염기 수용 원자 (N, O 우선)
        acceptor_idx = None
        for atom in mol_base3d.GetAtoms():
            if atom.GetSymbol() in ("N", "O", "S"):
                acceptor_idx = atom.GetIdx()
                break
        if acceptor_idx is None:
            acceptor_idx = 0

        # 통합 인덱스
        base_offset = mol_acid3d.GetNumAtoms()
        all_symbols = dict(symbols_acid)
        for bidx, sym in symbols_base.items():
            all_symbols[bidx + base_offset] = sym

        acceptor_unified = acceptor_idx + base_offset

        # 염기 배치: 산으로부터 최소 5A 분리 (이전: 3A -> 겹침 문제)
        h_pos = np.array(coords_acid[h_idx])
        donor_pos = np.array(coords_acid[donor_idx])
        approach_dir = _norm(h_pos - donor_pos)  # donor -> H 방향 (lone pair 접근 방향)

        # 초기 염기 위치: H로부터 5A 떨어진 곳
        initial_separation = 5.0   # 초기 분리 거리 (A)
        hbond_dist = 2.5           # H-bond TS 거리 (donor-H...acceptor)
        final_separation = 1.0     # 최종 acceptor-H 결합 거리

        base_acceptor_pos = np.array(coords_base[acceptor_idx])
        initial_target = h_pos + approach_dir * initial_separation
        base_shift_initial = initial_target - base_acceptor_pos

        coords_base_initial = {}
        for bidx, bc in coords_base.items():
            shifted = np.array(bc) + base_shift_initial
            coords_base_initial[bidx] = tuple(shifted)

        # 프레임 경계
        p1_end = int(n_frames * 0.20)
        p2_end = int(n_frames * 0.45)
        p3_end = int(n_frames * 0.70)

        bond_changes = [
            BondChange(p1_end, p3_end, donor_idx, h_idx, "break"),
            BondChange(p1_end, p3_end, h_idx, acceptor_unified, "form"),
        ]

        # 전하 라벨
        charge_labels = [
            # Phase 2: H-bond TS - 부분 전하
            ChargeLabel(donor_idx, "δ-", p1_end, p3_end),
            ChargeLabel(h_idx, "δ+", p1_end, p3_end),
            ChargeLabel(acceptor_unified, "δ-", p1_end, p3_end),
            # Phase 4: 최종 전하 (conjugate acid/base)
            ChargeLabel(donor_idx, "-", p3_end, n_frames),
            ChargeLabel(acceptor_unified, "+", p3_end, n_frames),
        ]

        # 접근 화살표 (lone pair direction)
        arrows = [
            ArrowAnnotation(
                from_atom=acceptor_unified, to_atom=h_idx,
                frame_start=0, frame_end=p2_end,
                style="dashed", color="green",
            ),
        ]

        frames = []
        bonds_per_frame = []
        bond_styles_per_frame = []
        energies = []
        labels_list = []

        dh_bond_key = (min(donor_idx, h_idx), max(donor_idx, h_idx))
        ah_bond_key = (min(h_idx, acceptor_unified), max(h_idx, acceptor_unified))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            frame_coords = {}
            frame_bonds = {}
            frame_bstyles = {}

            if fi < p1_end:
                # Phase 1: Base approaches from 5A to ~3A
                local_t = fi / max(p1_end - 1, 1)
                s = _ease_in_out(local_t)
                base_approach_frac = s * 0.4  # 40% of the way closer
                dh_bo = 1.0
                ah_bo = 0.0
                dh_style = "solid"
                ah_style = "solid"
                phase_label = "reactant"
            elif fi < p2_end:
                # Phase 2: H-bond transition state
                local_t = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                s = _ease_in_out(local_t)
                base_approach_frac = 0.4 + s * 0.3  # closer to H-bond distance
                dh_bo = 1.0 - 0.5 * s      # weakening
                ah_bo = 0.3 * s              # H-bond forming
                dh_style = "dotted"
                ah_style = "dotted"
                phase_label = "transition_state"
            elif fi < p3_end:
                # Phase 3: Proton transfer
                local_t = (fi - p2_end) / max(p3_end - p2_end - 1, 1)
                s = _ease_in_out(local_t)
                base_approach_frac = 0.7 + s * 0.15
                dh_bo = 0.5 * (1.0 - s)    # breaking
                ah_bo = 0.3 + 0.7 * s       # forming
                dh_style = "dotted" if dh_bo > 0.05 else "solid"
                ah_style = "dashed"
                phase_label = "transition_state" if local_t < 0.5 else "product"
            else:
                # Phase 4: Products separate
                local_t = (fi - p3_end) / max(n_frames - 1 - p3_end, 1)
                s = _ease_in_out(local_t)
                base_approach_frac = 0.85 - s * 0.2  # slight separation
                dh_bo = 0.0
                ah_bo = 1.0
                dh_style = "solid"
                ah_style = "solid"
                phase_label = "product"

            # ---- 산 원자 위치 ----
            for aidx, ac in coords_acid.items():
                if aidx == h_idx:
                    # H 이동: donor 근처 -> acceptor 근처
                    donor_p = np.array(coords_acid[donor_idx])
                    # H starts at its natural position, ends near acceptor
                    h_start = np.array(coords_acid[h_idx])
                    # Acceptor target position (current frame)
                    accept_target = np.array(coords_base_initial[acceptor_idx]) - approach_dir * initial_separation * base_approach_frac
                    h_end = accept_target - approach_dir * final_separation
                    # Overall proton transfer progress
                    if fi < p1_end:
                        h_frac = 0.0
                    elif fi < p2_end:
                        loc = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                        h_frac = _ease_in_out(loc) * 0.3
                    elif fi < p3_end:
                        loc = (fi - p2_end) / max(p3_end - p2_end - 1, 1)
                        h_frac = 0.3 + _ease_in_out(loc) * 0.7
                    else:
                        h_frac = 1.0
                    h_current = h_start * (1 - h_frac) + h_end * h_frac
                    frame_coords[aidx] = tuple(h_current)
                else:
                    frame_coords[aidx] = ac

            # ---- 염기 원자 위치 (접근) ----
            for bidx, bc in coords_base_initial.items():
                base_pos = np.array(bc) - approach_dir * initial_separation * base_approach_frac
                frame_coords[bidx + base_offset] = tuple(base_pos)

            # ---- 결합 차수 ----
            for bkey, bo in bonds_acid.items():
                if bkey == dh_bond_key or (bkey[0] == h_idx and bkey[1] == donor_idx) or (bkey[0] == donor_idx and bkey[1] == h_idx):
                    if dh_bo > 0.05:
                        frame_bonds[dh_bond_key] = dh_bo
                        frame_bstyles[dh_bond_key] = dh_style
                else:
                    frame_bonds[bkey] = bo
                    frame_bstyles[bkey] = "solid"

            # H-acceptor 결합
            if ah_bo > 0.05:
                frame_bonds[ah_bond_key] = ah_bo
                frame_bstyles[ah_bond_key] = ah_style

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            bond_styles_per_frame.append(frame_bstyles)
            energies.append(_parabolic_energy(t, barrier_kcal))
            labels_list.append(phase_label)

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels_list,
            n_frames=n_frames,
            charge_labels=charge_labels,
            arrows=arrows,
            bond_styles=bond_styles_per_frame,
        )

    # --------------------------------------------------------
    # 4-4. 의자형 뒤집기 (Chair Flip)
    # --------------------------------------------------------
    def generate_chair_flip(
        self,
        smiles: str = "C1CCCCC1",
        n_frames: int = 40,
        barrier_kcal: float = 10.5,
    ) -> Optional[ReactionTrajectory]:
        """사이클로헥산 의자형 뒤집기 애니메이션.

        경로: chair -> half-chair -> boat -> twist-boat -> half-chair -> chair
        축/적도 위치 교환.
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(smiles, str) or not smiles.strip():
            logger.warning(f"generate_chair_flip: smiles 타입/값 불일치 ({type(smiles).__name__})")
            return None
        try:
            return self._generate_chair_flip_impl(smiles, n_frames, barrier_kcal)
        except Exception as e:
            logger.error(f"Chair flip animation 실패: {e}", exc_info=True)
            return None

    def _generate_chair_flip_impl(
        self,
        smiles: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        # 사이클로헥산 의자 좌표 (이상적 기하)
        # 정의자(Chair 1): C1 up, C4 down
        r = 1.53  # C-C bond length (A)
        chair1 = {
            0: (r * math.cos(0),        r * math.sin(0),         0.25),
            1: (r * math.cos(math.pi/3), r * math.sin(math.pi/3), -0.25),
            2: (r * math.cos(2*math.pi/3), r * math.sin(2*math.pi/3), 0.25),
            3: (r * math.cos(math.pi),   r * math.sin(math.pi),   -0.25),
            4: (r * math.cos(4*math.pi/3), r * math.sin(4*math.pi/3), 0.25),
            5: (r * math.cos(5*math.pi/3), r * math.sin(5*math.pi/3), -0.25),
        }
        # 반전 의자(Chair 2): z 뒤집기
        chair2 = {k: (v[0], v[1], -v[2]) for k, v in chair1.items()}
        # 보트 중간체 (boat): C0, C3 동일 높이
        boat = {
            0: (chair1[0][0], chair1[0][1], 0.5),
            1: (chair1[1][0], chair1[1][1], 0.0),
            2: (chair1[2][0], chair1[2][1], 0.0),
            3: (chair1[3][0], chair1[3][1], 0.5),
            4: (chair1[4][0], chair1[4][1], 0.0),
            5: (chair1[5][0], chair1[5][1], 0.0),
        }

        # 수소 추가 (각 탄소에 2H: 축 + 적도)
        symbols = {}
        for i in range(6):
            symbols[i] = "C"
        h_idx = 6
        h_per_carbon = {}
        for ci in range(6):
            ax_idx = h_idx
            eq_idx = h_idx + 1
            symbols[ax_idx] = "H"
            symbols[eq_idx] = "H"
            h_per_carbon[ci] = (ax_idx, eq_idx)
            h_idx += 2

        def _add_hydrogens(ring_coords, is_chair1=True):
            """고리 좌표에 수소 위치 추가."""
            full = dict(ring_coords)
            for ci in range(6):
                cx, cy, cz = ring_coords[ci]
                ax_h, eq_h = h_per_carbon[ci]
                # 축: z 방향 (위/아래)
                z_sign = 1.0 if cz >= 0 else -1.0
                full[ax_h] = (cx, cy, cz + z_sign * 1.09)
                # 적도: 방사 방향 (바깥)
                rad_dir = _norm(np.array([cx, cy, 0]))
                eq_pos = np.array([cx, cy, cz]) + rad_dir * 1.09
                full[eq_h] = tuple(eq_pos)
            return full

        coords_c1 = _add_hydrogens(chair1, True)
        coords_c2 = _add_hydrogens(chair2, False)
        coords_boat = _add_hydrogens(boat)

        # 프레임 생성: chair1 -> boat -> chair2
        frames = []
        bonds_per_frame = []
        energies = []
        labels_list = []

        ring_bonds = {}
        for i in range(6):
            key = (i, (i + 1) % 6)
            ring_bonds[key] = 1.0
        for ci in range(6):
            ax_h, eq_h = h_per_carbon[ci]
            ring_bonds[(ci, ax_h)] = 1.0
            ring_bonds[(ci, eq_h)] = 1.0

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            frame_coords = {}

            if t <= 0.5:
                # chair1 -> boat (t: 0->0.5 -> local_t: 0->1)
                lt = t * 2.0
                for idx in coords_c1:
                    frame_coords[idx] = _lerp_coords(coords_c1[idx], coords_boat[idx], lt)
            else:
                # boat -> chair2 (t: 0.5->1 -> local_t: 0->1)
                lt = (t - 0.5) * 2.0
                for idx in coords_boat:
                    frame_coords[idx] = _lerp_coords(coords_boat[idx], coords_c2[idx], lt)

            frames.append(frame_coords)
            bonds_per_frame.append(dict(ring_bonds))

            # 에너지: 쌍봉 (두 전이상태)
            if t <= 0.5:
                e = barrier_kcal * math.sin(math.pi * t * 2)
            else:
                e = barrier_kcal * 0.7 * math.sin(math.pi * (t - 0.5) * 2)
            energies.append(e)

            if t < 0.15:
                labels_list.append("reactant")
            elif t > 0.85:
                labels_list.append("product")
            elif 0.4 < t < 0.6:
                labels_list.append("boat")
            else:
                labels_list.append("transition_state")

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=[],
            labels=labels_list,
            n_frames=n_frames,
        )

    # --------------------------------------------------------
    # 4-5. 내부 헬퍼
    # --------------------------------------------------------
    def _detect_bond_changes(
        self,
        bonds_r: Dict[Tuple[int, int], float],
        bonds_p: Dict[Tuple[int, int], float],
        atom_map: Dict[int, int],
        p_only_remap: Dict[int, int],
        n_frames: int,
    ) -> List[BondChange]:
        """반응물/생성물 결합 비교 -> BondChange 목록.

        탐지 대상:
          - break: 반응물에 있으나 생성물에 없는 결합
          - form: 생성물에 있으나 반응물에 없는 결합
          - weaken: 차수 감소 (e.g. double->single)
          - strengthen: 차수 증가 (e.g. single->double)
        원자 매핑(MCS/substructure)을 활용하여 정확한 대응 관계를 파악합니다.
        """
        # N 타입 가드: 외부로부터 전달된 dict 파라미터 검증
        if not isinstance(bonds_r, dict):
            logger.warning(f"_detect_bond_changes: bonds_r 타입 불일치 (expected dict, got {type(bonds_r).__name__})")
            return []
        if not isinstance(bonds_p, dict):
            logger.warning(f"_detect_bond_changes: bonds_p 타입 불일치 (expected dict, got {type(bonds_p).__name__})")
            return []
        if not isinstance(atom_map, dict):
            logger.warning(f"_detect_bond_changes: atom_map 타입 불일치 (expected dict, got {type(atom_map).__name__})")
            return []
        if not isinstance(p_only_remap, dict):
            logger.warning(f"_detect_bond_changes: p_only_remap 타입 불일치 (expected dict, got {type(p_only_remap).__name__})")
            return []

        changes = []
        fs = int(n_frames * self.TRANSITION_START)
        fe = int(n_frames * self.TRANSITION_END)
        seen_pairs = set()  # (unified_i, unified_j) 중복 방지

        def _add_change(ai, aj, ctype):
            """중복 없이 BondChange를 추가하는 헬퍼."""
            key = (min(ai, aj), max(ai, aj))
            if key not in seen_pairs:
                seen_pairs.add(key)
                changes.append(BondChange(fs, fe, key[0], key[1], ctype))

        reverse_map = {v: k for k, v in atom_map.items()}

        # ── 1) 반응물 결합 순회: 끊어지거나 약해지는 결합 탐지 ──
        for (ri, rj), bo_r in bonds_r.items():
            if not isinstance(atom_map, dict):  # Rule N: type guard
                atom_map = {}
            pi = atom_map.get(ri)
            pj = atom_map.get(rj)
            if pi is not None and pj is not None:
                pkey = (min(pi, pj), max(pi, pj))
                if not isinstance(bonds_p, dict):  # Rule N: type guard
                    bonds_p = {}
                bo_p = bonds_p.get(pkey, 0.0)
                if bo_p < 0.1 and bo_r > 0.5:
                    # 결합 완전 절단 (break)
                    _add_change(ri, rj, "break")
                elif bo_p < bo_r - 0.3:
                    # 차수 감소 (weaken): e.g. double(2.0)->single(1.0)
                    _add_change(ri, rj, "weaken")
                elif bo_p > bo_r + 0.3:
                    # 차수 증가 (strengthen): e.g. single(1.0)->double(2.0)
                    _add_change(ri, rj, "strengthen")
            else:
                # 매핑 안 되는 원자와의 결합 = 반응물에서만 존재 → 절단
                if bo_r > 0.5:
                    _add_change(ri, rj, "break")

        # ── 2) 생성물 결합 순회: 새로 형성되는 결합 탐지 ──
        for (pi, pj), bo_p in bonds_p.items():
            if not isinstance(reverse_map, dict):  # Rule N: type guard
                reverse_map = {}
            ri = reverse_map.get(pi)
            rj = reverse_map.get(pj)

            # 2a) 양쪽 모두 매핑된 원자인 경우
            if ri is not None and rj is not None:
                rkey = (min(ri, rj), max(ri, rj))
                if not isinstance(bonds_r, dict):  # Rule N: type guard
                    bonds_r = {}
                bo_r = bonds_r.get(rkey, 0.0)
                if bo_r < 0.1 and bo_p > 0.5:
                    # 새 결합 형성 (form)
                    _add_change(ri, rj, "form")
                elif bo_r > 0.1 and bo_p > bo_r + 0.3:
                    # 차수 증가 (strengthen) — 반응물 쪽에서 이미 처리했을 수 있음
                    _add_change(ri, rj, "strengthen")
                continue

            if not isinstance(p_only_remap, dict):  # Rule N: type guard
                p_only_remap = {}
            # 2b) 한쪽 또는 양쪽이 product-only 원자인 경우
            ui = ri if ri is not None else p_only_remap.get(pi)
            uj = rj if rj is not None else p_only_remap.get(pj)
            if ui is not None and uj is not None:
                ukey = (min(ui, uj), max(ui, uj))
                # 반응물에 이 결합이 없으면 형성
                if ukey not in bonds_r and bo_p > 0.5:
                    _add_change(ui, uj, "form")

        return changes

    def _detect_bond_changes_from_smiles(
        self,
        reactant_smi: str,
        product_smi: str,
        n_frames: int,
    ) -> List[BondChange]:
        """SMILES 기반 결합 변화 탐지 (수소 무시, 중원자 간 결합만 비교).

        3D 임베딩 없이 2D mol 객체의 결합을 직접 비교하여
        MCS 매핑 실패에 강건한 결합 변화 탐지를 수행합니다.

        Returns:
            BondChange 리스트 (reactant atom index 기준)
        """
        # N 타입 가드
        if not isinstance(reactant_smi, str) or not reactant_smi.strip():
            logger.warning(f"_detect_bond_changes_from_smiles: reactant_smi 타입/값 불일치")
            return []
        if not isinstance(product_smi, str) or not product_smi.strip():
            logger.warning(f"_detect_bond_changes_from_smiles: product_smi 타입/값 불일치")
            return []

        mol_r = Chem.MolFromSmiles(reactant_smi)
        mol_p = Chem.MolFromSmiles(product_smi)
        if mol_r is None or mol_p is None:
            return []

        changes = []
        fs = int(n_frames * self.TRANSITION_START)
        fe = int(n_frames * self.TRANSITION_END)

        # MCS 매핑 시도 (2D mol, 경량)
        atom_map = _map_atoms_mcs(mol_r, mol_p)
        if atom_map is None:
            atom_map = _map_atoms_substructure(mol_r, mol_p)
        if atom_map is None:
            # index-order fallback
            n_common = min(mol_r.GetNumAtoms(), mol_p.GetNumAtoms())
            atom_map = {i: i for i in range(n_common)}

        reverse_map = {v: k for k, v in atom_map.items()}

        # 반응물 결합 딕셔너리 (2D)
        bonds_r = {}
        for bond in mol_r.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            bonds_r[(min(i, j), max(i, j))] = bond.GetBondTypeAsDouble()

        bonds_p = {}
        for bond in mol_p.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            bonds_p[(min(i, j), max(i, j))] = bond.GetBondTypeAsDouble()

        # 중복 방지 집합
        seen_pairs = set()

        def _add_smiles_change(ai, aj, ctype):
            key = (min(ai, aj), max(ai, aj))
            if key not in seen_pairs:
                seen_pairs.add(key)
                changes.append(BondChange(fs, fe, key[0], key[1], ctype))

        # 반응물 결합 → 생성물에서 사라지거나 차수가 변한 것
        for (ri, rj), bo_r in bonds_r.items():
            if not isinstance(atom_map, dict):  # Rule N: type guard
                atom_map = {}
            pi = atom_map.get(ri)
            pj = atom_map.get(rj)
            if pi is not None and pj is not None:
                pkey = (min(pi, pj), max(pi, pj))
                if not isinstance(bonds_p, dict):  # Rule N: type guard
                    bonds_p = {}
                bo_p = bonds_p.get(pkey, 0.0)
                if bo_p < 0.1 and bo_r > 0.5:
                    _add_smiles_change(ri, rj, "break")
                elif bo_p < bo_r - 0.3:
                    _add_smiles_change(ri, rj, "weaken")
                elif bo_p > bo_r + 0.3:
                    _add_smiles_change(ri, rj, "strengthen")

        # 생성물 결합 → 반응물에 없는 것 = 형성
        for (pi, pj), bo_p in bonds_p.items():
            if not isinstance(reverse_map, dict):  # Rule N: type guard
                reverse_map = {}
            ri = reverse_map.get(pi)
            rj = reverse_map.get(pj)
            if ri is not None and rj is not None:
                rkey = (min(ri, rj), max(ri, rj))
                if not isinstance(bonds_r, dict):  # Rule N: type guard
                    bonds_r = {}
                bo_r = bonds_r.get(rkey, 0.0)
                if bo_r < 0.1 and bo_p > 0.5:
                    _add_smiles_change(ri, rj, "form")

        return changes

    def _interpolate_bonds(
        self,
        bonds_r: Dict[Tuple[int, int], float],
        bonds_p: Dict[Tuple[int, int], float],
        atom_map: Dict[int, int],
        p_only_remap: Dict[int, int],
        t: float,
    ) -> Dict[Tuple[int, int], float]:
        """프레임 t에서의 결합 차수 딕셔너리.
        코사인 보간을 사용하여 부드러운 결합 차수 전이를 구현합니다."""
        # N 타입 가드: dict 파라미터 검증
        if not isinstance(bonds_r, dict):
            logger.warning(f"_interpolate_bonds: bonds_r 타입 불일치 (expected dict, got {type(bonds_r).__name__})")
            return {}
        if not isinstance(bonds_p, dict):
            logger.warning(f"_interpolate_bonds: bonds_p 타입 불일치 (expected dict, got {type(bonds_p).__name__})")
            return {}
        if not isinstance(atom_map, dict):
            logger.warning(f"_interpolate_bonds: atom_map 타입 불일치 (expected dict, got {type(atom_map).__name__})")
            return {}
        if not isinstance(p_only_remap, dict):
            logger.warning(f"_interpolate_bonds: p_only_remap 타입 불일치 (expected dict, got {type(p_only_remap).__name__})")
            return {}

        result = {}
        reverse_map = {v: k for k, v in atom_map.items()}

        # 반응물 결합
        for (ri, rj), bo_r in bonds_r.items():
            pi = atom_map.get(ri)
            pj = atom_map.get(rj)
            if pi is not None and pj is not None:
                pkey = (min(pi, pj), max(pi, pj))
                bo_p = bonds_p.get(pkey, 0.0)
            else:
                bo_p = 0.0  # 매핑 안 되면 끊어짐

            if t < self.TRANSITION_START:
                bo = bo_r
            elif t > self.TRANSITION_END:
                bo = bo_p
            else:
                frac = (t - self.TRANSITION_START) / (self.TRANSITION_END - self.TRANSITION_START)
                # 코사인 보간: 시작/끝에서 부드럽게 전이
                frac = _cosine_interp(frac)
                bo = bo_r + (bo_p - bo_r) * frac

            if bo > 0.05:
                key = (min(ri, rj), max(ri, rj))
                result[key] = bo

        # 생성물에만 있는 결합 (새로 형성)
        for (pi, pj), bo_p in bonds_p.items():
            if not isinstance(reverse_map, dict):  # Rule N: type guard
                reverse_map = {}
            ri = reverse_map.get(pi)
            rj = reverse_map.get(pj)
            if not isinstance(p_only_remap, dict):  # Rule N: type guard
                p_only_remap = {}
            # 통합 인덱스 결정
            ui = ri if ri is not None else p_only_remap.get(pi)
            uj = rj if rj is not None else p_only_remap.get(pj)
            if ui is None or uj is None:
                continue
            ukey = (min(ui, uj), max(ui, uj))
            if ukey in result:
                continue  # 이미 처리됨

            if t < self.TRANSITION_START:
                bo = 0.0
            elif t > self.TRANSITION_END:
                bo = bo_p
            else:
                frac = (t - self.TRANSITION_START) / (self.TRANSITION_END - self.TRANSITION_START)
                frac = _cosine_interp(frac)
                bo = bo_p * frac
            if bo > 0.05:
                result[ukey] = bo

        return result

    # --------------------------------------------------------
    # 4-6. Diels-Alder [4+2] 고리화 첨가
    # --------------------------------------------------------
    def generate_diels_alder(
        self,
        diene_smi: str,
        dienophile_smi: str,
        n_frames: int = 40,
        barrier_kcal: float = 25.0,
    ) -> Optional[ReactionTrajectory]:
        """Diels-Alder [4+2] 고리화첨가 애니메이션.

        4단계:
        Phase 1 (0-25%): 디엔 + 디에노필 접근 (supra-supra 배향)
        Phase 2 (25-50%): 전이상태 - C1-C6, C4-C5 부분결합 (점선)
        Phase 3 (50-75%): 새 시그마결합 형성 + 파이결합 재배열
        Phase 4 (75-100%): 6원 고리 생성물 완성
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(diene_smi, str) or not diene_smi.strip():
            logger.warning(f"generate_diels_alder: diene_smi 타입/값 불일치 ({type(diene_smi).__name__})")
            return None
        if not isinstance(dienophile_smi, str) or not dienophile_smi.strip():
            logger.warning(f"generate_diels_alder: dienophile_smi 타입/값 불일치 ({type(dienophile_smi).__name__})")
            return None
        try:
            return self._generate_diels_alder_impl(
                diene_smi, dienophile_smi, n_frames, barrier_kcal
            )
        except Exception as e:
            logger.error(f"Diels-Alder animation 실패: {e}", exc_info=True)
            return None

    def _generate_diels_alder_impl(
        self,
        diene_smi: str,
        dienophile_smi: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        """Diels-Alder 내부 구현.

        알고리즘:
        1. 디엔, 디에노필 각각 3D 좌표 생성
        2. 디에노필을 디엔 아래쪽에 suprafacial 배향으로 배치
        3. 접근 → [4+2] TS → 새 시그마결합 형성 → 생성물
        """
        mol_diene = Chem.MolFromSmiles(diene_smi)
        mol_dp = Chem.MolFromSmiles(dienophile_smi)
        if mol_diene is None or mol_dp is None:
            logger.warning("Diels-Alder: SMILES 파싱 실패")
            return None

        mol_diene3d = _embed_3d(Chem.RWMol(mol_diene))
        mol_dp3d = _embed_3d(Chem.RWMol(mol_dp))
        if mol_diene3d is None or mol_dp3d is None:
            logger.warning("Diels-Alder: 3D 임베딩 실패")
            return None

        coords_diene = _get_coords_dict(mol_diene3d)
        symbols_diene = _get_symbols_dict(mol_diene3d)
        bonds_diene = _get_bonds_dict(mol_diene3d)

        coords_dp = _get_coords_dict(mol_dp3d)
        symbols_dp = _get_symbols_dict(mol_dp3d)
        bonds_dp = _get_bonds_dict(mol_dp3d)

        # 디엔의 말단 탄소 찾기 (C1, C4: 공역 디엔의 양 끝)
        # sp2 탄소 중 이웃이 가장 적은 두 원자 = 말단
        diene_sp2 = []
        for atom in mol_diene3d.GetAtoms():
            sym = atom.GetSymbol()
            if sym == '' or sym == 'C':  # Carbon = '' (빈문자열) 규칙 대비
                if atom.GetIsAromatic() or any(
                    b.GetBondTypeAsDouble() >= 1.5
                    for b in atom.GetBonds()
                ):
                    diene_sp2.append(atom.GetIdx())

        # 폴백: sp2 못 찾으면 첫 4개 비수소 원자 사용
        if len(diene_sp2) < 2:
            diene_sp2 = [a.GetIdx() for a in mol_diene3d.GetAtoms()
                         if a.GetSymbol() != 'H'][:4]

        if len(diene_sp2) < 2:
            logger.warning("Diels-Alder: 디엔 말단 탄소 식별 실패")
            return self.generate_frames(diene_smi, dienophile_smi, n_frames, barrier_kcal)

        # 말단 = 인덱스 순서 기준 첫 번째와 마지막 sp2 원자
        c1_idx = diene_sp2[0]      # 디엔 C1
        c4_idx = diene_sp2[-1]     # 디엔 C4

        # 디에노필의 이중결합 양 끝 (C5, C6)
        dp_double = []
        for bond in mol_dp3d.GetBonds():
            if bond.GetBondTypeAsDouble() >= 1.5:
                dp_double.append((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
        if not dp_double:
            # 폴백: 첫 2개 비-H 원자
            dp_heavy = [a.GetIdx() for a in mol_dp3d.GetAtoms()
                        if a.GetSymbol() != 'H'][:2]
            if len(dp_heavy) >= 2:
                dp_double = [(dp_heavy[0], dp_heavy[1])]
            else:
                return self.generate_frames(diene_smi, dienophile_smi, n_frames, barrier_kcal)

        c5_idx_local, c6_idx_local = dp_double[0]

        # 통합 인덱스: 디에노필 원자에 오프셋 적용
        dp_offset = mol_diene3d.GetNumAtoms()
        c5_idx = c5_idx_local + dp_offset
        c6_idx = c6_idx_local + dp_offset

        all_symbols = dict(symbols_diene)
        for didx, sym in symbols_dp.items():
            all_symbols[didx + dp_offset] = sym

        # 디에노필을 디엔 아래쪽에 suprafacial 배치
        # 디엔 무게중심 계산
        centroid_d = _centroid(coords_diene)
        coords_diene = _translate_coords(coords_diene, -centroid_d)

        # 디에노필 무게중심을 디엔 아래 5A에 배치
        centroid_dp = _centroid(coords_dp)
        initial_sep = 5.0   # 초기 분리 거리 (A) — 겹침 방지
        ts_sep = 2.2        # 전이상태 C-C 거리 (A)
        bond_sep = 1.54     # 최종 C-C 결합 거리 (A)
        approach_vec = np.array([0.0, 0.0, -1.0])  # z축 아래에서 접근

        dp_target = centroid_d + approach_vec * initial_sep  # 아래 위치를 기준으로 배치하지 않음
        # 원점 기준으로 dp를 z 아래로 배치
        dp_shift = np.array([0.0, 0.0, -initial_sep]) - centroid_dp
        coords_dp_shifted = {}
        for didx, dc in coords_dp.items():
            shifted = np.array(dc) + dp_shift + np.array([0.0, 0.0, 0.0])
            coords_dp_shifted[didx] = tuple(shifted)

        # 프레임 경계
        p1_end = int(n_frames * 0.25)   # Phase 1 끝
        p2_end = int(n_frames * 0.50)   # Phase 2 끝
        p3_end = int(n_frames * 0.75)   # Phase 3 끝

        # 결합 변화: C1-C6, C4-C5 새 시그마결합 형성
        bond_changes = [
            BondChange(p1_end, p3_end, c1_idx, c6_idx, "form"),
            BondChange(p1_end, p3_end, c4_idx, c5_idx, "form"),
        ]

        # 전하 없음 (동시적 메커니즘), 화살표만
        arrows = [
            ArrowAnnotation(
                from_atom=c1_idx, to_atom=c6_idx,
                frame_start=0, frame_end=p2_end,
                style="dashed", color="green",
            ),
            ArrowAnnotation(
                from_atom=c4_idx, to_atom=c5_idx,
                frame_start=0, frame_end=p2_end,
                style="dashed", color="green",
            ),
        ]

        frames = []
        bonds_per_frame = []
        bond_styles_per_frame = []
        energies = []
        labels_list = []

        c1c6_key = (min(c1_idx, c6_idx), max(c1_idx, c6_idx))
        c4c5_key = (min(c4_idx, c5_idx), max(c4_idx, c5_idx))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            frame_coords = {}
            frame_bonds = {}
            frame_bstyles = {}

            # 접근 진행률 계산 (디에노필이 디엔 쪽으로 이동)
            if fi < p1_end:
                local_t = fi / max(p1_end - 1, 1)
                s = _ease_in_out(local_t)
                # 5A → 3A 접근
                z_offset = -initial_sep + s * (initial_sep - 3.0)  # -5 → -3
                c1c6_bo = 0.0
                c4c5_bo = 0.0
                c1c6_style = "solid"
                c4c5_style = "solid"
                phase_label = "reactant"
            elif fi < p2_end:
                local_t = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                s = _ease_in_out(local_t)
                z_offset = -3.0 + s * (3.0 - ts_sep)  # -3 → -2.2
                c1c6_bo = 0.5 * s    # 부분 결합 형성
                c4c5_bo = 0.5 * s
                c1c6_style = "dotted"   # TS: 점선 표시
                c4c5_style = "dotted"
                phase_label = "transition_state"
            elif fi < p3_end:
                local_t = (fi - p2_end) / max(p3_end - p2_end - 1, 1)
                s = _ease_in_out(local_t)
                z_offset = -ts_sep + s * (ts_sep - bond_sep)  # -2.2 → -1.54
                c1c6_bo = 0.5 + 0.5 * s   # 결합 완성
                c4c5_bo = 0.5 + 0.5 * s
                c1c6_style = "dashed"   # 형성 중
                c4c5_style = "dashed"
                phase_label = "transition_state" if local_t < 0.5 else "product"
            else:
                local_t = (fi - p3_end) / max(n_frames - 1 - p3_end, 1)
                z_offset = -bond_sep  # 최종 결합 거리 유지
                c1c6_bo = 1.0
                c4c5_bo = 1.0
                c1c6_style = "solid"
                c4c5_style = "solid"
                phase_label = "product"

            # 디엔 원자 (고정)
            for aidx, ac in coords_diene.items():
                frame_coords[aidx] = ac

            # 디에노필 원자 (z축 접근)
            for didx, dc in coords_dp_shifted.items():
                # 원래 dp 위치에서 z_offset만큼 조정
                orig = np.array(coords_dp[didx]) + dp_shift
                # z축 이동량 = z_offset - (-initial_sep)
                z_move = z_offset - (-initial_sep)
                new_pos = np.array(dc) + np.array([0.0, 0.0, z_move])
                frame_coords[didx + dp_offset] = tuple(new_pos)

            # 디엔 결합
            for bkey, bo in bonds_diene.items():
                frame_bonds[bkey] = bo
                frame_bstyles[bkey] = "solid"

            # 디에노필 결합 (오프셋 적용)
            for (di, dj), bo in bonds_dp.items():
                ukey = (min(di + dp_offset, dj + dp_offset),
                        max(di + dp_offset, dj + dp_offset))
                frame_bonds[ukey] = bo
                frame_bstyles[ukey] = "solid"

            # 새 시그마 결합 (C1-C6, C4-C5)
            if c1c6_bo > 0.05:
                frame_bonds[c1c6_key] = c1c6_bo
                frame_bstyles[c1c6_key] = c1c6_style
            if c4c5_bo > 0.05:
                frame_bonds[c4c5_key] = c4c5_bo
                frame_bstyles[c4c5_key] = c4c5_style

            # 에너지: 가우시안 장벽 (Ea centered at ~40%, Hammond postulate 준수)
            energy = self._estimate_energy_profile_single(t, barrier_kcal, n_bond_changes=2)

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            bond_styles_per_frame.append(frame_bstyles)
            energies.append(energy)
            labels_list.append(phase_label)

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels_list,
            n_frames=n_frames,
            arrows=arrows,
            bond_styles=bond_styles_per_frame,
        )

    # --------------------------------------------------------
    # 4-7. E2 제거 반응
    # --------------------------------------------------------
    def generate_e2_elimination(
        self,
        substrate_smi: str,
        base_smi: str,
        n_frames: int = 40,
        barrier_kcal: float = 22.0,
    ) -> Optional[ReactionTrajectory]:
        """E2 제거 반응 애니메이션.

        anti-periplanar 기하 → 동시적 H 탈양성자화 + 이탈기 이탈 + 이중결합 형성

        4단계:
        Phase 1 (0-25%): 염기 접근 (anti-periplanar H를 향해)
        Phase 2 (25-50%): 전이상태 - B...H...C=C...LG 선형 TS
        Phase 3 (50-75%): C-H 절단, C-LG 절단, C=C 형성 동시 진행
        Phase 4 (75-100%): 생성물 (알켄 + BH + LG-)
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(substrate_smi, str) or not substrate_smi.strip():
            logger.warning(f"generate_e2_elimination: substrate_smi 타입/값 불일치 ({type(substrate_smi).__name__})")
            return None
        if not isinstance(base_smi, str) or not base_smi.strip():
            logger.warning(f"generate_e2_elimination: base_smi 타입/값 불일치 ({type(base_smi).__name__})")
            return None
        try:
            return self._generate_e2_impl(
                substrate_smi, base_smi, n_frames, barrier_kcal
            )
        except Exception as e:
            logger.error(f"E2 elimination animation 실패: {e}", exc_info=True)
            return None

    def _generate_e2_impl(
        self,
        substrate_smi: str,
        base_smi: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
        """E2 내부 구현.

        핵심: anti-periplanar 배향에서 H와 LG가 동시 이탈하면서 C=C 이중결합 형성.
        기질의 beta-H + alpha-C + beta-C + LG 관계를 자동 탐지.
        """
        mol_sub = Chem.MolFromSmiles(substrate_smi)
        if mol_sub is None:
            return None
        mol_sub3d = _embed_3d(Chem.RWMol(mol_sub))
        if mol_sub3d is None:
            return None

        coords_sub = _get_coords_dict(mol_sub3d)
        symbols_sub = _get_symbols_dict(mol_sub3d)
        bonds_sub = _get_bonds_dict(mol_sub3d)

        # 이탈기 (할로겐) 찾기 → alpha-C → beta-C → beta-H 탐색
        halogen_symbols = {"F", "Cl", "Br", "I"}
        lg_idx = None
        alpha_c = None
        beta_c = None
        beta_h = None

        for atom in mol_sub3d.GetAtoms():
            if atom.GetSymbol() in halogen_symbols:
                lg_idx = atom.GetIdx()
                # alpha-C = 이탈기에 직접 결합된 탄소
                for nbr_a in atom.GetNeighbors():
                    if nbr_a.GetSymbol() == 'C' or nbr_a.GetSymbol() == '':
                        alpha_c = nbr_a.GetIdx()
                        # beta-C = alpha-C의 이웃 탄소 (이탈기 아닌)
                        for nbr_b in nbr_a.GetNeighbors():
                            if nbr_b.GetIdx() == lg_idx:
                                continue
                            if nbr_b.GetSymbol() == 'C' or nbr_b.GetSymbol() == '':
                                beta_c = nbr_b.GetIdx()
                                # beta-H = beta-C에 결합된 수소
                                for nbr_h in nbr_b.GetNeighbors():
                                    if nbr_h.GetSymbol() == 'H':
                                        beta_h = nbr_h.GetIdx()
                                        break
                                if beta_h is not None:
                                    break
                        break
                if beta_h is not None:
                    break

        if any(x is None for x in [lg_idx, alpha_c, beta_c, beta_h]):
            logger.warning("E2: 이탈기/alpha-C/beta-C/beta-H 중 하나를 찾을 수 없음")
            return self.generate_frames(substrate_smi, base_smi, n_frames, barrier_kcal)

        # 염기 3D
        mol_base = Chem.MolFromSmiles(base_smi)
        if mol_base is None:
            return None
        mol_base3d = _embed_3d(Chem.RWMol(mol_base))
        if mol_base3d is None:
            return None

        coords_base = _get_coords_dict(mol_base3d)
        symbols_base = _get_symbols_dict(mol_base3d)

        # 염기의 활성 원자 (N, O 등)
        base_active = 0
        for a in mol_base3d.GetAtoms():
            if a.GetSymbol() in ('N', 'O', 'S'):
                base_active = a.GetIdx()
                break

        # 통합 인덱스
        base_offset = mol_sub3d.GetNumAtoms()
        all_symbols = dict(symbols_sub)
        for bidx, sym in symbols_base.items():
            all_symbols[bidx + base_offset] = sym

        base_active_unified = base_active + base_offset

        # 좌표 기준: 기질 무게중심을 원점으로
        centroid_s = _centroid(coords_sub)
        coords_sub = _translate_coords(coords_sub, -centroid_s)

        # 핵심 원자 좌표 갱신
        h_pos = np.array(coords_sub[beta_h])
        lg_pos = np.array(coords_sub[lg_idx])
        ac_pos = np.array(coords_sub[alpha_c])
        bc_pos = np.array(coords_sub[beta_c])

        # anti-periplanar: 염기는 H 반대편에서 접근 (LG와 같은 쪽)
        # 접근 방향 = beta-C → beta-H 방향의 연장
        approach_dir = _norm(h_pos - bc_pos)
        lg_depart_dir = _norm(lg_pos - ac_pos)  # 이탈기 이탈 방향

        # 염기 초기 위치: beta-H에서 6A 떨어진 곳
        base_start_dist = 6.0   # 초기 분리 (A)
        base_ts_dist = 2.0      # TS 거리 (A) — 수소결합 거리
        base_final_dist = 1.0   # B-H 결합 거리 (A)
        lg_depart_max = 6.0     # 이탈기 최대 이탈 거리 (A)

        base_center_start = h_pos + approach_dir * base_start_dist
        base_ref_pos = np.array(coords_base[base_active])
        base_shift = base_center_start - base_ref_pos

        coords_base_initial = {}
        for bidx, bc in coords_base.items():
            shifted = np.array(bc) + base_shift
            coords_base_initial[bidx] = tuple(shifted)

        # 프레임 경계
        p1_end = int(n_frames * 0.25)
        p2_end = int(n_frames * 0.50)
        p3_end = int(n_frames * 0.75)

        # 결합 변화
        bond_changes = [
            BondChange(p1_end, p3_end, beta_c, beta_h, "break"),   # C_beta-H 절단
            BondChange(p1_end, p3_end, alpha_c, lg_idx, "break"),  # C_alpha-LG 절단
            BondChange(p1_end, p3_end, alpha_c, beta_c, "form"),   # C=C 형성 (단 → 이중)
            BondChange(p1_end, p3_end, beta_h, base_active_unified, "form"),  # B-H 형성
        ]

        # 전하 라벨
        charge_labels = [
            # Phase 2: 전이상태 부분 전하
            ChargeLabel(base_active_unified, "δ-", p1_end, p3_end),
            ChargeLabel(beta_h, "δ+", p1_end, p3_end),
            ChargeLabel(lg_idx, "δ-", p1_end, p3_end),
            # Phase 3-4: 이탈기 음전하
            ChargeLabel(lg_idx, "-", p3_end, n_frames),
        ]

        # 화살표: 염기 → H (탈양성자화 방향)
        arrows = [
            ArrowAnnotation(
                from_atom=base_active_unified, to_atom=beta_h,
                frame_start=0, frame_end=p2_end,
                style="dashed", color="green",
            ),
        ]

        frames = []
        bonds_per_frame = []
        bond_styles_per_frame = []
        energies = []
        labels_list = []

        ch_key = (min(beta_c, beta_h), max(beta_c, beta_h))
        clg_key = (min(alpha_c, lg_idx), max(alpha_c, lg_idx))
        cc_key = (min(alpha_c, beta_c), max(alpha_c, beta_c))
        bh_key = (min(beta_h, base_active_unified), max(beta_h, base_active_unified))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            frame_coords = {}
            frame_bonds = {}
            frame_bstyles = {}

            if fi < p1_end:
                # Phase 1: 염기 접근
                local_t = fi / max(p1_end - 1, 1)
                s = _ease_in_out(local_t)
                base_dist = base_start_dist + (base_ts_dist + 1.0 - base_start_dist) * s
                lg_offset = 0.0
                h_transfer = 0.0
                ch_bo = 1.0
                clg_bo = 1.0
                cc_bo = 1.0   # 원래 단결합
                bh_bo = 0.0
                ch_style = "solid"
                clg_style = "solid"
                cc_style = "solid"
                bh_style = "solid"
                phase_label = "reactant"
            elif fi < p2_end:
                # Phase 2: 전이상태 (anti-periplanar TS)
                local_t = (fi - p1_end) / max(p2_end - p1_end - 1, 1)
                s = _ease_in_out(local_t)
                base_dist = base_ts_dist + 1.0 - s * 1.0  # → ts_dist
                lg_offset = s * 1.0     # LG 약간 이탈 시작
                h_transfer = s * 0.3    # H 약간 이동 시작
                ch_bo = 1.0 - 0.5 * s   # 약화
                clg_bo = 1.0 - 0.5 * s  # 약화
                cc_bo = 1.0 + 0.5 * s   # 1.0 → 1.5 (이중결합화 진행)
                bh_bo = 0.3 * s         # B-H 형성 시작
                ch_style = "dotted"
                clg_style = "dotted"
                cc_style = "dashed"     # 이중결합 형성 중
                bh_style = "dotted"
                phase_label = "transition_state"
            elif fi < p3_end:
                # Phase 3: 결합 변화 완료
                local_t = (fi - p2_end) / max(p3_end - p2_end - 1, 1)
                s = _ease_in_out(local_t)
                base_dist = base_ts_dist - s * (base_ts_dist - base_final_dist)
                lg_offset = 1.0 + s * (lg_depart_max - 1.0)
                h_transfer = 0.3 + s * 0.7  # H 이동 완료
                ch_bo = 0.5 * (1.0 - s)     # 절단
                clg_bo = 0.5 * (1.0 - s)    # 절단
                cc_bo = 1.5 + 0.5 * s       # → 2.0 이중결합
                bh_bo = 0.3 + 0.7 * s       # B-H 형성 완료
                ch_style = "dotted" if ch_bo > 0.05 else "solid"
                clg_style = "dotted" if clg_bo > 0.05 else "solid"
                cc_style = "dashed" if cc_bo < 1.9 else "solid"
                bh_style = "dashed"
                phase_label = "transition_state" if local_t < 0.5 else "product"
            else:
                # Phase 4: 생성물
                local_t = (fi - p3_end) / max(n_frames - 1 - p3_end, 1)
                s = _ease_in_out(local_t)
                base_dist = base_final_dist
                lg_offset = lg_depart_max + s * 2.0  # 더 멀리 이탈
                h_transfer = 1.0
                ch_bo = 0.0
                clg_bo = 0.0
                cc_bo = 2.0
                bh_bo = 1.0
                ch_style = "solid"
                clg_style = "solid"
                cc_style = "solid"
                bh_style = "solid"
                phase_label = "product"

            # ---- 기질 원자 위치 ----
            for aidx, ac in coords_sub.items():
                if aidx == lg_idx:
                    # 이탈기 이탈
                    frame_coords[aidx] = tuple(lg_pos + lg_depart_dir * lg_offset)
                elif aidx == beta_h:
                    # H 이동: 원래 위치 → 염기 쪽
                    h_target = h_pos + approach_dir * (base_start_dist - base_dist + base_final_dist)
                    h_current = h_pos * (1.0 - h_transfer) + h_target * h_transfer
                    frame_coords[aidx] = tuple(h_current)
                else:
                    frame_coords[aidx] = ac

            # ---- 염기 원자 위치 ----
            base_center_current = h_pos + approach_dir * base_dist
            base_shift_current = base_center_current - base_ref_pos
            for bidx, bc in coords_base.items():
                shifted = np.array(bc) + base_shift_current
                frame_coords[bidx + base_offset] = tuple(shifted)

            # ---- 결합 ----
            for bkey, bo in bonds_sub.items():
                # 기질 원래 결합
                bi, bj = bkey
                if bkey == ch_key or (bi in (beta_c, beta_h) and bj in (beta_c, beta_h)):
                    if ch_bo > 0.05:
                        frame_bonds[ch_key] = ch_bo
                        frame_bstyles[ch_key] = ch_style
                elif bkey == clg_key or (bi in (alpha_c, lg_idx) and bj in (alpha_c, lg_idx)):
                    if clg_bo > 0.05:
                        frame_bonds[clg_key] = clg_bo
                        frame_bstyles[clg_key] = clg_style
                elif bkey == cc_key or (bi in (alpha_c, beta_c) and bj in (alpha_c, beta_c)):
                    frame_bonds[cc_key] = cc_bo
                    frame_bstyles[cc_key] = cc_style
                else:
                    frame_bonds[bkey] = bo
                    frame_bstyles[bkey] = "solid"

            # B-H 결합
            if bh_bo > 0.05:
                frame_bonds[bh_key] = bh_bo
                frame_bstyles[bh_key] = bh_style

            # 에너지
            energy = self._estimate_energy_profile_single(t, barrier_kcal, n_bond_changes=4)

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            bond_styles_per_frame.append(frame_bstyles)
            energies.append(energy)
            labels_list.append(phase_label)

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels_list,
            n_frames=n_frames,
            charge_labels=charge_labels,
            arrows=arrows,
            bond_styles=bond_styles_per_frame,
        )

    # --------------------------------------------------------
    # 4-8. 좌표 보간 유틸리티 (public)
    # --------------------------------------------------------
    def _interpolate_coordinates(
        self,
        coords_start: np.ndarray,
        coords_end: np.ndarray,
        n_frames: int,
    ) -> list:
        """시작/끝 좌표 간 선형 Cartesian 보간.

        Args:
            coords_start: (N, 3) 시작 좌표 배열
            coords_end: (N, 3) 끝 좌표 배열
            n_frames: 생성할 프레임 수

        Returns:
            list of (N, 3) ndarray — 각 프레임의 좌표
        """
        # N 타입 가드: ndarray 파라미터 검증
        if not isinstance(coords_start, np.ndarray):
            logger.warning("_interpolate_coordinates: coords_start 타입 불일치 (expected ndarray, got %s)", type(coords_start).__name__)
            return []
        if not isinstance(coords_end, np.ndarray):
            logger.warning("_interpolate_coordinates: coords_end 타입 불일치 (expected ndarray, got %s)", type(coords_end).__name__)
            return []
        if not isinstance(n_frames, int) or n_frames < 1:
            logger.warning("_interpolate_coordinates: n_frames 값 불일치 (%s)", n_frames)
            n_frames = 40  # 기본값 폴백
        if coords_start.shape != coords_end.shape:
            logger.warning("_interpolate_coordinates: 시작/끝 좌표 shape 불일치")
            return [coords_start.copy() for _ in range(n_frames)]

        result = []
        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            s = _ease_in_out(t)
            interp = coords_start + (coords_end - coords_start) * s
            result.append(interp)
        return result

    # --------------------------------------------------------
    # 4-9. 에너지 프로파일 추정
    # --------------------------------------------------------
    def _estimate_energy_profile(
        self,
        n_frames: int,
        n_bond_changes: int = 2,
        barrier_kcal: float = 15.0,
    ) -> list:
        """가우시안 장벽 모델 에너지 프로파일 생성.

        Hammond postulate: 전이상태를 프레임 40%에 배치 (발열 반응 가정).
        결합 변화 수가 많을수록 장벽 높이 스케일링.

        Args:
            n_frames: 프레임 수
            n_bond_changes: 결합 변화 수 (장벽 스케일링에 사용)
            barrier_kcal: 기본 활성화 에너지 (kcal/mol)

        Returns:
            list of float — 각 프레임의 상대 에너지
        """
        # N 타입 가드: 수치 파라미터 검증
        if not isinstance(n_frames, int) or n_frames < 1:
            logger.warning("_estimate_energy_profile: n_frames 값 불일치 (%s)", n_frames)
            n_frames = 40
        if not isinstance(n_bond_changes, int) or n_bond_changes < 0:
            logger.warning("_estimate_energy_profile: n_bond_changes 값 불일치 (%s)", n_bond_changes)
            n_bond_changes = 2
        if not isinstance(barrier_kcal, (int, float)) or barrier_kcal < 0:
            logger.warning("_estimate_energy_profile: barrier_kcal 값 불일치 (%s)", barrier_kcal)
            barrier_kcal = 15.0
        energies = []
        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            energies.append(
                self._estimate_energy_profile_single(t, barrier_kcal, n_bond_changes)
            )
        return energies

    def _estimate_energy_profile_single(
        self,
        t: float,
        barrier_kcal: float = 15.0,
        n_bond_changes: int = 2,
    ) -> float:
        """단일 프레임의 에너지 값 (가우시안 장벽 모델).

        가우시안: E(t) = Ea * exp(-((t - t_peak)^2) / (2 * sigma^2))
        t_peak = 0.40 (Hammond postulate: 발열 반응 TS는 반응물 쪽에 치우침)
        sigma = 0.15 (결합 변화 수에 따라 넓어짐)
        """
        t_peak = 0.40   # 전이상태 위치 (40% 지점, Hammond postulate)
        # sigma: 결합 변화가 많으면 에너지 우물이 넓어짐
        sigma = 0.15 + 0.02 * max(n_bond_changes - 2, 0)  # 기본 0.15, 변화 많으면 확장
        # 장벽 스케일링: 결합 변화 2개 기준, 그 이상이면 약간 증가
        scale = 1.0 + 0.1 * max(n_bond_changes - 2, 0)
        effective_barrier = barrier_kcal * scale
        exponent = -((t - t_peak) ** 2) / (2.0 * sigma ** 2)
        return effective_barrier * math.exp(exponent)

    # --------------------------------------------------------
    # 4-10. Alignment helper (public)
    # --------------------------------------------------------
    def align_molecules(self, mol1, mol2):
        """RDKit AlignMol 래퍼."""
        if not RDKIT_AVAILABLE:
            return
        # N 타입 가드: mol 파라미터 None 체크
        if mol1 is None or mol2 is None:
            logger.warning("align_molecules: mol1 또는 mol2가 None")
            return
        try:
            rdMolAlign.AlignMol(mol2, mol1)
        except Exception as e:
            logger.warning(f"분자 정렬 실패: {e}")

    # --------------------------------------------------------
    # 4-11. Pericyclic Rearrangement (Claisen / Cope)
    # --------------------------------------------------------
    def _generate_pericyclic_rearrangement(
        self,
        reactant_smi: str,
        product_smi: str,
        n_frames: int,
        barrier_kcal: float,
        rearrangement_type: str = "claisen",
    ) -> Optional[ReactionTrajectory]:
        """[3,3]-시그마트로픽 자리옮김 반응 애니메이션 (Claisen / Cope).

        특징:
        - 6원 고리형 전이상태 (의자형)
        - 협동적 결합 재배열: 3개 결합 동시 변화
        - 열 허용 반응 (Woodward-Hoffmann)

        3단계:
        Phase 1 (0-30%): 반응물 분자 배향 + 기하 조정
        Phase 2 (30-70%): 고리형 TS — σ결합 절단 + 새 σ결합 형성 + π재배열
        Phase 3 (70-100%): 생성물 이완
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(reactant_smi, str) or not reactant_smi.strip():
            logger.warning(f"_generate_pericyclic_rearrangement: reactant_smi 타입/값 불일치")
            return None
        if not isinstance(product_smi, str) or not product_smi.strip():
            logger.warning(f"_generate_pericyclic_rearrangement: product_smi 타입/값 불일치")
            return None
        try:
            mol_r = Chem.MolFromSmiles(reactant_smi)
            mol_p = Chem.MolFromSmiles(product_smi)
            if mol_r is None or mol_p is None:
                return None

            mol_r3d = _embed_3d(Chem.RWMol(mol_r))
            mol_p3d = _embed_3d(Chem.RWMol(mol_p))
            if mol_r3d is None or mol_p3d is None:
                return None

            coords_r = _get_coords_dict(mol_r3d)
            coords_p = _get_coords_dict(mol_p3d)
            symbols_r = _get_symbols_dict(mol_r3d)
            symbols_p = _get_symbols_dict(mol_p3d)
            bonds_r = _get_bonds_dict(mol_r3d)
            bonds_p = _get_bonds_dict(mol_p3d)

            # MCS atom mapping
            atom_map = _map_atoms_mcs(mol_r3d, mol_p3d)
            if atom_map is None:
                atom_map = _map_atoms_substructure(mol_r3d, mol_p3d)
            if atom_map is None:
                n_common = min(mol_r3d.GetNumAtoms(), mol_p3d.GetNumAtoms())
                atom_map = {i: i for i in range(n_common)}

            # Align and center
            centroid_r = _centroid(coords_r)
            coords_r = _translate_coords(coords_r, -centroid_r)
            try:
                rdMolAlign.AlignMol(mol_p3d, mol_r3d)
                coords_p = _get_coords_dict(mol_p3d)
            except Exception as e:
                logger.warning("Pericyclic product alignment failed: %s", e)
            centroid_p = _centroid(coords_p)
            coords_p = _translate_coords(coords_p, -centroid_p)

            # Build unified symbol table
            all_symbols = dict(symbols_r)
            max_idx = max(all_symbols.keys()) if all_symbols else -1
            reverse_map = {v: k for k, v in atom_map.items()}
            p_only_remap = {}
            for pidx in range(mol_p3d.GetNumAtoms()):
                if pidx not in reverse_map:
                    max_idx += 1
                    p_only_remap[pidx] = max_idx
                    if not isinstance(symbols_p, dict):  # Rule N: type guard
                        symbols_p = {}
                    all_symbols[max_idx] = symbols_p.get(pidx, "X")

            # Detect heavy-atom bond changes only (filter H noise)
            bond_changes = self._detect_bond_changes_heavy_only(
                mol_r3d, mol_p3d, bonds_r, bonds_p, atom_map, p_only_remap, n_frames
            )

            # For symmetric molecules (e.g., Cope), MCS may map atoms in reverse
            # causing zero bond changes. Use identity mapping if same atom count.
            if not bond_changes and mol_r3d.GetNumAtoms() == mol_p3d.GetNumAtoms():
                identity_map = {i: i for i in range(mol_r3d.GetNumAtoms())}
                bond_changes = self._detect_bond_changes_heavy_only(
                    mol_r3d, mol_p3d, bonds_r, bonds_p, identity_map, {}, n_frames
                )
                # If identity map gives better results, use it for coordinate morph too
                if bond_changes:
                    atom_map = identity_map
                    p_only_remap = {}
                    # Recompute product coords with identity map
                    coords_p = _get_coords_dict(mol_p3d)
                    centroid_p2 = _centroid(coords_p)
                    coords_p = _translate_coords(coords_p, -centroid_p2)

            # If still no changes, try SMILES-based detection as last resort
            if not bond_changes:
                bond_changes = self._detect_bond_changes_from_smiles(
                    reactant_smi, product_smi, n_frames
                )

            # Phase boundaries
            p1_end = int(n_frames * 0.30)  # 배향 조정 완료
            p2_end = int(n_frames * 0.70)  # 전이상태 완료

            # Charge labels for TS
            ts_start = p1_end
            ts_end = p2_end
            charge_labels = []
            arrows = []

            # Reaction-specific energy barriers and annotations
            if rearrangement_type == "claisen":
                # Claisen: ~24 kcal/mol barrier, concerted pericyclic
                effective_barrier = barrier_kcal if barrier_kcal > 20 else 24.0
                charge_labels.append(
                    ChargeLabel(0, "‡", ts_start, ts_end)  # TS marker on first atom
                )
            else:
                # Cope: ~34 kcal/mol barrier for standard, lower for oxy-Cope
                effective_barrier = barrier_kcal if barrier_kcal > 25 else 34.0

            # Generate frames with 3-phase model
            frames = []
            bonds_per_frame = []
            bond_styles_per_frame = []
            energies = []
            labels_list = []

            for fi in range(n_frames):
                t = fi / max(n_frames - 1, 1)
                frame_coords = {}
                frame_bonds = {}
                frame_bstyles = {}

                if t < 0.30:
                    # Phase 1: geometry adjustment (slight contraction toward TS)
                    phase_t = t / 0.30
                    s = _ease_in_out(phase_t)
                    for r_idx, p_idx in atom_map.items():
                        if not isinstance(coords_r, dict):  # Rule N: type guard
                            coords_r = {}
                        c_r = coords_r.get(r_idx, (0, 0, 0))
                        # Slightly contract toward center (TS-like geometry)
                        contracted = (c_r[0] * (1 - 0.05 * s), c_r[1] * (1 - 0.05 * s), c_r[2])
                        frame_coords[r_idx] = contracted
                    bond_t = 0.0
                elif t < 0.70:
                    # Phase 2: concerted bond reorganization
                    phase_t = (t - 0.30) / 0.40
                    s = _cosine_interp(phase_t)
                    for r_idx, p_idx in atom_map.items():
                        c_r = coords_r.get(r_idx, (0, 0, 0))
                        if not isinstance(coords_p, dict):  # Rule N: type guard
                            coords_p = {}
                        c_p = coords_p.get(p_idx, (0, 0, 0))
                        # Contract then morph
                        contracted_r = (c_r[0] * 0.95, c_r[1] * 0.95, c_r[2])
                        frame_coords[r_idx] = _lerp_coords(contracted_r, c_p, s, smooth=True)
                    bond_t = s
                else:
                    # Phase 3: product relaxation
                    phase_t = (t - 0.70) / 0.30
                    s = _ease_in_out(phase_t)
                    for r_idx, p_idx in atom_map.items():
                        c_p = coords_p.get(p_idx, (0, 0, 0))
                        frame_coords[r_idx] = c_p
                    bond_t = 1.0

                # Handle unmapped reactant-only atoms
                for r_idx in coords_r:
                    if r_idx not in atom_map and r_idx not in frame_coords:
                        if not isinstance(coords_r, dict):  # Rule N: type guard
                            coords_r = {}
                        c = coords_r.get(r_idx, (0, 0, 0))
                        if t < 0.30:
                            frame_coords[r_idx] = c
                        else:
                            leave_t = (t - 0.30) / 0.70
                            offset = 4.0 * _ease_in_out(leave_t)
                            frame_coords[r_idx] = (c[0] - offset, c[1], c[2])

                # Handle product-only atoms
                for p_idx, unified_idx in p_only_remap.items():
                    if not isinstance(coords_p, dict):  # Rule N: type guard
                        coords_p = {}
                    c_p = coords_p.get(p_idx, (0, 0, 0))
                    if t < 0.30:
                        frame_coords[unified_idx] = (c_p[0] + 5.0, c_p[1], c_p[2])
                    elif t < 0.70:
                        phase_t2 = (t - 0.30) / 0.40
                        far = (c_p[0] + 5.0, c_p[1], c_p[2])
                        frame_coords[unified_idx] = _lerp_coords(far, c_p, _ease_in_out(phase_t2))
                    else:
                        frame_coords[unified_idx] = c_p

                # Bond interpolation
                frame_bonds = self._interpolate_bonds(
                    bonds_r, bonds_p, atom_map, p_only_remap, bond_t
                )

                # Bond styles: dotted during TS phase for changing bonds
                for bkey in frame_bonds:
                    if 0.25 < t < 0.75:
                        # Check if this bond is changing
                        is_changing = any(
                            (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j)) == (min(bkey[0], bkey[1]), max(bkey[0], bkey[1]))
                            for bc in bond_changes
                        )
                        frame_bstyles[bkey] = "dotted" if is_changing else "solid"
                    else:
                        frame_bstyles[bkey] = "solid"

                frames.append(frame_coords)
                bonds_per_frame.append(frame_bonds)
                bond_styles_per_frame.append(frame_bstyles)

                # Energy: concerted TS with narrow Gaussian (pericyclic)
                energy = effective_barrier * math.exp(-((t - 0.50) ** 2) / (2.0 * 0.12 ** 2))
                energies.append(energy)
                labels_list.append(_frame_label(t))

            return ReactionTrajectory(
                frames=frames,
                atom_symbols=all_symbols,
                bonds_per_frame=bonds_per_frame,
                energies=energies,
                bond_changes=bond_changes,
                labels=labels_list,
                n_frames=n_frames,
                charge_labels=charge_labels,
                arrows=arrows,
                bond_styles=bond_styles_per_frame,
            )
        except Exception as e:
            logger.error(f"Pericyclic rearrangement ({rearrangement_type}) 실패: {e}", exc_info=True)
            return None

    # --------------------------------------------------------
    # 4-12. Carbonyl Rearrangement (Aldol / Beckmann / Baeyer-Villiger / Wittig / Pinacol)
    # --------------------------------------------------------
    def _generate_carbonyl_rearrangement(
        self,
        reactant_smi: str,
        product_smi: str,
        n_frames: int,
        barrier_kcal: float,
        rearrangement_type: str = "aldol",
    ) -> Optional[ReactionTrajectory]:
        """카보닐 관련 자리옮김/첨가 반응 애니메이션.

        지원 유형:
        - aldol: 카보닐 α-탄소 친핵 첨가 → β-하이드록시 카보닐
        - beckmann: 옥심 → 아마이드 (1,2-이동 + N-O 절단)
        - baeyer_villiger: 케톤 + 퍼옥시산 → 에스터 (O 삽입)
        - wittig: 알데히드/케톤 + 일리드 → 알켄
        - pinacol: 비시날 다이올 → 케톤 (1,2-이동)

        공통 3단계:
        Phase 1 (0-30%): 반응물 접근 또는 배향
        Phase 2 (30-70%): 결합 재배열 (키 본드 변화 + 전하 표시)
        Phase 3 (70-100%): 생성물 이완 + 이탈기 분리
        """
        if not RDKIT_AVAILABLE:
            return None
        # N 타입 가드
        if not isinstance(reactant_smi, str) or not reactant_smi.strip():
            logger.warning(f"_generate_carbonyl_rearrangement: reactant_smi 타입/값 불일치")
            return None
        if not isinstance(product_smi, str) or not product_smi.strip():
            logger.warning(f"_generate_carbonyl_rearrangement: product_smi 타입/값 불일치")
            return None
        try:
            mol_r = Chem.MolFromSmiles(reactant_smi)
            mol_p = Chem.MolFromSmiles(product_smi)
            if mol_r is None or mol_p is None:
                return None

            mol_r3d = _embed_3d(Chem.RWMol(mol_r))
            mol_p3d = _embed_3d(Chem.RWMol(mol_p))
            if mol_r3d is None or mol_p3d is None:
                return None

            coords_r = _get_coords_dict(mol_r3d)
            coords_p = _get_coords_dict(mol_p3d)
            symbols_r = _get_symbols_dict(mol_r3d)
            symbols_p = _get_symbols_dict(mol_p3d)
            bonds_r = _get_bonds_dict(mol_r3d)
            bonds_p = _get_bonds_dict(mol_p3d)

            # Atom mapping
            atom_map = _map_atoms_mcs(mol_r3d, mol_p3d)
            if atom_map is None:
                atom_map = _map_atoms_substructure(mol_r3d, mol_p3d)
            if atom_map is None:
                n_common = min(mol_r3d.GetNumAtoms(), mol_p3d.GetNumAtoms())
                atom_map = {i: i for i in range(n_common)}

            # Align and center
            centroid_r = _centroid(coords_r)
            coords_r = _translate_coords(coords_r, -centroid_r)
            try:
                rdMolAlign.AlignMol(mol_p3d, mol_r3d)
                coords_p = _get_coords_dict(mol_p3d)
            except Exception as e:
                logger.warning("Carbonyl rearrangement product alignment failed: %s", e)
            centroid_p = _centroid(coords_p)
            coords_p = _translate_coords(coords_p, -centroid_p)

            # Unified symbols
            all_symbols = dict(symbols_r)
            max_idx = max(all_symbols.keys()) if all_symbols else -1
            reverse_map = {v: k for k, v in atom_map.items()}
            p_only_remap = {}
            for pidx in range(mol_p3d.GetNumAtoms()):
                if pidx not in reverse_map:
                    max_idx += 1
                    p_only_remap[pidx] = max_idx
                    if not isinstance(symbols_p, dict):  # Rule N: type guard
                        symbols_p = {}
                    all_symbols[max_idx] = symbols_p.get(pidx, "X")

            # Heavy-atom bond changes
            bond_changes = self._detect_bond_changes_heavy_only(
                mol_r3d, mol_p3d, bonds_r, bonds_p, atom_map, p_only_remap, n_frames
            )

            # Reaction-specific parameters
            energy_barriers = {
                "aldol": 18.0,       # Aldol addition
                "beckmann": 25.0,    # Beckmann rearrangement
                "baeyer_villiger": 22.0,  # Baeyer-Villiger oxidation
                "wittig": 12.0,      # Wittig reaction (low barrier)
                "pinacol": 20.0,     # Pinacol rearrangement
            }
            if not isinstance(energy_barriers, dict):  # Rule N: type guard
                energy_barriers = {}
            effective_barrier = barrier_kcal if barrier_kcal > 10 else energy_barriers.get(rearrangement_type, 15.0)

            # Charge labels based on reaction type
            charge_labels = []
            arrows = []
            p1_end = int(n_frames * 0.30)
            p2_end = int(n_frames * 0.70)

            if rearrangement_type == "beckmann":
                # Find the N and O in oxime
                for atom in mol_r3d.GetAtoms():
                    if atom.GetSymbol() == "N":
                        charge_labels.append(ChargeLabel(atom.GetIdx(), "δ+", p1_end, p2_end))
                    elif atom.GetSymbol() == "O":
                        charge_labels.append(ChargeLabel(atom.GetIdx(), "δ-", p1_end, p2_end))
            elif rearrangement_type == "baeyer_villiger":
                # Carbonyl carbon gets δ+, migrating group
                for atom in mol_r3d.GetAtoms():
                    if atom.GetSymbol() == "O":
                        charge_labels.append(ChargeLabel(atom.GetIdx(), "δ-", p1_end, p2_end))
                        break
            elif rearrangement_type == "aldol":
                # Electrophilic carbonyl carbon
                for atom in mol_r3d.GetAtoms():
                    if atom.GetSymbol() == "O":
                        for nbr in atom.GetNeighbors():
                            if nbr.GetSymbol() in ('C', ''):
                                charge_labels.append(ChargeLabel(nbr.GetIdx(), "δ+", p1_end, p2_end))
                                charge_labels.append(ChargeLabel(atom.GetIdx(), "δ-", p1_end, p2_end))
                                break
                        break

            # Spatial separation for bimolecular reactions (aldol, wittig)
            is_bimolecular = rearrangement_type in ("aldol", "wittig")
            initial_sep = 3.0 if is_bimolecular else 0.0  # Angstroms

            if is_bimolecular:
                coords_r = _translate_coords(coords_r, np.array([-initial_sep / 2, 0.0, 0.0]))
                coords_p = _translate_coords(coords_p, np.array([initial_sep / 2, 0.0, 0.0]))

            # Generate frames
            frames = []
            bonds_per_frame = []
            bond_styles_per_frame = []
            energies_list = []
            labels_list = []

            for fi in range(n_frames):
                t = fi / max(n_frames - 1, 1)
                frame_coords = {}
                frame_bonds = {}
                frame_bstyles = {}

                if t < 0.30:
                    # Phase 1: approach / orientation
                    phase_t = t / 0.30
                    s = _ease_in_out(phase_t)
                    for r_idx, p_idx in atom_map.items():
                        if not isinstance(coords_r, dict):  # Rule N: type guard
                            coords_r = {}
                        c_r = coords_r.get(r_idx, (0, 0, 0))
                        if not isinstance(coords_p, dict):  # Rule N: type guard
                            coords_p = {}
                        c_p = coords_p.get(p_idx, (0, 0, 0))
                        if is_bimolecular:
                            # Move toward midpoint
                            mid = ((c_r[0] + c_p[0]) / 2, (c_r[1] + c_p[1]) / 2, (c_r[2] + c_p[2]) / 2)
                            frame_coords[r_idx] = _lerp_coords(c_r, mid, s * 0.5, smooth=True)
                        else:
                            frame_coords[r_idx] = c_r
                    bond_t = 0.0
                elif t < 0.70:
                    # Phase 2: bond reorganization
                    phase_t = (t - 0.30) / 0.40
                    s = _cosine_interp(phase_t)
                    if not isinstance(coords_r, dict):  # Rule N: type guard
                        coords_r = {}
                    if not isinstance(coords_p, dict):  # Rule N: type guard
                        coords_p = {}
                    for r_idx, p_idx in atom_map.items():
                        c_r = coords_r.get(r_idx, (0, 0, 0))
                        c_p = coords_p.get(p_idx, (0, 0, 0))
                        if is_bimolecular:
                            mid = ((c_r[0] + c_p[0]) / 2, (c_r[1] + c_p[1]) / 2, (c_r[2] + c_p[2]) / 2)
                            start = _lerp_coords(c_r, mid, 0.5, smooth=True)
                        else:
                            start = c_r
                        frame_coords[r_idx] = _lerp_coords(start, c_p, s, smooth=True)
                    bond_t = s
                else:
                    # Phase 3: product relaxation
                    for r_idx, p_idx in atom_map.items():
                        if not isinstance(coords_p, dict):  # Rule N: type guard
                            coords_p = {}
                        c_p = coords_p.get(p_idx, (0, 0, 0))
                        frame_coords[r_idx] = c_p
                    bond_t = 1.0

                # Unmapped reactant atoms (leaving groups)
                for r_idx in coords_r:
                    if r_idx not in atom_map and r_idx not in frame_coords:
                        if not isinstance(coords_r, dict):  # Rule N: type guard
                            coords_r = {}
                        c = coords_r.get(r_idx, (0, 0, 0))
                        if t < 0.30:
                            frame_coords[r_idx] = c
                        else:
                            leave_t = (t - 0.30) / 0.70
                            offset = 5.0 * _ease_in_out(leave_t)
                            frame_coords[r_idx] = (c[0] - offset, c[1], c[2])

                # Product-only atoms (entering groups)
                for p_idx, unified_idx in p_only_remap.items():
                    if not isinstance(coords_p, dict):  # Rule N: type guard
                        coords_p = {}
                    c_p = coords_p.get(p_idx, (0, 0, 0))
                    if t < 0.30:
                        frame_coords[unified_idx] = (c_p[0] + 5.0, c_p[1], c_p[2])
                    elif t < 0.70:
                        phase_t2 = (t - 0.30) / 0.40
                        far = (c_p[0] + 5.0, c_p[1], c_p[2])
                        frame_coords[unified_idx] = _lerp_coords(far, c_p, _ease_in_out(phase_t2))
                    else:
                        frame_coords[unified_idx] = c_p

                # Bond interpolation
                frame_bonds = self._interpolate_bonds(
                    bonds_r, bonds_p, atom_map, p_only_remap, bond_t
                )

                # Bond styles
                for bkey in frame_bonds:
                    if 0.25 < t < 0.75:
                        is_changing = any(
                            (min(bc.atom_i, bc.atom_j), max(bc.atom_i, bc.atom_j)) == (min(bkey[0], bkey[1]), max(bkey[0], bkey[1]))
                            for bc in bond_changes
                        )
                        frame_bstyles[bkey] = "dotted" if is_changing else "solid"
                    else:
                        frame_bstyles[bkey] = "solid"

                frames.append(frame_coords)
                bonds_per_frame.append(frame_bonds)
                bond_styles_per_frame.append(frame_bstyles)

                # Energy profile with Hammond postulate offset
                # Beckmann/Pinacol: endothermic → TS closer to product (t_peak=0.55)
                # Aldol/Wittig: exothermic → TS closer to reactant (t_peak=0.40)
                t_peak = 0.55 if rearrangement_type in ("beckmann", "pinacol") else 0.40
                sigma = 0.15  # Narrow TS for concerted
                energy = effective_barrier * math.exp(-((t - t_peak) ** 2) / (2.0 * sigma ** 2))
                energies_list.append(energy)
                labels_list.append(_frame_label(t))

            return ReactionTrajectory(
                frames=frames,
                atom_symbols=all_symbols,
                bonds_per_frame=bonds_per_frame,
                energies=energies_list,
                bond_changes=bond_changes,
                labels=labels_list,
                n_frames=n_frames,
                charge_labels=charge_labels,
                arrows=arrows,
                bond_styles=bond_styles_per_frame,
            )
        except Exception as e:
            logger.error(f"Carbonyl rearrangement ({rearrangement_type}) 실패: {e}", exc_info=True)
            return None

    # --------------------------------------------------------
    # 4-13. Heavy-atom-only bond change detection
    # --------------------------------------------------------
    def _detect_bond_changes_heavy_only(
        self,
        mol_r,
        mol_p,
        bonds_r: Dict[Tuple[int, int], float],
        bonds_p: Dict[Tuple[int, int], float],
        atom_map: Dict[int, int],
        p_only_remap: Dict[int, int],
        n_frames: int,
    ) -> List[BondChange]:
        """결합 변화 탐지 — 수소 관련 결합 변화를 필터링하여 핵심 변화만 반환.

        수소 원자와의 결합 변화는 화학적으로 중요하지 않은 경우가 많으므로
        (3D 임베딩 시 H 위치 차이로 인한 노이즈) 중원자 간 결합만 추적합니다.

        Returns:
            BondChange 리스트 (중원자 간 변화만 포함)
        """
        # N 타입 가드: dict 파라미터 검증
        if not isinstance(bonds_r, dict):
            logger.warning("_detect_bond_changes_heavy_only: bonds_r 타입 불일치 (expected dict, got %s)", type(bonds_r).__name__)
            return []
        if not isinstance(bonds_p, dict):
            logger.warning("_detect_bond_changes_heavy_only: bonds_p 타입 불일치 (expected dict, got %s)", type(bonds_p).__name__)
            return []
        if not isinstance(atom_map, dict):
            logger.warning("_detect_bond_changes_heavy_only: atom_map 타입 불일치 (expected dict, got %s)", type(atom_map).__name__)
            return []
        if not isinstance(p_only_remap, dict):
            logger.warning("_detect_bond_changes_heavy_only: p_only_remap 타입 불일치 (expected dict, got %s)", type(p_only_remap).__name__)
            return []
        if mol_r is None or mol_p is None:
            logger.warning("_detect_bond_changes_heavy_only: mol_r 또는 mol_p가 None")
            return []
        # Get full bond changes first
        all_changes = self._detect_bond_changes(
            bonds_r, bonds_p, atom_map, p_only_remap, n_frames
        )

        # Build H-atom index sets
        h_indices_r = set()
        for atom in mol_r.GetAtoms():
            if atom.GetSymbol() == "H":
                h_indices_r.add(atom.GetIdx())

        h_indices_p = set()
        for atom in mol_p.GetAtoms():
            if atom.GetSymbol() == "H":
                h_indices_p.add(atom.GetIdx())

        # p_only_remap values are unified indices for product-only atoms
        h_unified = set()
        reverse_map = {v: k for k, v in atom_map.items()}
        for pidx in h_indices_p:
            if pidx in reverse_map:
                ridx = reverse_map[pidx]
                if ridx in h_indices_r:
                    h_unified.add(ridx)
            elif pidx in p_only_remap:
                h_unified.add(p_only_remap[pidx])

        h_all = h_indices_r | h_unified

        # Filter: keep only changes where BOTH atoms are heavy
        filtered = []
        for bc in all_changes:
            if bc.atom_i not in h_all and bc.atom_j not in h_all:
                filtered.append(bc)

        # If filtering removed everything, fall back to SMILES-based detection
        if not filtered and all_changes:
            filtered = self._detect_bond_changes_from_smiles(
                Chem.MolToSmiles(Chem.RemoveHs(mol_r)) if mol_r else "",
                Chem.MolToSmiles(Chem.RemoveHs(mol_p)) if mol_p else "",
                n_frames,
            )

        return filtered

    # --------------------------------------------------------
    # TS Detection: 전이상태 프레임 감지
    # --------------------------------------------------------
    @staticmethod
    def get_transition_state_frame_index(trajectory: 'ReactionTrajectory') -> int:
        """에너지 최대값(전이상태) 프레임 인덱스를 반환.

        에너지 프로파일이 있으면 argmax 사용, 없으면 40-60% 구간 중앙 휴리스틱.
        """
        # N 타입 가드: trajectory 검증
        if trajectory is None:
            return 0
        if not isinstance(trajectory, ReactionTrajectory):
            logger.warning("get_transition_state_frame_index: trajectory 타입 불일치 (expected ReactionTrajectory, got %s)", type(trajectory).__name__)
            return 0
        if trajectory.n_frames == 0:
            return 0
        # 에너지 프로파일 존재 시 최대값 프레임
        if isinstance(trajectory.energies, list) and len(trajectory.energies) == trajectory.n_frames:
            max_e = max(trajectory.energies)
            if max_e > 0:  # 유효한 에너지 프로파일
                return int(np.argmax(trajectory.energies))
        # 휴리스틱: 전체 프레임의 50% 지점 (전이상태는 보통 중앙)
        return trajectory.n_frames // 2

    @staticmethod
    def get_key_frame_indices(trajectory: 'ReactionTrajectory') -> dict:
        """반응물, 전이상태, 생성물의 프레임 인덱스를 반환.

        Returns:
            {'reactant': int, 'transition_state': int, 'product': int}
        """
        # N 타입 가드: trajectory 검증
        if trajectory is None:
            return {'reactant': 0, 'transition_state': 0, 'product': 0}
        if not isinstance(trajectory, ReactionTrajectory):
            logger.warning("get_key_frame_indices: trajectory 타입 불일치 (expected ReactionTrajectory, got %s)", type(trajectory).__name__)
            return {'reactant': 0, 'transition_state': 0, 'product': 0}
        if trajectory.n_frames == 0:
            return {'reactant': 0, 'transition_state': 0, 'product': 0}
        ts_idx = ReactionAnimationEngine.get_transition_state_frame_index(trajectory)
        return {
            'reactant': 0,
            'transition_state': ts_idx,
            'product': trajectory.n_frames - 1,
        }
