# engine_physics.py (v8.00 - Enhanced Directing Effects + Multi-atom Substituent Recognition)
from typing import Set, Dict, List, Tuple
from collections import deque
from chem_data import ELEMENT_DATA

# 타입 별칭 (engine_core.py와 동일)
CoordKey = Tuple[float, float]
AdjDict = Dict[CoordKey, List[Tuple[CoordKey, int]]]
AtomDict = Dict[CoordKey, dict]


class PhysicsEngine:
    """유발 효과(Inductive Effect) 및 치환기 점수 계산 엔진.

    전기음성도 차이를 기반으로 부분 전하를 산출하고,
    Pi 시스템에 대한 치환기의 전자 끌기/밀기 효과를 계산합니다.
    """

    # [PLAN-CHEM-003] 전이금속 원소 집합: Gasteiger 유발효과 계산에 부적합
    # d-orbital 참여로 인해 전기음성도 기반 유발효과가 부정확
    TM_SYMBOLS = frozenset({
        'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
        'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
    })

    def apply_inductive(self, mol: Set[CoordKey], atoms: AtomDict, adj: AdjDict,
                        charges: Dict[CoordKey, float]) -> None:
        """분자 내 각 결합의 전기음성도 차이에 따른 유발 효과를 적용합니다.

        Args:
            mol: 분자를 구성하는 원자 좌표 집합
            atoms: 원자 데이터
            adj: 인접 리스트
            charges: 부분 전하 딕셔너리 (in-place 수정)
        """
        for u in mol:
            for s in atoms[u].get("attach", {}).values():
                if s == "+":
                    charges[u] += 2.2  # 청색 선명도 강화
                elif s == "-":
                    charges[u] -= 2.2

            u_main = atoms[u].get("main") or "C"

            # [PLAN-CHEM-003] 전이금속은 유발효과 대신 formal charge만 반영
            # Gasteiger 알고리즘은 d-orbital을 고려하지 않아 TM에 부정확
            if u_main in self.TM_SYMBOLS:
                continue

            u_en = ELEMENT_DATA.get(u_main, {"negativity": 2.5})["negativity"]
            for v, order in adj.get(u, []):
                v_main = atoms[v].get("main") or "C"

                # 전이금속 이웃과의 유발효과도 skip
                if v_main in self.TM_SYMBOLS:
                    continue

                v_en = ELEMENT_DATA.get(v_main, {"negativity": 2.5})["negativity"]

                # [핵심 수정] 수소 간섭 계수를 0.08로 극단적으로 낮춤 (수소 삽입 시 고리 붕괴 해결)
                h_factor = 0.08 if (u_main == "C" and v_main == "H") or (u_main == "H" and v_main == "C") else 1.0
                diff = (u_en - v_en) * 0.45 * (1.0 + (order - 1) * 0.6) * h_factor
                charges[u] -= diff / 2.0

    def _classify_substituent(self, ring_node: CoordKey, neighbor: CoordKey,
                               order: int, atoms: AtomDict, adj: AdjDict,
                               ring_atoms: Set[CoordKey]) -> float:
        """치환기를 분석하여 directing_strength를 반환합니다.

        양수 = EWG (메타 지향), 음수 = EDG (오쏘/파라 지향)

        다원자 치환기도 전체적으로 분석하여 정확한 분류를 수행합니다.
        예: -NO2 (전체가 EWG), -OH (lone pair EDG), -COOH (EWG)
        """
        sub_main = atoms.get(neighbor, {}).get("main") or "C"
        sub_en = ELEMENT_DATA.get(sub_main, {"negativity": 2.5})["negativity"]
        c_en = ELEMENT_DATA.get("C", {"negativity": 2.5})["negativity"]

        has_plus = any(s == "+" for s in atoms.get(neighbor, {}).get("attach", {}).values())
        has_minus = any(s == "-" for s in atoms.get(neighbor, {}).get("attach", {}).values())

        # 양/음 전하 → 강한 EWG/EDG
        if has_plus:
            return 0.18  # EWG (강화: 0.15→0.18)
        if has_minus:
            return -0.18  # EDG

        # 다원자 치환기 분석: neighbor의 비고리 이웃들도 검사
        sub_neighbors = []
        for nb, nb_order in adj.get(neighbor, []):
            if nb != ring_node and nb not in ring_atoms:
                nb_main = atoms.get(nb, {}).get("main") or "C"
                sub_neighbors.append((nb_main, nb_order))

        # -NO2 패턴: N에 이중결합 O 2개 → 강한 EWG
        if sub_main == "N" and order == 1:
            double_o_count = sum(1 for m, o in sub_neighbors if m == "O" and o >= 2)
            if double_o_count >= 2:
                return 0.22  # 매우 강한 EWG (-NO2)
            single_o_count = sum(1 for m, o in sub_neighbors if m == "O" and o == 1)
            if double_o_count == 1 and single_o_count >= 1:
                return 0.18  # -NO2 변형

        # -CHO / -COR (알데히드/케톤 직접 연결): C=O → EWG
        if (sub_main in ('', 'C')) and order == 1:
            double_o = sum(1 for m, o in sub_neighbors if m == "O" and o >= 2)
            if double_o >= 1:
                # -COOH: C(=O)(OH) → 강한 EWG
                single_o = sum(1 for m, o in sub_neighbors if m == "O" and o == 1)
                if single_o >= 1:
                    return 0.16  # -COOH, -COOR
                return 0.12  # -CHO, -COR (카보닐)

        # -SO3H, -SO2: S에 이중결합 O → 강한 EWG
        if sub_main == "S" and order == 1:
            double_o = sum(1 for m, o in sub_neighbors if m == "O" and o >= 2)
            if double_o >= 2:
                return 0.20  # -SO3H, -SO2R

        # -CN: C≡N → 강한 EWG
        if (sub_main in ('', 'C')) and order == 1:
            triple_n = sum(1 for m, o in sub_neighbors if m == "N" and o >= 3)
            if triple_n >= 1:
                return 0.14  # -CN

        # 이중결합 고전기음성도 원자 → EWG
        if sub_en > c_en + 0.3 and order >= 2:
            return 0.12  # =O, =N 직접 이중결합 EWG

        # 할로겐 (F, Cl, Br, I): 유발효과 EWG + 공명효과 EDG → 순 EDG (약함)
        if sub_main in ('F', 'Cl', 'Br', 'I') and order == 1:
            # F는 유발효과가 워낙 강해서 약한 비활성화 EDG
            if sub_main == 'F':
                return -0.02  # F: 약한 비활성화 오쏘/파라 지향
            return -0.04  # Cl, Br, I: 약한 활성화 오쏘/파라 지향

        # -OH, -OR, -NH2, -NHR: 단결합 lone pair 공여 → EDG
        if sub_main in ('O', 'N', 'S') and order == 1:
            # -NH2가 -OH보다 더 강한 EDG
            if sub_main == 'N':
                return -0.10  # -NH2, -NHR (강한 EDG)
            if sub_main == 'O':
                return -0.08  # -OH, -OR
            return -0.06  # -SH, -SR

        # 알킬기: 초공액 효과 → 약한 EDG
        if sub_en <= c_en:
            return -0.07  # -CH3, -C2H5 등 (강화: 0.06→0.07)

        return 0.0

    def apply_directing_effects(self, ring_atoms: Set[CoordKey], atoms: AtomDict,
                                adj: AdjDict, charges: Dict[CoordKey, float]) -> None:
        """방향족 고리의 오쏘/파라/메타 지향성 보정을 적용합니다.

        EDG(전자공여기) → 오쏘/파라 위치 전자밀도 증가
        EWG(전자흡인기) → 메타 위치 전자밀도 증가

        개선사항 (v8.0):
        - 다원자 치환기 인식 (-NO2, -COOH, -SO3H, -CN 등)
        - 오쏘 vs 파라 거리 감쇠 (오쏘가 약간 더 강함)
        - 치환기별 강도 세분화

        Args:
            ring_atoms: 방향족 고리 원자 좌표 집합
            atoms: 원자 데이터
            adj: 인접 리스트
            charges: 부분 전하 딕셔너리 (in-place 수정)
        """
        ring_size = len(ring_atoms)

        # 치환기 찾기: 고리에 직접 연결된 비고리 원자
        for ring_node in ring_atoms:
            for neighbor, order in adj.get(ring_node, []):
                if neighbor in ring_atoms:
                    continue
                # H는 지향성 효과 무시 (모든 위치에 동일한 영향)
                sub_main = atoms.get(neighbor, {}).get("main") or "C"
                if sub_main == "H":
                    continue

                # 다원자 치환기 분류
                directing_strength = self._classify_substituent(
                    ring_node, neighbor, order, atoms, adj, ring_atoms
                )

                if abs(directing_strength) < 0.01:
                    continue

                # BFS로 고리 내 위상 거리 계산
                distances: Dict[CoordKey, int] = {ring_node: 0}
                queue: deque = deque([ring_node])
                while queue:
                    curr = queue.popleft()
                    for nb, _ in adj.get(curr, []):
                        if nb in ring_atoms and nb not in distances:
                            distances[nb] = distances[curr] + 1
                            queue.append(nb)

                # 위상 거리에 따른 전하 보정
                for target in ring_atoms:
                    dist = distances.get(target, 0)
                    if dist == 0:
                        # ipso 위치 — 약한 보정 (치환기 직접 연결)
                        charges[target] += directing_strength * 0.4
                    elif dist == 1:
                        # 오쏘 위치 — 가장 강한 보정
                        charges[target] -= directing_strength * 1.2
                    elif dist == 3 or (ring_size == 6 and dist == ring_size - 1 and dist == 5):
                        # 파라 위치 (6원환: dist=3) — 오쏘보다 약간 약함
                        charges[target] -= directing_strength * 0.9
                    elif dist % 2 == 1:
                        # 기타 홀수 거리 (큰 고리) — 오쏘/파라 계열
                        charges[target] -= directing_strength * 0.7
                    else:
                        # 메타 위치 (dist=2, 4 등) — 반대 방향
                        charges[target] += directing_strength * 0.35

    def calculate_substituent_score(self, node: CoordKey, pi_isl: Set[CoordKey],
                                    atoms: AtomDict, adj: AdjDict) -> float:
        """치환기 node의 Pi 시스템에 대한 전자 끌기/밀기 점수를 계산합니다.

        Args:
            node: 치환기 원자 좌표
            pi_isl: Pi 시스템 섬 (원자 좌표 집합)
            atoms: 원자 데이터
            adj: 인접 리스트

        Returns:
            치환기 점수 (양수: 전자 끌기, 음수: 전자 밀기)
        """
        at_main = atoms[node].get("main") or "C"
        at_en = ELEMENT_DATA.get(at_main, {"negativity": 2.5})["negativity"]
        # 양전하 측쇄의 전자 당김 효과 강화 (설폰산 메타 지향성 해결)
        score = sum(3.5 if s == "+" else -3.5 for s in atoms[node].get("attach", {}).values())
        for neighbor, order in adj.get(node, []):
            if neighbor in pi_isl:
                continue
            n_en = ELEMENT_DATA.get(atoms[neighbor].get("main") or "C", {"negativity": 2.5})["negativity"]
            score += (n_en - at_en) * order * 1.1
        return score

    def get_bond_length_angstrom(self, elem1: str, elem2: str, order: int,
                                  is_aromatic: bool = False) -> float:
        """두 원자 간 표준 결합 길이를 Angstrom 단위로 반환합니다.

        [PLAN-CHEM-001] chem_data.py BOND_LENGTHS 테이블을 조회하고,
        없으면 공유 반지름 합으로 추정합니다.

        Args:
            elem1: 첫 번째 원소 기호 (빈 문자열이면 'C')
            elem2: 두 번째 원소 기호 (빈 문자열이면 'C')
            order: 결합 차수 (1, 2, 3)
            is_aromatic: 방향족 결합 여부 (True이면 order=1.5로 조회)

        Returns:
            결합 길이 (Angstrom). 테이블에 없으면 공유 반지름 합 기반 추정값.
        """
        from chem_data import BOND_LENGTHS

        # 빈 문자열 → Carbon
        e1 = elem1 if elem1 else 'C'
        e2 = elem2 if elem2 else 'C'

        effective_order = 1.5 if is_aromatic else order

        # 정방향/역방향 모두 검색
        key1 = (e1, e2, effective_order)
        key2 = (e2, e1, effective_order)
        length = BOND_LENGTHS.get(key1) or BOND_LENGTHS.get(key2)
        if length:
            return length

        # fallback: 공유 반지름 합으로 추정
        return self._estimate_bond_length(e1, e2, order)

    @staticmethod
    def _estimate_bond_length(elem1: str, elem2: str, order: int) -> float:
        """공유 반지름 합으로 결합 길이를 추정합니다 (fallback).

        Args:
            elem1: 첫 번째 원소 기호
            elem2: 두 번째 원소 기호
            order: 결합 차수

        Returns:
            추정 결합 길이 (Angstrom)
        """
        r1 = ELEMENT_DATA.get(elem1, {"radius": 0.77})["radius"]
        r2 = ELEMENT_DATA.get(elem2, {"radius": 0.77})["radius"]
        # 이중결합 ~13% 축소, 삼중결합 ~20% 축소
        shrink = {1: 1.0, 2: 0.87, 3: 0.80}.get(order, 1.0)
        return (r1 + r2) * shrink
