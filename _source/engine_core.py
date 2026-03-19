# engine_core.py (v2.80 - Interface Unified + Type Hints)
import math
from typing import Optional, List, Set, Dict, Tuple

# 타입 별칭: 좌표 키 (x, y) 튜플
CoordKey = Tuple[float, float]
# 인접 리스트: { 좌표키: [(이웃좌표키, 결합차수), ...] }
AdjDict = Dict[CoordKey, List[Tuple[CoordKey, int]]]
# 원자 데이터: { 좌표키: {"main": str, "attach": dict} }
AtomDict = Dict[CoordKey, dict]


class ConjugationEngine:
    """공액계(Conjugation) 및 방향족 탐색 엔진.

    Pi 시스템 섬 탐색, 고리 발견, Hückel 규칙 판정을 담당합니다.
    """

    # 전이금속: d-오비탈 상호작용이므로 π 공액에 참여하지 않음
    TRANSITION_METALS = frozenset({
        'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
        'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
        'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg',
    })

    def __init__(self):
        self.eps: float = 8.0  # 좌표 매칭 허용 오차 (픽셀)

    def find_matching_atom(self, pt: CoordKey, keys: List[CoordKey]) -> Optional[CoordKey]:
        """좌표 pt와 eps(8px) 이내로 매칭되는 원자 키를 반환합니다.
        
        Args:
            pt: 탐색할 좌표 (x, y)
            keys: 원자 좌표 키 목록
            
        Returns:
            매칭된 좌표 키, 없으면 None
        """
        for k in keys:
            if math.hypot(pt[0] - k[0], pt[1] - k[1]) < self.eps:
                return k
        return None

    def get_pi_islands_in_mol(self, mol: Set[CoordKey], atoms: AtomDict, adj: AdjDict) -> List[Set[CoordKey]]:
        """분자 섬(mol) 내부에서 연결된 Pi 시스템 섬들을 탐색합니다.
        
        Args:
            mol: 분자를 구성하는 원자 좌표 집합
            atoms: 전체 원자 데이터
            adj: 인접 리스트
            
        Returns:
            Pi 시스템 섬 목록 (각 섬은 좌표 집합)
        """
        pi_islands = []
        visited = set()
        
        for node in mol:
            at = atoms.get(node, {})
            # 전이금속은 π 공액에 참여하지 않음 (d-오비탈 상호작용)
            elem = at.get("main", "") or ""  # '' = carbon
            if elem in self.TRANSITION_METALS:
                continue
            # [PLAN-CHEM-002] formal charge가 있는 원자도 pi 참여자로 인정
            # ferrocene의 Cp- 고리: [cH-] 원자가 charge="-"로 저장되지만
            # attach에는 없을 수 있음 → charge 필드 직접 체크 추가
            has_charge_field = at.get("charge", "") in ("+", "-")
            is_participant = (any(o >= 2 for _, o in adj.get(node, [])) or
                             any(s in ["+", "-", "·", ".."] for s in at.get("attach", {}).values()) or
                             has_charge_field)

            if node not in visited and is_participant:
                island = set()
                stack = [node]
                while stack:
                    curr = stack.pop()
                    if curr not in island:
                        island.add(curr)
                        visited.add(curr)
                        for n, _ in adj.get(curr, []):
                            if n in mol:
                                n_at = atoms.get(n, {})
                                # 전이금속을 통한 BFS 전파 차단
                                n_elem = n_at.get("main", "") or ""
                                if n_elem in self.TRANSITION_METALS:
                                    continue
                                n_has_charge = n_at.get("charge", "") in ("+", "-")
                                if (any(o >= 2 for _, o in adj.get(n, [])) or
                                    any(s in ["+", "-", "·", ".."] for s in n_at.get("attach", {}).values()) or
                                    n_has_charge):
                                    stack.append(n)
                if len(island) >= 2:
                    pi_islands.append(island)
        return pi_islands

    def get_rings(self, island: Set[CoordKey], adj: AdjDict) -> List[List[CoordKey]]:
        """Pi 섬 내에서 고리(ring) 구조를 DFS로 탐색합니다.
        
        Args:
            island: Pi 시스템 섬 (원자 좌표 집합)
            adj: 인접 리스트
            
        Returns:
            발견된 고리 목록 (각 고리는 좌표 리스트)
        """
        rings = []

        def dfs(curr, start, path):
            if len(path) > 15:
                return
            for n, _ in adj.get(curr, []):
                if n == start and len(path) >= 3:
                    if tuple(sorted(path)) not in [tuple(sorted(r)) for r in rings]:
                        rings.append(path[:])
                elif n in island and n not in path:
                    path.append(n)
                    dfs(n, start, path)
                    path.pop()

        for node in island:
            dfs(node, node, [node])
        return rings

    def is_huckel(self, r: List[CoordKey], atoms: AtomDict, adj: AdjDict) -> bool:
        """고리 r이 Hückel 방향족 규칙(4n+2)을 만족하는지 판정합니다.
        
        Args:
            r: 고리를 구성하는 원자 좌표 리스트
            atoms: 원자 데이터 (인자 순서 통일: atoms → adj)
            adj: 인접 리스트
            
        Returns:
            Hückel 규칙 만족 여부
        """
        pi = 0
        for i in range(len(r)):
            u, v = r[i], r[(i + 1) % len(r)]
            if any(neighbor == v and order >= 2 for neighbor, order in adj[u]):
                pi += 2
        ex = sum(2 for n in r if any(s in ["-", ".."] for s in atoms[n].get("attach", {}).values()))
        rad = sum(1 for n in r if "·" in atoms[n].get("attach", {}).values())
        return (pi + ex + rad) in [2, 6, 10, 14, 18, 22, 26]
