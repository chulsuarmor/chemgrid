# engine_physics.py (v7.01 - NMR Prediction Added)
from typing import Set, Dict, List, Tuple
from chem_data import ELEMENT_DATA

# 타입 별칭 (engine_core.py와 동일)
CoordKey = Tuple[float, float]
AdjDict = Dict[CoordKey, List[Tuple[CoordKey, int]]]
AtomDict = Dict[CoordKey, dict]

# NMR 예측 테이블 (ppm 단위)
NMR_H_SHIFTS = {
    "Aliphatic": 0.9,      # R-CH3
    "Allylic": 1.7,        # C=C-CH3
    "Ketone_alpha": 2.1,   # -C(=O)-CH3
    "Ether_alpha": 3.4,    # -O-CH3
    "Ester_alpha": 3.7,    # -C(=O)O-CH3
    "Alcohol_alpha": 3.5,  # -CH2-OH
    "Halogen_alpha": 3.0,  # -CH2-X
    "Vinylic": 5.0,        # C=CH
    "Aromatic": 7.3,       # Ar-H (Benzene ~7.36)
    "Aldehyde": 9.5,       # -CHO
    "Carboxylic": 11.0,    # -COOH
    "Alcohol_OH": 2.0,     # R-OH (Broad)
    "Amine_NH": 1.5,       # R-NH2 (Broad)
}

NMR_C_SHIFTS = {
    "Aliphatic": 20.0,     # R-CH3
    "Aliphatic_CH2": 30.0, # R-CH2-R
    "Aliphatic_CH": 40.0,  # R-CH-R
    "Aliphatic_C": 35.0,   # R-C-R
    "Alcohol_alpha": 60.0, # C-OH
    "Ether_alpha": 70.0,   # C-O-C
    "Alkyne": 80.0,        # C#C
    "Alkene": 120.0,       # C=C
    "Aromatic": 128.5,     # Ar-C (Benzene ~128.5)
    "Nitrile": 118.0,      # -CN
    "Amide": 165.0,        # -C(=O)N
    "Ester": 170.0,        # -C(=O)O
    "Carboxylic": 175.0,   # -COOH
    "Aldehyde": 195.0,     # -CHO
    "Ketone": 205.0,       # -C(=O)-
}

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

    def predict_nmr_shifts(self, atoms: AtomDict, adj: AdjDict, aromatic_set: Set[CoordKey]) -> Dict[CoordKey, Dict[str, float]]:
        """원자별 예상 NMR Chemical Shift 값을 반환합니다.

        Args:
            atoms: 원자 데이터
            adj: 인접 리스트
            aromatic_set: 방향족 원자 집합

        Returns:
            Dict[CoordKey, {'H': float, 'C': float}]: 각 원자 좌표별 예상 H, C Shift 값
        """
        shifts = {}

        for coord, data in atoms.items():
            elem = data.get("main", "C")
            
            # 기본값 설정
            h_shift = 0.0
            c_shift = 0.0
            
            # 탄소(C)인 경우 13C 예측 및 부착된 수소의 1H 예측
            if elem == "C":
                is_aromatic = coord in aromatic_set
                neighbors = adj.get(coord, [])
                
                # 1. 탄소 기본 환경 판단
                if is_aromatic:
                    c_shift = NMR_C_SHIFTS["Aromatic"]
                    h_shift = NMR_H_SHIFTS["Aromatic"]
                else:
                    # 결합 차수 확인 (이중, 삼중 결합)
                    has_double = any(order == 2 for _, order in neighbors)
                    has_triple = any(order == 3 for _, order in neighbors)
                    
                    if has_triple:
                        c_shift = NMR_C_SHIFTS["Alkyne"]
                        h_shift = NMR_H_SHIFTS["Vinylic"] # Alkyne H는 별도지만 근사치
                    elif has_double:
                        c_shift = NMR_C_SHIFTS["Alkene"]
                        h_shift = NMR_H_SHIFTS["Vinylic"]
                    else:
                        c_shift = NMR_C_SHIFTS["Aliphatic"]
                        h_shift = NMR_H_SHIFTS["Aliphatic"]

                    # 인접 원자에 의한 Shift (알파 효과)
                    for n_coord, _ in neighbors:
                        n_elem = atoms[n_coord].get("main", "C")
                        if n_elem == "O":
                            # C=O 확인 (Double Bond)
                            is_carbonyl = False
                            for _, order in adj.get(n_coord, []): # O의 이웃 확인
                                if order == 2: is_carbonyl = True
                            
                            if is_carbonyl:
                                c_shift = max(c_shift, NMR_C_SHIFTS["Ketone"]) # 대략적 케톤/알데히드
                                h_shift = max(h_shift, NMR_H_SHIFTS["Aldehyde"] if len(neighbors) < 3 else NMR_H_SHIFTS["Ketone_alpha"])
                            else:
                                c_shift = max(c_shift, NMR_C_SHIFTS["Ether_alpha"])
                                h_shift = max(h_shift, NMR_H_SHIFTS["Ether_alpha"])
                        
                        elif n_elem == "N":
                            c_shift = max(c_shift, 50.0) # Amine alpha
                            h_shift = max(h_shift, 2.5)
                        
                        elif n_elem in ["F", "Cl", "Br", "I"]:
                            c_shift = max(c_shift, NMR_C_SHIFTS["Alcohol_alpha"]) # 할로겐 유사
                            h_shift = max(h_shift, NMR_H_SHIFTS["Halogen_alpha"])

                # 2. 벤젠 예외 처리 (정확히 C6H6인 경우 등)
                # 여기서는 'aromatic_set'에 속하면 벤젠 영역 값(7.3/128.5)을 사용하므로, 
                # CDCl3 용매 피크(7.26)와 구분되는 7.36(벤젠 순수) 등을 제공.
                # 사용자가 요청한 '실제 값' 반영.
                if is_aromatic:
                    # 벤젠의 경우 H: 7.36, C: 128.5
                    h_shift = 7.36
                    c_shift = 128.5

            elif elem == "H":
                # 수소가 독립 원자로 존재하는 경우 (거의 없음, 보통 attach로 처리됨)
                h_shift = 0.0 # 처리 안함
            
            shifts[coord] = {"H": h_shift, "C": c_shift}

        return shifts
