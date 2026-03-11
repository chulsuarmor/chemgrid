# engine_resonance.py (v5.60 - Sign & Directing Fix)
import numpy as np
from chem_data import ELEMENT_DATA

class ResonanceEngine:
    def calculate_resonance_deltas(self, island, atoms, adj):
        nodes = list(island); n = len(nodes)
        deltas = {node: 0.0 for node in nodes}
        if n < 2: return deltas
        
        H = np.zeros((n, n)); sym_adj = {}
        for u in island:
            for v, order in adj.get(u, []):
                if v in island:
                    pair = tuple(sorted((u, v)))
                    sym_adj[pair] = max(sym_adj.get(pair, 0), order)

        for i, u in enumerate(nodes):
            at_main = atoms[u].get("main") or "C"
            u_en = ELEMENT_DATA.get(at_main, {"negativity": 2.5})["negativity"]
            alpha = (2.5 - u_en) * 1.8
            fc_bias = sum(4.0 if s=="+" else -4.0 for s in atoms[u].get("attach", {}).values())
            # [해결] 부호를 +로 변경하여 양전하 원자의 에너지 준위 상승 (청색 강제)
            H[i, i] = alpha + fc_bias 

            for j, v in enumerate(nodes):
                pair = tuple(sorted((u, v)))
                if pair in sym_adj:
                    H[i, j] = H[j, i] = -1.4 if sym_adj[pair] >= 1.5 else -0.85

        try:
            vals, vecs = np.linalg.eigh(H)
            pi_e_list = [self._get_node_pi_contribution(node, atoms, adj) for node in nodes]
            total_pi_e = sum(pi_e_list); densities = np.zeros(n); rem_e = total_pi_e
            for k in range(n):
                occ = min(2.0, rem_e); densities += occ * (vecs[:, k] ** 2); rem_e -= occ
            for i, node in enumerate(nodes):
                deltas[node] = (pi_e_list[i] - densities[i]) * 1.5
        except: pass
        return deltas

    def _get_node_pi_contribution(self, node, atoms, adj):
        # [해결] 양이온(+) 탄소는 파이 시스템 기여 전자 0개
        if any(s == "+" for s in atoms[node].get("attach", {}).values()): return 0.0
        count = 0
        if any(o >= 2 for _, o in adj.get(node, [])): count += 1
        for s in atoms[node].get("attach", {}).values():
            if s in ["-", ".."]: count += 1
        return count