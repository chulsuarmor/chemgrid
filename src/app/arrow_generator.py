# arrow_generator.py (v2.0 - Electron Flow Arrow Generator — Textbook Quality)
"""
ChemGrid: 결합 변화 + 전자 구조 데이터 → ArrowData 자동 생성
- Gasteiger 부분전하 기반 전자 흐름 방향 결정
- ORCA Mulliken 전하 옵션 (Tier 1)
- HMO 전자밀도 보조 (방향족계)
- 페리고리/라디칼 감지
- v2.0: 적응형 곡률(adaptive curvature), pi/sigma 결합 세분류,
#        향상된 전자 흐름 방향 결정 (formal charge + partial charge + EN)
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from bond_change_detector import BondChange, BondChangeResult, AtomMapping, ChargeChange

# 기존 ArrowData import
from reaction_mechanisms import ArrowData


# ============================================================================
# ELECTRONEGATIVITY TABLE (Pauling scale)
# ============================================================================

ELECTRONEGATIVITY = {
    1: 2.20,   # H
    5: 2.04,   # B
    6: 2.55,   # C
    7: 3.04,   # N
    8: 3.44,   # O
    9: 3.98,   # F
    14: 1.90,  # Si
    15: 2.19,  # P
    16: 2.58,  # S
    17: 3.16,  # Cl
    35: 2.96,  # Br
    53: 2.66,  # I
}

# 색상 팔레트 (전자 흐름 화살표)
ARROW_COLORS = [
    "#E53935",  # 빨강 (기본)
    "#1E88E5",  # 파랑
    "#43A047",  # 초록
    "#FB8C00",  # 주황
    "#8E24AA",  # 보라
    "#00ACC1",  # 청록
]


# ============================================================================
# MAIN CLASS
# ============================================================================

class ArrowGenerator:
    """
    결합 변화 + 전자 구조 데이터로부터 ArrowData 목록을 생성.

    사용법:
        gen = ArrowGenerator()
        arrows = gen.generate(bond_change_result)
    """

    def __init__(self, orca_available: bool = False):
        self._orca_available = orca_available

    def generate(self, result: BondChangeResult) -> List[ArrowData]:
        """
        BondChangeResult로부터 전자 흐름 화살표 생성.

        Returns:
            List[ArrowData] - CurvedArrowRenderer와 호환되는 화살표 목록
        """
        if not RDKIT_AVAILABLE or result is None:
            return []

        r_mol = result.r_mol
        p_mol = result.p_mol
        bond_changes = result.bond_changes
        charge_changes = result.charge_changes
        mapping = result.mapping

        if not bond_changes and not mapping.unmapped_reactant and not mapping.unmapped_product:
            logger.debug("결합 변화 및 원자 변화 없음 - 화살표 없음")
            return []

        # 1. 부분전하 계산
        charges = self._get_partial_charges(r_mol)

        # 2. 페리고리 반응 감지
        if self._detect_pericyclic(bond_changes, r_mol):
            return self._generate_pericyclic_arrows(bond_changes, r_mol, charges)

        # 3. 라디칼 반응 감지
        if self._detect_radical(result):
            return self._generate_radical_arrows(bond_changes, r_mol, charges)

        # 4. 일반 이온성/극성 메커니즘
        arrows = self._generate_polar_arrows(bond_changes, charge_changes, mapping,
                                              r_mol, p_mol, charges)

        # 5. 전자 흐름 체인 정렬
        arrows = self._resolve_electron_chain(arrows, r_mol, charges)

        # 6. 색상 할당
        arrows = self._assign_colors(arrows)

        return arrows

    # ────────────────────────────────────────────────────────────────────
    # Partial Charges
    # ────────────────────────────────────────────────────────────────────

    def _get_partial_charges(self, mol) -> Dict[int, float]:
        """
        부분전하 계산.
        Tier 1: ORCA Mulliken (설치 시 자동 사용, 캐시)
        Tier 2: Gasteiger (기본, 항상 사용 가능)
        Tier 3: 전기음성도 기반 추정 (fallback)
        """
        charges: Dict[int, float] = {}

        # Tier 1: ORCA Mulliken 전하 (설치된 경우)
        if self._orca_available:
            orca_charges = self._try_orca_charges(mol)
            if orca_charges:
                logger.info(f"ORCA Mulliken 전하 사용 (Tier 1, {len(orca_charges)}원자)")
                return orca_charges

        # Tier 2: Gasteiger 전하
        try:
            mol_copy = Chem.RWMol(mol)
            AllChem.ComputeGasteigerCharges(mol_copy, nIter=25)

            for i in range(mol_copy.GetNumAtoms()):
                charge = float(mol_copy.GetAtomWithIdx(i).GetDoubleProp('_GasteigerCharge'))
                if math.isnan(charge) or math.isinf(charge):
                    charge = self._estimate_charge_from_en(mol, i)
                charges[i] = charge

        except Exception as e:
            logger.warning(f"Gasteiger charge 계산 실패: {e}, 전기음성도 fallback")
            for i in range(mol.GetNumAtoms()):
                charges[i] = self._estimate_charge_from_en(mol, i)

        return charges

    def _try_orca_charges(self, mol) -> Optional[Dict[int, float]]:
        """ORCA single-point 계산으로 Mulliken 전하 획득"""
        try:
            from orca_interface import (
                find_orca_executable, OrcaExecutor, OrcaOutputParser,
                generate_orca_input
            )

            orca_path = find_orca_executable()
            if not orca_path:
                return None

            # SMILES → 3D 좌표 생성
            smiles = Chem.MolToSmiles(mol)
            mol_3d = Chem.AddHs(mol)
            res = AllChem.EmbedMolecule(mol_3d, randomSeed=42)
            if res != 0:
                return None
            AllChem.MMFFOptimizeMolecule(mol_3d, maxIters=200)

            # ORCA 입력 생성 + 실행
            import tempfile, os
            with tempfile.TemporaryDirectory() as tmpdir:
                inp_file = os.path.join(tmpdir, "charge_calc.inp")
                inp_content = generate_orca_input(mol_3d, method="B3LYP",
                                                   basis="6-31G(d)",
                                                   job_type="SP")
                with open(inp_file, "w") as f:
                    f.write(inp_content)

                executor = OrcaExecutor(str(orca_path))
                out_file = executor.run(inp_file, timeout=120)

                if out_file and os.path.exists(out_file):
                    parser = OrcaOutputParser()
                    result = parser.parse(out_file)
                    if result.converged and result.charges_mulliken:
                        # 수소 제외, 중원자만 반환 (mol 인덱스 기준)
                        heavy_charges: Dict[int, float] = {}
                        heavy_idx = 0
                        for i in range(mol_3d.GetNumAtoms()):
                            atom = mol_3d.GetAtomWithIdx(i)
                            if atom.GetAtomicNum() > 1:
                                if i in result.charges_mulliken:
                                    heavy_charges[heavy_idx] = result.charges_mulliken[i]
                                heavy_idx += 1
                        if heavy_charges:
                            return heavy_charges

        except Exception as e:
            logger.debug(f"ORCA 전하 계산 실패: {e}")

        return None

    def _estimate_charge_from_en(self, mol, atom_idx: int) -> float:
        """전기음성도 기반 부분전하 추정 (Tier 3 fallback)"""
        atom = mol.GetAtomWithIdx(atom_idx)
        en_self = ELECTRONEGATIVITY.get(atom.GetAtomicNum(), 2.5)

        # 이웃 원자들의 전기음성도와 비교
        neighbor_ens = []
        for neighbor in atom.GetNeighbors():
            neighbor_ens.append(ELECTRONEGATIVITY.get(neighbor.GetAtomicNum(), 2.5))

        if not neighbor_ens:
            return 0.0

        avg_neighbor_en = sum(neighbor_ens) / len(neighbor_ens)
        # 양수 = 이웃보다 전기음성도 낮음 = 부분 양전하
        return (avg_neighbor_en - en_self) * 0.2

    # ────────────────────────────────────────────────────────────────────
    # Reaction Type Detection
    # ────────────────────────────────────────────────────────────────────

    def _detect_pericyclic(self, bond_changes: List[BondChange], mol) -> bool:
        """
        페리고리 반응 감지: 결합 변화가 순환 고리를 형성하는지.

        두 가지 패턴 감지:
        1. 직접 순환: 모든 결합 변화 원자가 정확히 2개의 변화에 참여
        2. 간접 순환 (Diels-Alder 등): 결합 변화 원자들이 분자 내 기존 결합으로
           연결되어 순환 경로를 형성. 변하지 않는 결합이 중간에 있어도 감지.
        """
        if len(bond_changes) < 3:
            return False

        # 외부 원자(-1) 제외
        valid_changes = [bc for bc in bond_changes
                         if bc.atom_i >= 0 and bc.atom_j >= 0]
        if len(valid_changes) < 3:
            return False

        # ─── 패턴 1: 직접 순환 ───
        change_atoms: Set[int] = set()
        adj: Dict[int, Set[int]] = {}
        for bc in valid_changes:
            change_atoms.add(bc.atom_i)
            change_atoms.add(bc.atom_j)
            adj.setdefault(bc.atom_i, set()).add(bc.atom_j)
            adj.setdefault(bc.atom_j, set()).add(bc.atom_i)

        if all(len(adj.get(a, set())) == 2 for a in change_atoms):
            logger.debug(f"페리고리 반응 감지 (직접 순환): {len(change_atoms)}원자")
            return True

        # ─── 패턴 2: 간접 순환 (Diels-Alder 등) ───
        # 결합 변화 원자 중 degree-1인 원자들이 분자 내 기존 결합으로 연결 가능한지 확인
        # 예: [4]=[3] 변화 atoms에서 atom 1,3이 degree-1
        #     하지만 분자 내에서 1-2-3 경로로 연결됨 → 순환 완성
        degree_one = [a for a in change_atoms if len(adj.get(a, set())) == 1]

        if len(degree_one) == 2:
            # degree-1 원자 2개가 분자 내 기존 결합으로 연결되면 순환
            a, b = degree_one
            # BFS로 분자 내 경로 탐색 (결합 변화에 포함되지 않은 결합만 사용)
            path = self._find_molecular_path(mol, a, b, change_atoms - {a, b})
            if path is not None and len(path) <= 4:  # 짧은 경로만 허용
                total_atoms = len(change_atoms) + len(path) - 2  # 양 끝 제외
                if total_atoms >= 4:
                    logger.debug(
                        f"페리고리 반응 감지 (간접 순환): "
                        f"{total_atoms}원자, 경로길이={len(path)}"
                    )
                    return True

        return False

    def _find_molecular_path(self, mol, start: int, end: int,
                              exclude: Set[int]) -> Optional[List[int]]:
        """
        분자 내에서 start→end 최단 경로 탐색 (BFS).
        exclude 집합의 원자는 중간 경유지로 사용 불가 (결합 변화에 관여하는 원자).
        """
        if mol is None:
            return None

        from collections import deque
        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            current, path = queue.popleft()
            if current == end:
                return path

            if len(path) > 5:  # 경로 길이 제한
                continue

            atom = mol.GetAtomWithIdx(current)
            for neighbor in atom.GetNeighbors():
                n_idx = neighbor.GetIdx()
                if n_idx in visited:
                    continue
                if n_idx == end:
                    return path + [n_idx]
                if n_idx not in exclude:
                    visited.add(n_idx)
                    queue.append((n_idx, path + [n_idx]))

        return None

    def _detect_radical(self, result: BondChangeResult) -> bool:
        """
        라디칼 반응 감지: 홀수 전자 변화 또는 동종분해.
        조건: 결합 끊김만 있고 생성 없으며, 매핑되지 않은 원자도 없는 경우
        (유입/이탈 원자가 있으면 치환 반응이지 라디칼이 아님)
        """
        if not result.charge_changes and result.bond_changes:
            broken = [bc for bc in result.bond_changes if bc.is_broken]
            formed = [bc for bc in result.bond_changes if bc.is_formed]
            has_unmapped = (result.mapping.unmapped_reactant or
                           result.mapping.unmapped_product)
            # 결합 끊김만 있고 생성 없으며, 유입/이탈 원자도 없으면 → 동종분해
            if broken and not formed and not has_unmapped:
                return True
        return False

    # ────────────────────────────────────────────────────────────────────
    # Arrow Generation: Polar (Ionic) Mechanism
    # ────────────────────────────────────────────────────────────────────

    def _generate_polar_arrows(self, bond_changes: List[BondChange],
                                charge_changes: List[ChargeChange],
                                mapping: AtomMapping,
                                r_mol, p_mol,
                                charges: Dict[int, float]) -> List[ArrowData]:
        """
        일반 극성(이온성) 메커니즘 화살표 생성.
        핵심: 전자는 전기음성도 높은/음전하 원자 → 양전하 원자로 이동
        """
        arrows: List[ArrowData] = []

        # 전하 변화 맵
        charge_delta: Dict[int, int] = {}
        for cc in charge_changes:
            charge_delta[cc.atom_idx] = cc.delta

        # ─── 결합 끊김 처리 ───
        for bc in bond_changes:
            if bc.change_type in ("broken", "order_decrease"):
                arrow = self._arrow_for_bond_break(bc, charges, charge_delta, r_mol)
                if arrow:
                    arrows.append(arrow)

        # ─── 결합 생성 처리 ───
        for bc in bond_changes:
            if bc.change_type in ("formed", "order_increase"):
                arrow = self._arrow_for_bond_form(bc, charges, charge_delta,
                                                   r_mol, p_mol, mapping)
                if arrow:
                    arrows.append(arrow)

        # ─── 유입/이탈 원자 처리 (unmapped) ───
        # 이탈기: 반응물에만 있는 원자 → 결합 끊김 화살표 (이미 처리될 수 있음)
        # 유입 원자: 생성물에만 있는 원자 → 새 결합 형성 화살표
        if mapping.unmapped_product and p_mol:
            for p_idx in mapping.unmapped_product:
                # 생성물에서 이 원자의 이웃 중 매핑된 원자 찾기
                p_atom = p_mol.GetAtomWithIdx(p_idx)
                for neighbor in p_atom.GetNeighbors():
                    n_pidx = neighbor.GetIdx()
                    r_idx = mapping.product_to_reactant.get(n_pidx)
                    if r_idx is not None:
                        # 유입 원자(external) → 매핑된 원자로의 결합 형성
                        r_atom = r_mol.GetAtomWithIdx(r_idx)
                        incoming_sym = p_atom.GetSymbol()
                        target_sym = r_atom.GetSymbol()

                        # 화살표: 유입 원자(외부) → 반응물 원자
                        arrows.append(ArrowData(
                            arrow_type="full",
                            from_type="lone_pair",
                            from_label=f"{incoming_sym} (유입)",
                            to_type="atom",
                            to_label=f"{target_sym} (반응 중심)",
                            from_atom_idx=-1,  # external
                            to_atom_idx=r_idx,
                            curvature=0.45,  # [v2.0] 외부→내부: 넓은 아치
                            color="#1E88E5",
                        ))
                        break  # 첫 이웃만

        return arrows

    def _arrow_for_bond_break(self, bc: BondChange, charges: Dict[int, float],
                               charge_delta: Dict[int, int], mol) -> Optional[ArrowData]:
        """
        결합 끊김 → 화살표 생성.
        이종분해: 전자쌍이 더 전기음성인 원자로 이동.
        """
        # atom_j == -1 이면 이탈기(unmapped) 관련 결합 끊김
        if bc.atom_j == -1:
            atom_i = mol.GetAtomWithIdx(bc.atom_i)
            sym_i = atom_i.GetSymbol()
            from_type = "sigma_bond" if bc.reactant_order <= 1.5 else "pi_bond"
            return ArrowData(
                arrow_type="full",
                from_type=from_type,
                from_label=f"{sym_i}-LG \u03c3결합",
                to_type="atom",
                to_label=f"이탈기 (전자쌍 수용)",
                from_atom_idx=bc.atom_i,
                to_atom_idx=-1,  # external (이탈기)
                curvature=0.45,  # [v2.0] 이탈기: 넓은 아치
            )

        if bc.atom_i < 0 or bc.atom_j < 0:
            return None
        if bc.atom_i >= mol.GetNumAtoms() or bc.atom_j >= mol.GetNumAtoms():
            return None

        atom_i = mol.GetAtomWithIdx(bc.atom_i)
        atom_j = mol.GetAtomWithIdx(bc.atom_j)

        en_i = ELECTRONEGATIVITY.get(atom_i.GetAtomicNum(), 2.5)
        en_j = ELECTRONEGATIVITY.get(atom_j.GetAtomicNum(), 2.5)

        delta_i = charge_delta.get(bc.atom_i, 0)
        delta_j = charge_delta.get(bc.atom_j, 0)

        if delta_i < delta_j:
            from_idx, to_idx = bc.atom_j, bc.atom_i
            from_label = f"{atom_j.GetSymbol()}-{atom_i.GetSymbol()} σ결합"
            to_label = f"{atom_i.GetSymbol()} (전자쌍 수용)"
        elif delta_j < delta_i:
            from_idx, to_idx = bc.atom_i, bc.atom_j
            from_label = f"{atom_i.GetSymbol()}-{atom_j.GetSymbol()} σ결합"
            to_label = f"{atom_j.GetSymbol()} (전자쌍 수용)"
        elif en_j >= en_i:
            from_idx, to_idx = bc.atom_i, bc.atom_j
            from_label = f"{atom_i.GetSymbol()}-{atom_j.GetSymbol()} σ결합"
            to_label = f"{atom_j.GetSymbol()} (전자쌍 수용)"
        else:
            from_idx, to_idx = bc.atom_j, bc.atom_i
            from_label = f"{atom_j.GetSymbol()}-{atom_i.GetSymbol()} σ결합"
            to_label = f"{atom_i.GetSymbol()} (전자쌍 수용)"

        # [v2.0] 세분류된 결합 소스 유형 + 적응형 곡률
        from_type = self._classify_bond_source(mol, bc.atom_i, bc.atom_j)
        curvature = self._adaptive_curvature(mol, from_idx, to_idx, "polar")

        return ArrowData(
            arrow_type="full",
            from_type=from_type,
            from_label=from_label,
            to_type="atom",
            to_label=to_label,
            from_atom_idx=from_idx,
            to_atom_idx=to_idx,
            curvature=curvature,
        )

    def _arrow_for_bond_form(self, bc: BondChange, charges: Dict[int, float],
                              charge_delta: Dict[int, int],
                              r_mol, p_mol, mapping: AtomMapping) -> Optional[ArrowData]:
        """
        결합 생성 → 화살표 생성.
        친핵 공격: 전자 제공 원자(Nu) → 전자 수용 원자(E).
        """
        # atom_j == -1 이면 유입 원자(unmapped)와의 결합 형성
        # → 이미 _generate_polar_arrows 의 unmapped 처리에서 다루므로 skip
        if bc.atom_j == -1 or bc.atom_i == -1:
            return None

        # 결합 생성의 경우 from_atom_idx와 to_atom_idx가 반응물 기준
        atom_i = r_mol.GetAtomWithIdx(bc.atom_i) if bc.atom_i < r_mol.GetNumAtoms() else None
        atom_j = r_mol.GetAtomWithIdx(bc.atom_j) if bc.atom_j < r_mol.GetNumAtoms() else None

        if atom_i is None or atom_j is None:
            return None

        # 전자 제공자(Nu) 결정: 더 음전하/전기음성 원자가 전자 제공
        charge_i = charges.get(bc.atom_i, 0.0)
        charge_j = charges.get(bc.atom_j, 0.0)
        en_i = ELECTRONEGATIVITY.get(atom_i.GetAtomicNum(), 2.5)
        en_j = ELECTRONEGATIVITY.get(atom_j.GetAtomicNum(), 2.5)

        # 형식전하 우선
        fc_i = atom_i.GetFormalCharge()
        fc_j = atom_j.GetFormalCharge()

        # 비공유전자쌍 확인
        lp_i = self._has_lone_pair(atom_i)
        lp_j = self._has_lone_pair(atom_j)

        # Nu 결정 점수 (낮을수록 Nu)
        score_i = charge_i + fc_i * 0.5 - (0.3 if lp_i else 0)
        score_j = charge_j + fc_j * 0.5 - (0.3 if lp_j else 0)

        if score_i <= score_j:
            # i가 Nu (전자 제공)
            from_idx, to_idx = bc.atom_i, bc.atom_j
            from_sym, to_sym = atom_i.GetSymbol(), atom_j.GetSymbol()
            from_type = "lone_pair" if lp_i else "negative_charge"
        else:
            from_idx, to_idx = bc.atom_j, bc.atom_i
            from_sym, to_sym = atom_j.GetSymbol(), atom_i.GetSymbol()
            from_type = "lone_pair" if lp_j else "negative_charge"

        # [v2.0] 적응형 곡률
        curvature = self._adaptive_curvature(r_mol, from_idx, to_idx, "polar")

        return ArrowData(
            arrow_type="full",
            from_type=from_type,
            from_label=f"{from_sym} 비공유전자쌍" if from_type == "lone_pair"
                        else f"{from_sym} 음전하",
            to_type="atom",
            to_label=f"{to_sym} (친전자 중심)",
            from_atom_idx=from_idx,
            to_atom_idx=to_idx,
            curvature=curvature,
        )

    def _has_lone_pair(self, atom) -> bool:
        """원자에 비공유전자쌍이 있는지 확인"""
        # 간단한 규칙: N, O, S, F, Cl, Br, I 등 비금속에 비공유전자쌍
        lp_atoms = {7, 8, 9, 15, 16, 17, 34, 35, 53}
        return atom.GetAtomicNum() in lp_atoms

    # ────────────────────────────────────────────────────────────────────
    # [v2.0] Adaptive Curvature — 교과서 품질 곡선 계산
    # ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _adaptive_curvature(mol, from_idx: int, to_idx: int,
                            mechanism: str = "polar") -> float:
        """
        원자 간 거리와 메커니즘 유형에 따른 적응형 곡률 계산.

        교과서 곡선 화살표 규칙:
        - 인접 원자 (결합 1개 거리): 큰 곡률 (0.5~0.7) → 넓은 아치
        - 원거리 원자 (결합 2~3개): 작은 곡률 (0.25~0.4) → 완만한 곡선
        - 페리고리: 일정한 곡률 (0.3) → 순환 전자 흐름 표현
        - 라디칼 (fishhook): 약간 작은 곡률 (0.25) → 얇은 곡선

        Returns:
            float: 곡률 값 (양수=위로 볼록, 부호는 호출자가 결정)
        """
        if from_idx < 0 or to_idx < 0:
            return 0.4  # 외부 원자 → 기본값

        if mol is None:
            return 0.35

        # 그래프 거리 계산 (BFS)
        graph_dist = _graph_distance(mol, from_idx, to_idx)

        if mechanism == "pericyclic":
            return 0.30  # 페리고리: 균일한 순환 곡선
        elif mechanism == "radical":
            return 0.25  # 라디칼 fishhook: 가벼운 곡선

        # 극성 메커니즘: 거리에 반비례하는 곡률
        if graph_dist <= 1:
            return 0.55  # 인접: 결합 위를 크게 휘어 넘기는 아치
        elif graph_dist == 2:
            return 0.40  # 1,3-관계: 중간 곡선
        elif graph_dist == 3:
            return 0.30  # 1,4-관계: 완만한 곡선
        else:
            return 0.25  # 먼 거리: 최소 곡률

    @staticmethod
    def _classify_bond_source(mol, atom_i: int, atom_j: int) -> str:
        """
        결합 소스 유형을 세분류 (교과서 화살표 시작점 표현용).

        Returns:
            "sigma_bond": σ 결합 (단일 결합)
            "pi_bond": π 결합 (이중/삼중 결합의 π 성분)
            "aromatic_pi": 방향족 π 전자
        """
        if mol is None or atom_i < 0 or atom_j < 0:
            return "bond"
        if atom_i >= mol.GetNumAtoms() or atom_j >= mol.GetNumAtoms():
            return "bond"

        bond = mol.GetBondBetweenAtoms(atom_i, atom_j)
        if bond is None:
            return "bond"

        bt = bond.GetBondType()
        if bt == Chem.rdchem.BondType.AROMATIC:
            return "aromatic_pi"
        order = _bond_type_to_order(bt)
        if order >= 2.0:
            return "pi_bond"
        return "sigma_bond"

    # ────────────────────────────────────────────────────────────────────
    # Arrow Generation: Pericyclic
    # ────────────────────────────────────────────────────────────────────

    def _generate_pericyclic_arrows(self, bond_changes: List[BondChange],
                                     mol, charges: Dict[int, float]) -> List[ArrowData]:
        """
        페리고리 반응 화살표 생성 (순환 전자 흐름).
        예: Diels-Alder → 3개 화살표 (3쌍의 전자가 순환 이동)
        """
        arrows: List[ArrowData] = []
        valid_changes = [bc for bc in bond_changes
                         if bc.atom_i >= 0 and bc.atom_j >= 0]

        # 결합 변화 원자들을 순환 순서로 정렬 (직접 순환)
        chain = self._order_cyclic_atoms(valid_changes)

        if not chain:
            # 간접 순환: 분자 경로를 통해 완전한 순환 구성
            chain = self._build_pericyclic_chain(valid_changes, mol)

        if not chain:
            # 순환 정렬 실패 → 일반 처리 fallback
            return self._generate_polar_arrows(
                bond_changes, [], AtomMapping(), mol, mol, charges
            )

        # 순환 화살표: π결합 → 새 σ결합 형성 (쌍으로)
        # Diels-Alder: 3개 화살표 (π→σ, π→σ, π→σ)
        n = len(chain)
        for idx in range(0, n, 2):
            from_idx = chain[idx]
            to_idx = chain[(idx + 1) % n]
            next_to = chain[(idx + 2) % n]
            color_idx = (idx // 2) % len(ARROW_COLORS)

            atom_from = mol.GetAtomWithIdx(from_idx)
            atom_to = mol.GetAtomWithIdx(to_idx)

            # [v2.0] 세분류된 전자 소스 타입
            from_type = self._classify_bond_source(mol, from_idx, to_idx)
            if from_type == "pi_bond" or from_type == "aromatic_pi":
                from_label = f"{atom_from.GetSymbol()}={atom_to.GetSymbol()} \u03c0전자"
            elif self._has_lone_pair(atom_from):
                from_type = "lone_pair"
                from_label = f"{atom_from.GetSymbol()} 비공유전자쌍"
            else:
                from_label = f"{atom_from.GetSymbol()}-{atom_to.GetSymbol()} \u03c3전자"

            # [v2.0] 페리고리 적응형 곡률
            peri_curvature = self._adaptive_curvature(mol, from_idx, next_to, "pericyclic")

            arrows.append(ArrowData(
                arrow_type="full",
                from_type=from_type,
                from_label=from_label,
                to_type="bond",
                to_label=f"새 결합 형성",
                from_atom_idx=from_idx,
                to_atom_idx=next_to,
                curvature=peri_curvature,
                color=ARROW_COLORS[color_idx],
            ))

        return arrows

    def _build_pericyclic_chain(self, bond_changes: List[BondChange],
                                 mol) -> List[int]:
        """
        간접 순환(Diels-Alder 등)의 원자 체인 구성.
        결합 변화 그래프의 degree-1 원자들 사이에 분자 경로를 삽입하여
        완전한 순환 체인 생성.

        Returns:
            순환 원자 체인 (짝수 인덱스=π결합 시작, 홀수 인덱스=π결합 끝)
            or 빈 리스트
        """
        change_atoms: Set[int] = set()
        adj: Dict[int, Set[int]] = {}
        for bc in bond_changes:
            change_atoms.add(bc.atom_i)
            change_atoms.add(bc.atom_j)
            adj.setdefault(bc.atom_i, set()).add(bc.atom_j)
            adj.setdefault(bc.atom_j, set()).add(bc.atom_i)

        degree_one = [a for a in change_atoms if len(adj.get(a, set())) == 1]
        if len(degree_one) != 2:
            return []

        a, b = degree_one

        # 결합 변화 경로 추출 (a→...→b)
        change_path = self._trace_change_path(a, b, adj, change_atoms)
        if not change_path:
            return []

        # 분자 내 경로로 cycle 완성 (b→...→a)
        mol_path = self._find_molecular_path(mol, b, a, change_atoms - {a, b})
        if not mol_path or len(mol_path) < 2:
            return []

        # 전체 순환: change_path + mol_path(양끝 제외)
        full_chain = change_path + mol_path[1:-1]  # a,b는 이미 포함

        return full_chain

    def _trace_change_path(self, start: int, end: int,
                            adj: Dict[int, Set[int]],
                            atoms: Set[int]) -> List[int]:
        """결합 변화 그래프에서 start→end 경로 추출"""
        visited = {start}
        path = [start]
        current = start

        while current != end:
            neighbors = [n for n in adj.get(current, set()) if n not in visited]
            if not neighbors:
                return []
            next_node = neighbors[0]
            visited.add(next_node)
            path.append(next_node)
            current = next_node

        return path

    def _order_cyclic_atoms(self, bond_changes: List[BondChange]) -> List[int]:
        """결합 변화 원자들을 순환 순서로 정렬"""
        # 인접 리스트 구성
        adj: Dict[int, List[int]] = {}
        for bc in bond_changes:
            adj.setdefault(bc.atom_i, []).append(bc.atom_j)
            adj.setdefault(bc.atom_j, []).append(bc.atom_i)

        # 모든 원자가 2개 연결이어야 순환
        atoms = list(adj.keys())
        if not all(len(adj[a]) == 2 for a in atoms):
            return []

        # DFS로 순환 순서 추출
        if not atoms:
            return []

        visited = set()
        chain = []
        current = atoms[0]

        while current not in visited:
            visited.add(current)
            chain.append(current)
            neighbors = adj[current]
            next_atom = None
            for n in neighbors:
                if n not in visited:
                    next_atom = n
                    break
            if next_atom is None:
                break
            current = next_atom

        return chain if len(chain) == len(atoms) else []

    # ────────────────────────────────────────────────────────────────────
    # Arrow Generation: Radical
    # ────────────────────────────────────────────────────────────────────

    def _generate_radical_arrows(self, bond_changes: List[BondChange],
                                  mol, charges: Dict[int, float]) -> List[ArrowData]:
        """라디칼 반응 화살표 생성 (half-arrow / fishhook)"""
        arrows: List[ArrowData] = []

        for bc in bond_changes:
            if bc.is_broken:
                # 동종분해: 각 원자에 1전자씩
                atom_i = mol.GetAtomWithIdx(bc.atom_i)
                atom_j = mol.GetAtomWithIdx(bc.atom_j)

                # [v2.0] 라디칼 적응형 곡률 + 세분류
                rad_curv = self._adaptive_curvature(mol, bc.atom_i, bc.atom_j, "radical")
                bond_src = self._classify_bond_source(mol, bc.atom_i, bc.atom_j)
                bond_label = f"{atom_i.GetSymbol()}-{atom_j.GetSymbol()} \u03c3결합"
                if bond_src == "pi_bond":
                    bond_label = f"{atom_i.GetSymbol()}={atom_j.GetSymbol()} \u03c0결합"

                # 화살표 1: 결합 → 원자 i (반쪽 화살표 / fishhook)
                arrows.append(ArrowData(
                    arrow_type="half",
                    from_type=bond_src,
                    from_label=bond_label,
                    to_type="atom",
                    to_label=f"{atom_i.GetSymbol()}\u00b7 (라디칼)",
                    from_atom_idx=bc.atom_j,  # 결합 중심→원자 i
                    to_atom_idx=bc.atom_i,
                    curvature=rad_curv,
                    color="#E53935",
                ))

                # 화살표 2: 결합 → 원자 j (반쪽 화살표 / fishhook)
                arrows.append(ArrowData(
                    arrow_type="half",
                    from_type=bond_src,
                    from_label=bond_label,
                    to_type="atom",
                    to_label=f"{atom_j.GetSymbol()}\u00b7 (라디칼)",
                    from_atom_idx=bc.atom_i,
                    to_atom_idx=bc.atom_j,
                    curvature=-rad_curv,
                    color="#1E88E5",
                ))

        return arrows

    # ────────────────────────────────────────────────────────────────────
    # Electron Chain Resolution
    # ────────────────────────────────────────────────────────────────────

    def _resolve_electron_chain(self, arrows: List[ArrowData],
                                 mol, charges: Dict[int, float]) -> List[ArrowData]:
        """
        화살표를 전자 흐름 체인 순서로 정렬.
        Nu(전자 제공) → ... → LG(이탈기) 순서.
        """
        if len(arrows) <= 1:
            return arrows

        # 각 화살표의 from/to 원자로 체인 구성
        # from→to 방향으로 연결: 앞 화살표의 to가 뒤 화살표의 from
        arrow_by_from: Dict[int, ArrowData] = {}
        arrow_by_to: Dict[int, ArrowData] = {}

        for a in arrows:
            if a.from_atom_idx >= 0:
                arrow_by_from[a.from_atom_idx] = a
            if a.to_atom_idx >= 0:
                arrow_by_to[a.to_atom_idx] = a

        # 체인 시작점 찾기: from_atom이 다른 화살표의 to_atom이 아닌 것
        chain_starts = []
        for a in arrows:
            if a.from_atom_idx >= 0 and a.from_atom_idx not in arrow_by_to:
                chain_starts.append(a)

        if not chain_starts:
            return arrows  # 순환이거나 단독 → 원래 순서

        # 체인 따라가기
        ordered: List[ArrowData] = []
        used: Set[int] = set()

        for start in chain_starts:
            current = start
            while current and id(current) not in used:
                ordered.append(current)
                used.add(id(current))
                # 다음: 현재 to_atom에서 시작하는 화살표
                next_arrow = arrow_by_from.get(current.to_atom_idx)
                current = next_arrow

        # 사용되지 않은 화살표 추가
        for a in arrows:
            if id(a) not in used:
                ordered.append(a)

        return ordered

    # ────────────────────────────────────────────────────────────────────
    # Color Assignment
    # ────────────────────────────────────────────────────────────────────

    def _assign_colors(self, arrows: List[ArrowData]) -> List[ArrowData]:
        """화살표에 순서대로 색상 할당"""
        for i, arrow in enumerate(arrows):
            if arrow.color == "#E53935":  # 기본색이면 변경
                arrow.color = ARROW_COLORS[i % len(ARROW_COLORS)]
        return arrows

    # ────────────────────────────────────────────────────────────────────
    # External Atom Handling
    # ────────────────────────────────────────────────────────────────────

    def generate_with_externals(self, result: BondChangeResult,
                                 external_labels: Dict[int, str] = None) -> List[ArrowData]:
        """
        외부 라벨 (시약 등)을 고려한 화살표 생성.
        unmapped 원자 → external_label로 변환.

        Args:
            result: BondChangeResult
            external_labels: {atom_idx: "H⁺"} 형태의 외부 라벨 매핑
        """
        arrows = self.generate(result)

        if external_labels:
            for arrow in arrows:
                if arrow.from_atom_idx in result.mapping.unmapped_reactant:
                    label = external_labels.get(arrow.from_atom_idx, "외부")
                    arrow.from_atom_idx = -1
                    arrow.from_label = label
                if arrow.to_atom_idx in result.mapping.unmapped_reactant:
                    label = external_labels.get(arrow.to_atom_idx, "외부")
                    arrow.to_atom_idx = -1
                    arrow.to_label = label

        return arrows


# ============================================================================
# UTILITY: bond order helper (re-exported for convenience)
# ============================================================================

def _bond_type_to_order(bond_type) -> float:
    """RDKit BondType → 수치 결합차수"""
    if not RDKIT_AVAILABLE:
        return 1.0
    from bond_change_detector import _bond_type_to_order as _bto
    return _bto(bond_type)


def _graph_distance(mol, idx_a: int, idx_b: int) -> int:
    """
    분자 그래프에서 두 원자 사이의 최단 결합 거리 (BFS).
    연결되지 않은 경우 999 반환.
    """
    if mol is None or idx_a < 0 or idx_b < 0:
        return 999
    if idx_a == idx_b:
        return 0
    n = mol.GetNumAtoms()
    if idx_a >= n or idx_b >= n:
        return 999

    from collections import deque
    visited = {idx_a}
    queue = deque([(idx_a, 0)])
    while queue:
        current, dist = queue.popleft()
        if dist > 6:  # 최대 탐색 깊이 제한
            break
        atom = mol.GetAtomWithIdx(current)
        for nb in atom.GetNeighbors():
            nb_idx = nb.GetIdx()
            if nb_idx == idx_b:
                return dist + 1
            if nb_idx not in visited:
                visited.add(nb_idx)
                queue.append((nb_idx, dist + 1))
    return 999
