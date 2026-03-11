# engine_physics.py (v7.00 - Interface Unified + Type Hints)
from typing import Set, Dict, List, Tuple
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
            u_en = ELEMENT_DATA.get(u_main, {"negativity": 2.5})["negativity"]
            for v, order in adj.get(u, []):
                v_main = atoms[v].get("main") or "C"
                v_en = ELEMENT_DATA.get(v_main, {"negativity": 2.5})["negativity"]

                # [핵심 수정] 수소 간섭 계수를 0.08로 극단적으로 낮춤 (수소 삽입 시 고리 붕괴 해결)
                h_factor = 0.08 if (u_main == "C" and v_main == "H") or (u_main == "H" and v_main == "C") else 1.0
                diff = (u_en - v_en) * 0.45 * (1.0 + (order - 1) * 0.6) * h_factor
                charges[u] -= diff / 2.0

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
