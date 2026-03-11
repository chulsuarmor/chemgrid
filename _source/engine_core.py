# engine_core.py (v2.70 - Isolated Island Discovery)
import math

class ConjugationEngine:
    def __init__(self):
        self.eps = 8.0 

    def find_matching_atom(self, pt, keys):
        for k in keys:
            if math.hypot(pt[0]-k[0], pt[1]-k[1]) < self.eps: return k
        return None

    def get_pi_islands_in_mol(self, mol, atoms, adj):
        """[해결] 인자로 받은 분자 섬(mol) 내부에서만 Pi 시스템을 탐색함"""
        pi_islands = []
        visited = set()
        
        # 전체가 아닌, 해당 분자 섬에 속한 원자들만 루프
        for node in mol:
            at = atoms.get(node, {})
            is_participant = (any(o >= 2 for _, o in adj.get(node, [])) or 
                             any(s in ["+", "-", "·", ".."] for s in at.get("attach", {}).values()))
            
            if node not in visited and is_participant:
                island = set(); stack = [node]
                while stack:
                    curr = stack.pop()
                    if curr not in island:
                        island.add(curr); visited.add(curr)
                        for n, _ in adj.get(curr, []):
                            # 인접 원자도 '같은 분자' 내에 있고 Pi 참여 조건 충족 시 포함
                            if n in mol:
                                n_at = atoms.get(n, {})
                                if (any(o >= 2 for _, o in adj.get(n, [])) or 
                                    any(s in ["+", "-", "·", ".."] for s in n_at.get("attach", {}).values())):
                                    stack.append(n)
                if len(island) >= 2: pi_islands.append(island)
        return pi_islands

    def get_rings(self, island, adj):
        rings = []
        def dfs(curr, start, path):
            if len(path) > 15: return
            for n, _ in adj.get(curr, []):
                if n == start and len(path) >= 3:
                    if tuple(sorted(path)) not in [tuple(sorted(r)) for r in rings]: rings.append(path[:])
                elif n in island and n not in path:
                    path.append(n); dfs(n, start, path); path.pop()
        for node in island: dfs(node, node, [node])
        return rings

    def is_huckel(self, r, adj, atoms):
        pi = 0
        for i in range(len(r)):
            u, v = r[i], r[(i+1)%len(r)]
            if any(neighbor == v and order >= 2 for neighbor, order in adj[u]): pi += 2
        ex = sum(2 for n in r if any(s in ["-", ".."] for s in atoms[n].get("attach", {}).values()))
        rad = sum(1 for n in r if "·" in atoms[n].get("attach", {}).values())
        return (pi + ex + rad) in [2, 6, 10, 14, 18, 22, 26]