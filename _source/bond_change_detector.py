# bond_change_detector.py (v1.0 - Bond Change Detection via Atom Mapping)
"""
ChemGrid: 반응물/생성물 SMILES 비교를 통한 결합 변화 탐지 엔진
- rdFMCS (Maximum Common Substructure) 기반 원자 매핑
- Fallback: Morgan fingerprint + Hungarian algorithm
- 결합 끊김/생성/차수변화 자동 탐지
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdFMCS, rdmolops
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class BondChange:
    """결합 변화 단위"""
    atom_i: int             # 반응물 원자 인덱스
    atom_j: int             # 반응물 원자 인덱스
    reactant_order: float   # 0 = 반응물에 없음
    product_order: float    # 0 = 생성물에 없음
    change_type: str        # "broken", "formed", "order_increase", "order_decrease"

    @property
    def is_broken(self) -> bool:
        return self.change_type == "broken"

    @property
    def is_formed(self) -> bool:
        return self.change_type == "formed"


@dataclass
class ChargeChange:
    """원자 전하 변화"""
    atom_idx: int           # 반응물 원자 인덱스
    reactant_charge: int    # 반응물 형식전하
    product_charge: int     # 생성물 형식전하
    delta: int              # 변화량 (product - reactant)


@dataclass
class AtomMapping:
    """반응물↔생성물 원자 대응"""
    reactant_to_product: Dict[int, int] = field(default_factory=dict)
    product_to_reactant: Dict[int, int] = field(default_factory=dict)
    unmapped_reactant: List[int] = field(default_factory=list)  # 이탈기 원자
    unmapped_product: List[int] = field(default_factory=list)   # 유입 원자


@dataclass
class BondChangeResult:
    """결합 변화 탐지 전체 결과"""
    mapping: AtomMapping
    bond_changes: List[BondChange]
    charge_changes: List[ChargeChange]
    r_mol: object = None    # RDKit Mol (반응물)
    p_mol: object = None    # RDKit Mol (생성물)


# ============================================================================
# BOND ORDER MAPPING
# ============================================================================

def _bond_type_to_order(bond_type) -> float:
    """RDKit BondType → 수치 결합차수"""
    if not RDKIT_AVAILABLE:
        return 1.0
    bt = Chem.rdchem.BondType
    mapping = {
        bt.SINGLE: 1.0,
        bt.DOUBLE: 2.0,
        bt.TRIPLE: 3.0,
        bt.AROMATIC: 1.5,
        bt.ONEANDAHALF: 1.5,
        bt.TWOANDAHALF: 2.5,
    }
    return mapping.get(bond_type, 1.0)


# ============================================================================
# MAIN CLASS
# ============================================================================

class BondChangeDetector:
    """
    반응물→생성물 사이의 결합 변화를 탐지하는 엔진.

    사용법:
        detector = BondChangeDetector()
        result = detector.detect("CBr", "CO")
        for bc in result.bond_changes:
            print(f"{bc.atom_i}-{bc.atom_j}: {bc.change_type}")
    """

    def detect(self, reactant_smiles: str, product_smiles: str) -> Optional[BondChangeResult]:
        """
        반응물/생성물 SMILES를 비교하여 결합 변화 목록 반환.

        Args:
            reactant_smiles: 반응물 SMILES (multi-fragment OK, e.g. "CBr.[OH-]")
            product_smiles: 생성물 SMILES (e.g. "CO.[Br-]")

        Returns:
            BondChangeResult or None if parsing fails
        """
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available - BondChangeDetector disabled")
            return None

        # SMILES 파싱
        r_mol = Chem.MolFromSmiles(reactant_smiles)
        p_mol = Chem.MolFromSmiles(product_smiles)
        if r_mol is None or p_mol is None:
            logger.error(f"SMILES 파싱 실패: R={reactant_smiles}, P={product_smiles}")
            return None

        # 수소 추가 (메커니즘에서 H 이동 중요)
        r_mol_h = Chem.AddHs(r_mol)
        p_mol_h = Chem.AddHs(p_mol)

        # 1단계: 원자 매핑
        mapping = self._mcs_atom_map(r_mol, p_mol)
        if mapping is None:
            mapping = self._fingerprint_atom_map(r_mol, p_mol)

        # 1.5단계: 미매핑 원자 매칭 확장 (다성분 반응 지원)
        mapping = self._extend_mapping_unmapped(r_mol, p_mol, mapping)

        # 2단계: 결합 차이 계산
        bond_changes = self._compute_bond_diff(r_mol, p_mol, mapping)

        # 3단계: 전하 변화 계산
        charge_changes = self._compute_charge_diff(r_mol, p_mol, mapping)

        return BondChangeResult(
            mapping=mapping,
            bond_changes=bond_changes,
            charge_changes=charge_changes,
            r_mol=r_mol,
            p_mol=p_mol,
        )

    # ────────────────────────────────────────────────────────────────────
    # Atom Mapping Methods
    # ────────────────────────────────────────────────────────────────────

    def _mcs_atom_map(self, r_mol, p_mol) -> Optional[AtomMapping]:
        """
        rdFMCS (Maximum Common Substructure) 기반 원자 매핑.
        가장 큰 공통 부분구조를 찾아 원자 대응을 만듦.
        """
        try:
            mcs_result = rdFMCS.FindMCS(
                [r_mol, p_mol],
                atomCompare=rdFMCS.AtomCompare.CompareElements,
                bondCompare=rdFMCS.BondCompare.CompareAny,
                matchValences=False,
                ringMatchesRingOnly=False,   # 선형→고리 변환 허용 (Diels-Alder 등)
                completeRingsOnly=False,
                timeout=5,
            )

            if mcs_result.canceled or mcs_result.numAtoms == 0:
                logger.debug("MCS 탐색 실패 또는 공통 원자 없음")
                return None

            # MCS SMARTS → 분자 객체
            mcs_mol = Chem.MolFromSmarts(mcs_result.smartsString)
            if mcs_mol is None:
                return None

            # 반응물/생성물에서 MCS 매치 찾기
            r_matches = r_mol.GetSubstructMatches(mcs_mol)
            p_matches = p_mol.GetSubstructMatches(mcs_mol)

            if not r_matches or not p_matches:
                return None

            # 첫 번째 매치 사용
            r_match = r_matches[0]
            p_match = p_matches[0]

            # 매핑 구성: MCS 인덱스를 통해 반응물→생성물
            mapping = AtomMapping()
            for mcs_idx in range(len(r_match)):
                r_idx = r_match[mcs_idx]
                p_idx = p_match[mcs_idx]
                mapping.reactant_to_product[r_idx] = p_idx
                mapping.product_to_reactant[p_idx] = r_idx

            # 매핑되지 않은 원자들
            all_r = set(range(r_mol.GetNumAtoms()))
            all_p = set(range(p_mol.GetNumAtoms()))
            mapping.unmapped_reactant = sorted(all_r - set(mapping.reactant_to_product.keys()))
            mapping.unmapped_product = sorted(all_p - set(mapping.product_to_reactant.keys()))

            # MCS가 너무 작으면 (원자의 30% 미만 매핑) fallback
            coverage = len(mapping.reactant_to_product) / max(r_mol.GetNumAtoms(), 1)
            if coverage < 0.3:
                logger.debug(f"MCS 커버리지 부족 ({coverage:.1%}), fallback 사용")
                return None

            logger.debug(
                f"MCS 매핑 완료: {len(mapping.reactant_to_product)}원자 매핑, "
                f"미매핑 R={len(mapping.unmapped_reactant)} P={len(mapping.unmapped_product)}"
            )
            return mapping

        except Exception as e:
            logger.warning(f"MCS 원자 매핑 실패: {e}")
            return None

    def _fingerprint_atom_map(self, r_mol, p_mol) -> AtomMapping:
        """
        Morgan fingerprint 유사도 기반 원자 매핑 (fallback).
        각 원자의 로컬 환경(radius=2)을 비교하여 가장 유사한 원자끼리 매핑.
        """
        mapping = AtomMapping()

        r_num = r_mol.GetNumAtoms()
        p_num = p_mol.GetNumAtoms()

        # 각 원자의 Morgan 환경 해시
        r_envs = self._atom_environments(r_mol)
        p_envs = self._atom_environments(p_mol)

        # 원소별로 그룹화하여 같은 원소끼리만 매칭
        r_by_elem: Dict[int, List[int]] = {}
        p_by_elem: Dict[int, List[int]] = {}

        for i in range(r_num):
            elem = r_mol.GetAtomWithIdx(i).GetAtomicNum()
            r_by_elem.setdefault(elem, []).append(i)
        for j in range(p_num):
            elem = p_mol.GetAtomWithIdx(j).GetAtomicNum()
            p_by_elem.setdefault(elem, []).append(j)

        used_p: Set[int] = set()

        for elem in r_by_elem:
            if elem not in p_by_elem:
                continue

            r_atoms = r_by_elem[elem]
            p_atoms = [a for a in p_by_elem[elem] if a not in used_p]

            # 각 (r, p) 쌍의 유사도 계산
            pairs = []
            for ri in r_atoms:
                for pj in p_atoms:
                    sim = self._env_similarity(r_envs[ri], p_envs[pj])
                    pairs.append((sim, ri, pj))

            # 유사도 높은 순으로 greedy 매칭
            pairs.sort(key=lambda x: -x[0])
            used_r: Set[int] = set()

            for sim, ri, pj in pairs:
                if ri in used_r or pj in used_p:
                    continue
                if sim < 0.1:  # 최소 유사도 임계값
                    continue
                mapping.reactant_to_product[ri] = pj
                mapping.product_to_reactant[pj] = ri
                used_r.add(ri)
                used_p.add(pj)

        # 미매핑 원자
        mapping.unmapped_reactant = sorted(set(range(r_num)) - set(mapping.reactant_to_product.keys()))
        mapping.unmapped_product = sorted(set(range(p_num)) - set(mapping.product_to_reactant.keys()))

        logger.debug(
            f"Fingerprint 매핑 완료: {len(mapping.reactant_to_product)}원자, "
            f"미매핑 R={len(mapping.unmapped_reactant)} P={len(mapping.unmapped_product)}"
        )
        return mapping

    def _atom_environments(self, mol) -> Dict[int, Set[int]]:
        """각 원자의 Morgan 환경 비트셋 (radius=2)"""
        info = {}
        AllChem.GetMorganFingerprint(mol, radius=2, bitInfo=info)

        env_by_atom: Dict[int, Set[int]] = {i: set() for i in range(mol.GetNumAtoms())}
        for bit_id, atom_rad_list in info.items():
            for atom_idx, radius in atom_rad_list:
                env_by_atom[atom_idx].add(bit_id)

        return env_by_atom

    def _env_similarity(self, env_a: Set[int], env_b: Set[int]) -> float:
        """두 원자 환경의 Tanimoto 유사도"""
        if not env_a and not env_b:
            return 1.0
        if not env_a or not env_b:
            return 0.0
        intersection = len(env_a & env_b)
        union = len(env_a | env_b)
        return intersection / union if union > 0 else 0.0

    # ────────────────────────────────────────────────────────────────────
    # Unmapped Atom Extension (for multi-fragment reactions)
    # ────────────────────────────────────────────────────────────────────

    def _extend_mapping_unmapped(self, r_mol, p_mol, mapping: AtomMapping) -> AtomMapping:
        """
        미매핑 원자끼리 원소 타입과 연결성 기반으로 매칭 확장.

        다성분 반응(Diels-Alder 등)에서 MCS가 한 fragment만 매핑했을 때,
        남은 fragment 원자들을 product의 미매핑 원자와 연결하여 완전한 매핑 구축.

        예: butadiene(4C)+ethylene(2C)→cyclohexene(6C)
            MCS maps 4C, 이 메서드가 나머지 2C도 매핑
        """
        if not mapping.unmapped_reactant or not mapping.unmapped_product:
            return mapping  # 미매핑 없으면 그대로

        # 원소별로 미매핑 원자 그룹화
        r_by_elem: Dict[int, List[int]] = {}
        p_by_elem: Dict[int, List[int]] = {}

        for ri in mapping.unmapped_reactant:
            elem = r_mol.GetAtomWithIdx(ri).GetAtomicNum()
            r_by_elem.setdefault(elem, []).append(ri)

        for pi in mapping.unmapped_product:
            elem = p_mol.GetAtomWithIdx(pi).GetAtomicNum()
            p_by_elem.setdefault(elem, []).append(pi)

        # 같은 원소끼리 매칭 (연결성 유사도 기반)
        new_r2p = dict(mapping.reactant_to_product)
        new_p2r = dict(mapping.product_to_reactant)
        matched_r: Set[int] = set()
        matched_p: Set[int] = set()

        for elem in r_by_elem:
            if elem not in p_by_elem:
                continue

            r_atoms = r_by_elem[elem]
            p_atoms = p_by_elem[elem]

            if len(r_atoms) != len(p_atoms):
                continue  # 개수 불일치 → 안전하게 skip

            # 연결성 기반 매칭 점수 계산
            # 이미 매핑된 이웃이 있으면 가산점
            pairs = []
            for ri in r_atoms:
                for pi in p_atoms:
                    score = self._unmapped_match_score(
                        r_mol, p_mol, ri, pi, new_r2p, new_p2r
                    )
                    pairs.append((score, ri, pi))

            # 점수 높은 순으로 greedy 매칭
            pairs.sort(key=lambda x: -x[0])

            for score, ri, pi in pairs:
                if ri in matched_r or pi in matched_p:
                    continue
                new_r2p[ri] = pi
                new_p2r[pi] = ri
                matched_r.add(ri)
                matched_p.add(pi)

        if matched_r:
            new_mapping = AtomMapping(
                reactant_to_product=new_r2p,
                product_to_reactant=new_p2r,
                unmapped_reactant=sorted(
                    set(mapping.unmapped_reactant) - matched_r
                ),
                unmapped_product=sorted(
                    set(mapping.unmapped_product) - matched_p
                ),
            )
            logger.debug(
                f"미매핑 원자 {len(matched_r)}개 추가 매핑 → "
                f"남은 미매핑 R={len(new_mapping.unmapped_reactant)} "
                f"P={len(new_mapping.unmapped_product)}"
            )
            return new_mapping

        return mapping

    def _unmapped_match_score(self, r_mol, p_mol,
                               r_idx: int, p_idx: int,
                               r2p: Dict[int, int],
                               p2r: Dict[int, int]) -> float:
        """
        미매핑 원자 (r_idx, p_idx) 쌍의 매칭 점수 계산.
        이미 매핑된 이웃과의 연결 일관성을 평가.
        """
        score = 0.0

        # 반응물 원자의 이웃 중 이미 매핑된 것 확인
        r_atom = r_mol.GetAtomWithIdx(r_idx)
        p_atom = p_mol.GetAtomWithIdx(p_idx)

        for r_neighbor in r_atom.GetNeighbors():
            rn_idx = r_neighbor.GetIdx()
            pn_mapped = r2p.get(rn_idx)
            if pn_mapped is not None:
                # 생성물에서 p_idx와 pn_mapped가 결합되어 있으면 보너스
                p_bond = p_mol.GetBondBetweenAtoms(p_idx, pn_mapped)
                if p_bond is not None:
                    score += 10.0  # 연결 일관성 높음

        # 생성물 원자의 이웃 중 이미 매핑된 것 확인
        for p_neighbor in p_atom.GetNeighbors():
            pn_idx = p_neighbor.GetIdx()
            rn_mapped = p2r.get(pn_idx)
            if rn_mapped is not None:
                r_bond = r_mol.GetBondBetweenAtoms(r_idx, rn_mapped)
                if r_bond is not None:
                    score += 10.0

        # 차수 유사도 보너스
        r_degree = r_atom.GetDegree()
        p_degree = p_atom.GetDegree()
        score += max(0, 5.0 - abs(r_degree - p_degree))

        return score

    # ────────────────────────────────────────────────────────────────────
    # Bond Diff Computation
    # ────────────────────────────────────────────────────────────────────

    def _compute_bond_diff(self, r_mol, p_mol, mapping: AtomMapping) -> List[BondChange]:
        """
        반응물/생성물의 결합 차이를 계산.
        매핑된 원자 쌍 기준 + unmapped 원자와 mapped 원자 사이 결합도 포함.
        """
        changes: List[BondChange] = []

        # 반응물 결합 세트: (r_i, r_j) -> order
        r_bonds: Dict[Tuple[int, int], float] = {}
        for bond in r_mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            order = _bond_type_to_order(bond.GetBondType())
            key = (min(i, j), max(i, j))
            r_bonds[key] = order

        # 생성물 결합 세트 (반응물 인덱스로 변환)
        p_bonds_mapped: Dict[Tuple[int, int], float] = {}
        for bond in p_mol.GetBonds():
            pi, pj = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            order = _bond_type_to_order(bond.GetBondType())

            ri = mapping.product_to_reactant.get(pi)
            rj = mapping.product_to_reactant.get(pj)

            if ri is not None and rj is not None:
                key = (min(ri, rj), max(ri, rj))
                p_bonds_mapped[key] = order

        # 매핑된 원자 간 결합 비교
        all_bond_keys = set(r_bonds.keys()) | set(p_bonds_mapped.keys())

        for key in all_bond_keys:
            r_order = r_bonds.get(key, 0.0)
            p_order = p_bonds_mapped.get(key, 0.0)

            if abs(r_order - p_order) < 0.01:
                continue

            if r_order > 0 and p_order == 0:
                change_type = "broken"
            elif r_order == 0 and p_order > 0:
                change_type = "formed"
            elif p_order > r_order:
                change_type = "order_increase"
            else:
                change_type = "order_decrease"

            changes.append(BondChange(
                atom_i=key[0],
                atom_j=key[1],
                reactant_order=r_order,
                product_order=p_order,
                change_type=change_type,
            ))

        # ─── unmapped 원자와 mapped 원자 사이 결합 감지 ───
        # 생성물에만 있는 원자(유입)가 매핑된 원자와 결합 → "formed"
        unmapped_p_set = set(mapping.unmapped_product)
        for bond in p_mol.GetBonds():
            pi, pj = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            order = _bond_type_to_order(bond.GetBondType())

            # 한쪽이 unmapped, 다른 쪽이 mapped
            if pi in unmapped_p_set and pj not in unmapped_p_set:
                ri = mapping.product_to_reactant.get(pj)
                if ri is not None:
                    changes.append(BondChange(
                        atom_i=ri, atom_j=-1,  # -1 = external (유입 원자)
                        reactant_order=0.0, product_order=order,
                        change_type="formed",
                    ))
            elif pj in unmapped_p_set and pi not in unmapped_p_set:
                ri = mapping.product_to_reactant.get(pi)
                if ri is not None:
                    changes.append(BondChange(
                        atom_i=ri, atom_j=-1,
                        reactant_order=0.0, product_order=order,
                        change_type="formed",
                    ))

        # 반응물에만 있는 원자(이탈)가 매핑된 원자와 결합 → "broken"
        unmapped_r_set = set(mapping.unmapped_reactant)
        for bond in r_mol.GetBonds():
            ri, rj = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            order = _bond_type_to_order(bond.GetBondType())

            if ri in unmapped_r_set and rj not in unmapped_r_set:
                changes.append(BondChange(
                    atom_i=rj, atom_j=-1,
                    reactant_order=order, product_order=0.0,
                    change_type="broken",
                ))
            elif rj in unmapped_r_set and ri not in unmapped_r_set:
                changes.append(BondChange(
                    atom_i=ri, atom_j=-1,
                    reactant_order=order, product_order=0.0,
                    change_type="broken",
                ))

        logger.debug(f"결합 변화 {len(changes)}개 감지: " +
                     ", ".join(f"{c.atom_i}-{c.atom_j}({c.change_type})" for c in changes))
        return changes

    # ────────────────────────────────────────────────────────────────────
    # Charge Diff
    # ────────────────────────────────────────────────────────────────────

    def _compute_charge_diff(self, r_mol, p_mol, mapping: AtomMapping) -> List[ChargeChange]:
        """매핑된 원자들의 형식전하 변화 계산"""
        changes: List[ChargeChange] = []

        for r_idx, p_idx in mapping.reactant_to_product.items():
            r_charge = r_mol.GetAtomWithIdx(r_idx).GetFormalCharge()
            p_charge = p_mol.GetAtomWithIdx(p_idx).GetFormalCharge()

            if r_charge != p_charge:
                changes.append(ChargeChange(
                    atom_idx=r_idx,
                    reactant_charge=r_charge,
                    product_charge=p_charge,
                    delta=p_charge - r_charge,
                ))

        return changes

    # ────────────────────────────────────────────────────────────────────
    # Utility
    # ────────────────────────────────────────────────────────────────────

    def get_leaving_atoms(self, result: BondChangeResult) -> List[int]:
        """이탈기 원자 인덱스 (반응물 기준)"""
        return result.mapping.unmapped_reactant

    def get_incoming_atoms(self, result: BondChangeResult) -> List[int]:
        """유입 원자 인덱스 (생성물 기준)"""
        return result.mapping.unmapped_product

    def get_reaction_center(self, result: BondChangeResult) -> Set[int]:
        """반응 중심 원자 인덱스 (반응물 기준) - 결합 변화에 관여하는 원자들"""
        center: Set[int] = set()
        for bc in result.bond_changes:
            center.add(bc.atom_i)
            center.add(bc.atom_j)
        for cc in result.charge_changes:
            center.add(cc.atom_idx)
        return center
