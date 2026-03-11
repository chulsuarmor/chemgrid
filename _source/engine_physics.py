# engine_physics.py (v6.97 - H-Induced Activation Fix)
from chem_data import ELEMENT_DATA

class PhysicsEngine:
    def apply_inductive(self, mol, atoms, adj, charges):
        for u in mol:
            for s in atoms[u].get("attach", {}).values():
                if s == "+": charges[u] += 2.2 # 청색 선명도 강화
                elif s == "-": charges[u] -= 2.2 
            
            u_main = atoms[u].get("main") or "C"
            u_en = ELEMENT_DATA.get(u_main, {"negativity": 2.5})["negativity"]
            for v, order in adj.get(u, []):
                v_main = atoms[v].get("main") or "C"
                v_en = ELEMENT_DATA.get(v_main, {"negativity": 2.5})["negativity"]
                
                # [핵심 수정] 수소 간섭 계수를 0.08로 극단적으로 낮춤 (수소 삽입 시 고리 붕괴 해결)
                h_factor = 0.08 if (u_main == "C" and v_main == "H") or (u_main == "H" and v_main == "C") else 1.0
                diff = (u_en - v_en) * 0.45 * (1.0 + (order-1)*0.6) * h_factor
                charges[u] -= diff / 2.0 

    def calculate_substituent_score(self, node, pi_isl, atoms, adj):
        at_main = atoms[node].get("main") or "C"
        at_en = ELEMENT_DATA.get(at_main, {"negativity": 2.5})["negativity"]
        # 양전하 측쇄의 전자 당김 효과 강화 (설폰산 메타 지향성 해결)
        score = sum(3.5 if s=="+" else -3.5 for s in atoms[node].get("attach", {}).values())
        for neighbor, order in adj.get(node, []):
            if neighbor in pi_isl: continue
            n_en = ELEMENT_DATA.get(atoms[neighbor].get("main") or "C", {"negativity": 2.5})["negativity"]
            score += (n_en - at_en) * order * 1.1
        return score