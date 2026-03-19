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
    from rdkit.Chem import AllChem, rdFMCS, rdMolAlign
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
class ReactionTrajectory:
    """반응 애니메이션 전체 궤적 데이터."""
    frames: List[Dict[int, Tuple[float, float, float]]]         # 프레임별 atom_idx -> (x, y, z)
    atom_symbols: Dict[int, str]                                 # atom_idx -> element symbol
    bonds_per_frame: List[Dict[Tuple[int, int], float]]          # 프레임별 (i,j) -> bond_order
    energies: List[float]                                        # 프레임별 상대 에너지 (kcal/mol)
    bond_changes: List[BondChange]                               # 결합 변화 목록
    labels: List[str]                                            # 프레임별 라벨 ("reactant" / "transition_state" / "product")
    n_frames: int                                                # 총 프레임 수


# ============================================================
# Section 2: Helper Utilities
# ============================================================

def _ease_in_out(t: float) -> float:
    """Smoothstep ease-in-out: 0->0, 0.5->0.5, 1->1."""
    return 3 * t * t - 2 * t * t * t


def _lerp_coords(
    c1: Tuple[float, float, float],
    c2: Tuple[float, float, float],
    t: float,
    smooth: bool = True,
) -> Tuple[float, float, float]:
    """두 3D 좌표 간 선형(또는 ease) 보간."""
    s = _ease_in_out(t) if smooth else t
    return (
        c1[0] + (c2[0] - c1[0]) * s,
        c1[1] + (c2[1] - c1[1]) * s,
        c1[2] + (c2[2] - c1[2]) * s,
    )


def _parabolic_energy(t: float, barrier: float = 15.0) -> float:
    """포물선 에너지: E(t) = barrier * 4*t*(1-t).  최대값 = barrier at t=0.5."""
    return barrier * 4.0 * t * (1.0 - t)


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
            return None
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    except Exception:
        pass
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
        return None
    try:
        mcs = rdFMCS.FindMCS(
            [mol_r, mol_p],
            timeout=5,
            bondCompare=rdFMCS.BondCompare.CompareAny,
            atomCompare=rdFMCS.AtomCompare.CompareElements,
        )
        if mcs.numAtoms == 0:
            return None
        patt = Chem.MolFromSmarts(mcs.smartsString)
        if patt is None:
            return None
        match_r = mol_r.GetSubstructMatch(patt)
        match_p = mol_p.GetSubstructMatch(patt)
        if not match_r or not match_p or len(match_r) != len(match_p):
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
    except Exception:
        pass
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
        """범용 반응 애니메이션 프레임 생성.

        1. SMILES -> RDKit mol + 3D 좌표
        2. MCS 원자 매핑
        3. 프레임별 좌표 보간 + 결합 차수 전이
        4. 에너지 프로파일 (포물선)
        """
        if not RDKIT_AVAILABLE:
            return None
        try:
            return self._generate_frames_impl(
                reactant_smiles, product_smiles, n_frames, barrier_kcal
            )
        except Exception as e:
            logger.error(f"generate_frames 실패: {e}", exc_info=True)
            return None

    def _generate_frames_impl(
        self,
        reactant_smiles: str,
        product_smiles: str,
        n_frames: int,
        barrier_kcal: float,
    ) -> Optional[ReactionTrajectory]:
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

        # 정렬: 반응물 무게중심을 원점으로
        centroid_r = _centroid(coords_r)
        coords_r = _translate_coords(coords_r, -centroid_r)

        # 생성물도 반응물 무게중심 기준 정렬
        try:
            rdMolAlign.AlignMol(mol_p3d, mol_r3d)
            coords_p = _get_coords_dict(mol_p3d)
        except Exception:
            pass
        centroid_p = _centroid(coords_p)
        coords_p = _translate_coords(coords_p, -centroid_p)

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
                all_symbols[max_idx] = symbols_p.get(pidx, "X")

        # 5) 결합 변화 탐지
        bond_changes = self._detect_bond_changes(
            bonds_r, bonds_p, atom_map, p_only_remap, n_frames
        )

        # 6) 프레임 생성
        frames = []
        bonds_per_frame = []
        energies = []
        labels = []

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            frame_coords = {}
            frame_bonds = {}

            # 매핑된 원자: 보간
            for r_idx, p_idx in atom_map.items():
                c_r = coords_r.get(r_idx, (0, 0, 0))
                c_p = coords_p.get(p_idx, (0, 0, 0))
                frame_coords[r_idx] = _lerp_coords(c_r, c_p, t)

            # 반응물에만 있는 원자: 점차 사라짐 (이탈기 등)
            for r_idx in coords_r:
                if r_idx not in atom_map and r_idx not in frame_coords:
                    c = coords_r[r_idx]
                    # 이탈 방향으로 이동
                    offset = 3.0 * t
                    frame_coords[r_idx] = (c[0] + offset, c[1], c[2])

            # 생성물에만 있는 원자: 점차 등장
            for p_idx, unified_idx in p_only_remap.items():
                c = coords_p.get(p_idx, (0, 0, 0))
                offset = 3.0 * (1.0 - t)
                frame_coords[unified_idx] = (c[0] - offset, c[1], c[2])

            # 결합 차수 보간
            frame_bonds = self._interpolate_bonds(
                bonds_r, bonds_p, atom_map, p_only_remap, t
            )

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            energies.append(_parabolic_energy(t, barrier_kcal))
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
        attack_dir = _norm(c_pos - lg_pos)  # C -> 반대쪽
        nuc_start_dist = 5.0   # 초기 거리 (A)
        nuc_bond_dist = 1.5    # 최종 결합 거리 (A)

        # 통합 원자 인덱스: 기질 유지, 친핵체는 오프셋
        nuc_offset = mol_sub3d.GetNumAtoms()
        all_symbols = dict(symbols_sub)
        for nidx, sym in symbols_nuc.items():
            all_symbols[nidx + nuc_offset] = sym

        # 프레임 생성
        frames = []
        bonds_per_frame = []
        energies = []
        labels_list = []
        bond_changes = []

        # 결합 변화 기록
        bond_changes.append(BondChange(
            frame_start=int(n_frames * 0.3),
            frame_end=int(n_frames * 0.7),
            atom_i=c_center,
            atom_j=lg_idx,
            change_type="break",
        ))
        bond_changes.append(BondChange(
            frame_start=int(n_frames * 0.3),
            frame_end=int(n_frames * 0.7),
            atom_i=c_center,
            atom_j=nuc_atom_idx + nuc_offset,
            change_type="form",
        ))

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            s = _ease_in_out(t)

            frame_coords = {}
            frame_bonds = {}

            # 친핵체 위치: 멀리서 접근
            nuc_dist = nuc_start_dist * (1 - s) + nuc_bond_dist * s
            nuc_center = c_pos + attack_dir * nuc_dist
            nuc_ref = np.array(coords_nuc[nuc_atom_idx])
            nuc_shift = nuc_center - nuc_ref
            for nidx, nc in coords_nuc.items():
                shifted = np.array(nc) + nuc_shift
                frame_coords[nidx + nuc_offset] = tuple(shifted)

            # 이탈기 위치: 점차 이탈
            lg_dist = 0.0 + s * 4.0  # 원래 위치에서 4A 이탈
            lg_dir = _norm(lg_pos - c_pos)

            # 기질 원자 위치 (Walden 반전 적용)
            for aidx, acoords in coords_sub.items():
                ac = np.array(acoords)
                if aidx == lg_idx:
                    # 이탈기: 점차 이동
                    new_pos = lg_pos + lg_dir * lg_dist
                    frame_coords[aidx] = tuple(new_pos)
                elif aidx == c_center:
                    frame_coords[aidx] = tuple(c_pos)
                else:
                    # 다른 치환기: Walden 반전 (중심 탄소 기준 뒤집기)
                    # 공격 축에 대해 반전 (t=0: 원래, t=1: 반전)
                    vec = ac - c_pos
                    # 공격 축 성분
                    proj = np.dot(vec, attack_dir) * attack_dir
                    perp = vec - proj
                    # 축 방향 성분 반전
                    inverted_vec = -proj + perp
                    final_vec = vec * (1 - s) + inverted_vec * s
                    frame_coords[aidx] = tuple(c_pos + final_vec)

            # 결합 차수
            for bkey, bo in bonds_sub.items():
                bi, bj = bkey
                if (bi == c_center and bj == lg_idx) or (bi == lg_idx and bj == c_center):
                    # C-LG 결합 끊어짐
                    if t < self.TRANSITION_START:
                        frame_bonds[bkey] = bo
                    elif t > self.TRANSITION_END:
                        frame_bonds[bkey] = 0.0
                    else:
                        frac = (t - self.TRANSITION_START) / (self.TRANSITION_END - self.TRANSITION_START)
                        frame_bonds[bkey] = bo * (1 - frac)
                else:
                    frame_bonds[bkey] = bo

            # C-Nuc 결합 형성
            nuc_bond_key = (min(c_center, nuc_atom_idx + nuc_offset),
                           max(c_center, nuc_atom_idx + nuc_offset))
            if t < self.TRANSITION_START:
                frame_bonds[nuc_bond_key] = 0.0
            elif t > self.TRANSITION_END:
                frame_bonds[nuc_bond_key] = 1.0
            else:
                frac = (t - self.TRANSITION_START) / (self.TRANSITION_END - self.TRANSITION_START)
                frame_bonds[nuc_bond_key] = frac

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            energies.append(_parabolic_energy(t, barrier_kcal))
            labels_list.append(_frame_label(t))

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels_list,
            n_frames=n_frames,
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

        # 염기 배치: 산의 H 근처에 수용 원자가 오도록
        h_pos = np.array(coords_acid[h_idx])
        donor_pos = np.array(coords_acid[donor_idx])
        approach_dir = _norm(h_pos - donor_pos)
        base_acceptor_pos = np.array(coords_base[acceptor_idx])
        target_pos = h_pos + approach_dir * 3.0
        base_shift = target_pos - base_acceptor_pos

        coords_base_shifted = {}
        for bidx, bc in coords_base.items():
            shifted = np.array(bc) + base_shift
            coords_base_shifted[bidx] = tuple(shifted)

        # 프레임 생성
        frames = []
        bonds_per_frame = []
        energies = []
        labels_list = []

        bond_changes = [
            BondChange(int(n_frames * 0.3), int(n_frames * 0.7),
                       donor_idx, h_idx, "break"),
            BondChange(int(n_frames * 0.3), int(n_frames * 0.7),
                       h_idx, acceptor_idx + base_offset, "form"),
        ]

        for fi in range(n_frames):
            t = fi / max(n_frames - 1, 1)
            s = _ease_in_out(t)
            frame_coords = {}
            frame_bonds = {}

            # 산 원자 (H 제외) 고정
            for aidx, ac in coords_acid.items():
                if aidx == h_idx:
                    # H 이동: donor -> acceptor 방향
                    donor_p = np.array(coords_acid[donor_idx])
                    accept_p = np.array(coords_base_shifted[acceptor_idx])
                    # H 위치: donor 근처 -> acceptor 근처
                    h_start = donor_p + _norm(h_pos - donor_p) * 1.0
                    h_end = accept_p + _norm(accept_p - donor_p) * (-1.0)
                    h_current = h_start * (1 - s) + h_end * s
                    frame_coords[aidx] = tuple(h_current)
                else:
                    frame_coords[aidx] = ac

            # 염기 원자
            for bidx, bc in coords_base_shifted.items():
                # 염기 약간 접근
                approach = np.array(bc) - approach_dir * s * 0.5
                frame_coords[bidx + base_offset] = tuple(approach)

            # 결합: donor-H 약화, acceptor-H 형성
            for bkey, bo in bonds_acid.items():
                bi, bj = bkey
                if (bi == donor_idx and bj == h_idx) or (bi == h_idx and bj == donor_idx):
                    if t < self.TRANSITION_START:
                        frame_bonds[bkey] = bo
                    elif t > self.TRANSITION_END:
                        frame_bonds[bkey] = 0.0
                    else:
                        frac = (t - self.TRANSITION_START) / (self.TRANSITION_END - self.TRANSITION_START)
                        frame_bonds[bkey] = bo * (1 - frac)
                else:
                    frame_bonds[bkey] = bo

            # 새 결합: H-acceptor
            new_key = (min(h_idx, acceptor_idx + base_offset),
                       max(h_idx, acceptor_idx + base_offset))
            if t < self.TRANSITION_START:
                frame_bonds[new_key] = 0.0
            elif t > self.TRANSITION_END:
                frame_bonds[new_key] = 1.0
            else:
                frac = (t - self.TRANSITION_START) / (self.TRANSITION_END - self.TRANSITION_START)
                frame_bonds[new_key] = frac

            frames.append(frame_coords)
            bonds_per_frame.append(frame_bonds)
            energies.append(_parabolic_energy(t, barrier_kcal))
            labels_list.append(_frame_label(t))

        return ReactionTrajectory(
            frames=frames,
            atom_symbols=all_symbols,
            bonds_per_frame=bonds_per_frame,
            energies=energies,
            bond_changes=bond_changes,
            labels=labels_list,
            n_frames=n_frames,
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
        """반응물/생성물 결합 비교 -> BondChange 목록."""
        changes = []
        fs = int(n_frames * self.TRANSITION_START)
        fe = int(n_frames * self.TRANSITION_END)

        # 반응물 결합 -> 끊어지는지 확인
        reverse_map = {v: k for k, v in atom_map.items()}
        for (ri, rj), bo_r in bonds_r.items():
            # 대응하는 생성물 결합 찾기
            pi = atom_map.get(ri)
            pj = atom_map.get(rj)
            if pi is not None and pj is not None:
                pkey = (min(pi, pj), max(pi, pj))
                bo_p = bonds_p.get(pkey, 0.0)
                if bo_p < 0.1 and bo_r > 0.5:
                    changes.append(BondChange(fs, fe, ri, rj, "break"))
                elif bo_p < bo_r - 0.3:
                    changes.append(BondChange(fs, fe, ri, rj, "weaken"))

        # 생성물에만 있는 결합 -> 형성
        for (pi, pj), bo_p in bonds_p.items():
            ri = reverse_map.get(pi)
            rj = reverse_map.get(pj)
            if ri is not None and rj is not None:
                rkey = (min(ri, rj), max(ri, rj))
                bo_r = bonds_r.get(rkey, 0.0)
                if bo_r < 0.1 and bo_p > 0.5:
                    changes.append(BondChange(fs, fe, ri, rj, "form"))

        return changes

    def _interpolate_bonds(
        self,
        bonds_r: Dict[Tuple[int, int], float],
        bonds_p: Dict[Tuple[int, int], float],
        atom_map: Dict[int, int],
        p_only_remap: Dict[int, int],
        t: float,
    ) -> Dict[Tuple[int, int], float]:
        """프레임 t에서의 결합 차수 딕셔너리."""
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
                bo = bo_r + (bo_p - bo_r) * frac

            if bo > 0.05:
                key = (min(ri, rj), max(ri, rj))
                result[key] = bo

        # 생성물에만 있는 결합 (새로 형성)
        for (pi, pj), bo_p in bonds_p.items():
            ri = reverse_map.get(pi)
            rj = reverse_map.get(pj)
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
                bo = bo_p * frac
            if bo > 0.05:
                result[ukey] = bo

        return result

    # --------------------------------------------------------
    # 4-6. Alignment helper (public)
    # --------------------------------------------------------
    def align_molecules(self, mol1, mol2):
        """RDKit AlignMol 래퍼."""
        if not RDKIT_AVAILABLE:
            return
        try:
            rdMolAlign.AlignMol(mol2, mol1)
        except Exception as e:
            logger.warning(f"분자 정렬 실패: {e}")
