# engine_resonance.py (v5.90 - CHEM-5: Aromatic Substituent Directing Effect)
# 변경 이력:
#   v5.90: [CHEM-5] 방향족 치환기 오쏘/파라 vs 메타 전자밀도 차별화
#          - _detect_ring_substituents(): 방향족 고리 치환기 감지 + EDG/EWG 분류
#          - _classify_substituent_effect(): 치환기 전자 기증/철수 판단
#          - _bfs_ring_distances(): 치환기 연결 탄소 기준 BFS 거리 계산
#          - calculate_resonance_deltas(): 오쏘/파라/메타별 억제 계수 차등 적용
#   v5.80: [CHEM-1/2/3] 방향족 균등 분배, 전하 필드, 라디칼 반영
import logging
import numpy as np
from collections import deque
from typing import Set, Dict, List, Tuple, Optional
from chem_data import ELEMENT_DATA

logger = logging.getLogger(__name__)

# 타입 별칭 (engine_core.py와 동일)
CoordKey = Tuple[float, float]
AdjDict = Dict[CoordKey, List[Tuple[CoordKey, int]]]
AtomDict = Dict[CoordKey, dict]


class ResonanceEngine:
    """공명(Resonance) 전자밀도 계산 엔진.
    
    Hückel 분자궤도법(HMO) 기반으로 Pi 시스템 내
    각 원자의 전자밀도 편차(delta)를 계산합니다.
    
    v5.90 신규:
    - 방향족 치환기의 오쏘/파라 지향성(EDG) vs 메타 지향성(EWG) 가시화
    - EDG(-OH, -NH2, -F 등): 오쏘/파라 delta 유지, 메타 강억제
    - EWG(-NO2, -COOH, -CN 등): 메타 delta 상대 유지, 오쏘/파라 강억제
    """

    def calculate_resonance_deltas(self, island: Set[CoordKey], atoms: AtomDict,
                                   adj: AdjDict) -> Dict[CoordKey, float]:
        """Pi 시스템 섬 내 각 원자의 공명 전하 편차를 계산합니다.
        
        Hückel 행렬(H)을 구성하고 고유값 분해를 통해
        전자밀도 분포를 산출한 뒤, 기여 전자수와의 차이를 반환합니다.
        
        v5.90: 방향족 치환기 효과로 인한 오쏘/파라 vs 메타 비대칭 delta 억제 적용.
        
        Args:
            island: Pi 시스템 섬 (원자 좌표 집합)
            atoms: 원자 데이터
            adj: 인접 리스트
            
        Returns:
            각 원자의 공명 전하 편차 딕셔너리
        """
        nodes = list(island)
        n = len(nodes)
        deltas = {node: 0.0 for node in nodes}
        if n < 2:
            return deltas

        H = np.zeros((n, n))
        # Rule N: 타입 가드 — adj/atoms는 dict
        assert isinstance(adj, dict) and isinstance(atoms, dict)
        sym_adj = {}
        for u in island:
            for v, order in adj.get(u, []):
                if v in island:
                    pair = tuple(sorted((u, v)))
                    sym_adj[pair] = max(sym_adj.get(pair, 0), order)

        for i, u in enumerate(nodes):
            _atom_u = atoms.get(u, {})
            if not isinstance(_atom_u, dict):
                _atom_u = {}
            at_main = _atom_u.get("main") or "C"
            _el_data_u = ELEMENT_DATA.get(at_main, {"negativity": 2.5})
            u_en = _el_data_u["negativity"] if isinstance(_el_data_u, dict) and "negativity" in _el_data_u else 2.5
            alpha = (2.5 - u_en) * 1.8
            _att_u = _atom_u.get("attach", {})
            if not isinstance(_att_u, dict):
                _att_u = {}
            fc_bias = sum(4.0 if s == "+" else -4.0 for s in _att_u.values())
            # [CHEM-2] charge 필드 직접 반영
            charge_field = _atom_u.get("charge", "")
            if not isinstance(charge_field, str):
                charge_field = str(charge_field) if charge_field is not None else ""
            charge_field_bias = 4.0 if charge_field == "+" else (-4.0 if charge_field == "-" else 0.0)
            H[i, i] = alpha + fc_bias + charge_field_bias

            for j, v in enumerate(nodes):
                pair = tuple(sorted((u, v)))
                if pair in sym_adj:
                    H[i, j] = H[j, i] = -1.4 if sym_adj[pair] >= 1.5 else -0.85

        try:
            vals, vecs = np.linalg.eigh(H)
            pi_e_list = [self._get_node_pi_contribution(node, atoms, adj) for node in nodes]
            total_pi_e = sum(pi_e_list)
            densities = np.zeros(n)
            rem_e = total_pi_e
            for k in range(n):
                occ = min(2.0, rem_e)
                densities += occ * (vecs[:, k] ** 2)
                rem_e -= occ
            for i, node in enumerate(nodes):
                deltas[node] = (pi_e_list[i] - densities[i]) * 1.5

            # ── [CHEM-1 + CHEM-5] 방향족 delta 억제 ──────────────────────────
            # 방향족 원자를 식별하고, 치환기 유무와 종류에 따라 억제 계수를 차등 적용
            aromatic_nodes = self._get_aromatic_nodes_rdkit(island, atoms, adj)
            if aromatic_nodes:
                # [CHEM-5] 치환기 효과 감지
                substituent_effects = self._detect_ring_substituents(
                    aromatic_nodes, atoms, adj
                )

                if substituent_effects:
                    # 치환기가 있는 방향족 시스템: 오쏘/파라 vs 메타 차등 억제
                    self._apply_directing_effect(
                        deltas, aromatic_nodes, substituent_effects, adj
                    )
                else:
                    # 치환기 없는 순수 방향족 (벤젠, 나프탈렌 등): CHEM-1 균등 억제
                    for node in aromatic_nodes:
                        if node in deltas:
                            deltas[node] *= 0.1

        except Exception as e:
            logger.warning("Resonance delta calculation error: %s", e)
        return deltas

    # ══════════════════════════════════════════════════════════════════
    # [CHEM-5] 치환기 감지 및 지향성 효과 적용
    # ══════════════════════════════════════════════════════════════════

    def _detect_ring_substituents(
        self,
        aromatic_nodes: Set[CoordKey],
        atoms: AtomDict,
        adj: AdjDict,
    ) -> List[Dict]:
        """방향족 고리에 연결된 치환기를 감지하고 EDG/EWG를 분류합니다.
        
        Args:
            aromatic_nodes: 방향족 원자 좌표 집합
            atoms: 원자 데이터
            adj: 인접 리스트
            
        Returns:
            [{attachment: CoordKey, sub_atom: CoordKey, effect: str}] 리스트
            effect: "EDG" | "EWG" | "EDG_WEAK" | "NEUTRAL"
        """
        substituents = []
        # Rule N: 타입 가드 — adj/atoms는 dict
        assert isinstance(adj, dict) and isinstance(atoms, dict)
        for ar_node in aromatic_nodes:
            for neighbor, order in adj.get(ar_node, []):
                # 방향족 고리 외부 원자인지 확인
                if neighbor not in aromatic_nodes:
                    _atom_nb = atoms.get(neighbor, {})
                    if not isinstance(_atom_nb, dict):
                        _atom_nb = {}
                    n_main = _atom_nb.get("main", "C")
                    # H는 무시 (수소는 약한 EDG이나 지향성 효과 계산에서 제외)
                    if n_main == "H":
                        continue
                    effect = self._classify_substituent_effect(neighbor, atoms, adj)
                    if effect != "NEUTRAL":
                        substituents.append({
                            "attachment": ar_node,    # 고리에서 치환기가 붙은 탄소
                            "sub_atom": neighbor,     # 치환기 원자
                            "effect": effect,
                        })
        return substituents

    def _classify_substituent_effect(
        self,
        sub_key: CoordKey,
        atoms: AtomDict,
        adj: AdjDict,
    ) -> str:
        """치환기 원자의 전자 기증/철수 효과를 분류합니다.
        
        분류 기준 (공명 효과 우선):
        - EDG (+M): -OH, -OR, -NH2, -NHR, -NR2, 할로겐(-F,-Cl,-Br,-I), -S-
        - EWG (-M): -NO2, -COOH, -CHO, -CO-, -CN, -SO3H, -SO2R
        - EDG_WEAK (+I): 알킬기 (피리딘 같이 약한 기증)
        - NEUTRAL: 단순 탄소 골격 (기준)
        
        Args:
            sub_key: 치환기 원자 좌표
            atoms: 원자 데이터
            adj: 인접 리스트
            
        Returns:
            "EDG" | "EWG" | "EDG_WEAK" | "NEUTRAL"
        """
        _atom_sub = atoms.get(sub_key, {})
        if not isinstance(_atom_sub, dict):
            _atom_sub = {}
        sub_main = _atom_sub.get("main", "C")

        # ── 할로겐: EDG (lone pair donation, 오쏘/파라 지향)
        if sub_main in ("F", "Cl", "Br", "I"):
            return "EDG"

        # ── 산소
        if sub_main == "O":
            # C=O (알데히드, 케톤, 카르복실): EWG
            for neighbor, order in adj.get(sub_key, []):
                _atom_n = atoms.get(neighbor, {})
                if not isinstance(_atom_n, dict):
                    _atom_n = {}
                n_main = _atom_n.get("main", "C")
                if n_main == "C" and order >= 2:
                    return "EWG"
            # -O- (charge "-") → O- 음이온: 강한 EDG
            if _atom_sub.get("charge") == "-":
                return "EDG"
            # 단결합 O (-OH, -OR): EDG (lone pair donation)
            return "EDG"

        # ── 질소
        if sub_main == "N":
            # NO2: N에 양전하 또는 N-O 이중결합 → EWG
            if _atom_sub.get("charge") == "+":
                return "EWG"
            # N과 연결된 O가 있고 이중결합 → EWG (NO2, NO 계열)
            for neighbor, order in adj.get(sub_key, []):
                _atom_n2 = atoms.get(neighbor, {})
                if not isinstance(_atom_n2, dict):
                    _atom_n2 = {}
                n_main = _atom_n2.get("main", "C")
                if n_main == "O" and order >= 2:
                    return "EWG"
            # CN (N가 C와 삼중결합): EWG (단, C쪽에서 감지해야 함)
            # 나머지 N: EDG (-NH2, -NHR, -NR2 계열)
            return "EDG"

        # ── 황
        if sub_main == "S":
            # SO2R, SO3H: S 주변 O가 2개 이상 → EWG
            o_count = sum(1 for nb, _ in adj.get(sub_key, [])
                          if (atoms.get(nb, {}) if isinstance(atoms.get(nb), dict) else {}).get("main") == "O")
            if o_count >= 2:
                return "EWG"
            # -SH, -SR: 약한 EDG
            return "EDG"

        # ── 탄소 치환기
        if sub_main == "C":
            # C≡N (CN): C와 삼중결합 N → EWG
            for neighbor, order in adj.get(sub_key, []):
                _atom_cn = atoms.get(neighbor, {})
                if not isinstance(_atom_cn, dict):
                    _atom_cn = {}
                if _atom_cn.get("main") == "N" and order >= 3:
                    return "EWG"
            # C=O: 알데히드(-CHO), 케톤(-COR), 카르복실(-COOH) → EWG
            for neighbor, order in adj.get(sub_key, []):
                _atom_co = atoms.get(neighbor, {})
                if not isinstance(_atom_co, dict):
                    _atom_co = {}
                if _atom_co.get("main") == "O" and order >= 2:
                    return "EWG"
            # CF3: C에 할로겐 3개 → EWG
            halogen_count = sum(1 for nb, _ in adj.get(sub_key, [])
                                if (atoms.get(nb, {}) if isinstance(atoms.get(nb), dict) else {}).get("main") in ("F", "Cl", "Br"))
            if halogen_count >= 2:
                return "EWG"
            # 알킬기: 약한 EDG
            return "EDG_WEAK"

        return "NEUTRAL"

    def _bfs_ring_distances(
        self,
        attachment: CoordKey,
        aromatic_nodes: Set[CoordKey],
        adj: AdjDict,
    ) -> Dict[CoordKey, int]:
        """치환기 연결 탄소(attachment)에서 방향족 고리 내 BFS 최단 거리 계산.
        
        6원 방향족 고리 기준:
        - 거리 0: ipso (치환기 붙은 탄소)
        - 거리 1: ortho (오쏘)
        - 거리 2: meta (메타)
        - 거리 3: para (파라)
        
        Args:
            attachment: 치환기가 붙은 방향족 탄소 좌표
            aromatic_nodes: 방향족 원자 집합
            adj: 인접 리스트
            
        Returns:
            {aromatic_node: distance} 딕셔너리
        """
        distances: Dict[CoordKey, int] = {attachment: 0}
        queue = deque([attachment])
        while queue:
            current = queue.popleft()
            # Rule N: isinstance guard for adj
            if not isinstance(adj, dict): adj = {}
            for neighbor, _ in adj.get(current, []):
                if neighbor in aromatic_nodes and neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        return distances

    def _apply_directing_effect(
        self,
        deltas: Dict[CoordKey, float],
        aromatic_nodes: Set[CoordKey],
        substituent_effects: List[Dict],
        adj: AdjDict,
    ):
        """치환기 지향성 효과에 따라 방향족 원자의 delta 억제 계수를 차등 적용합니다.
        
        이론:
        - EDG 치환기: 오쏘/파라 위치에 π 전자밀도 증가 → delta 억제 완화
          (오쏘:×0.50, 파라:×0.50, 메타:×0.05)
        - EWG 치환기: 오쏘/파라 전자밀도 감소, 메타 상대적 유지 → 반대 패턴
          (오쏘:×0.05, 파라:×0.05, 메타:×0.35)
        - 복수 치환기: 억제 계수의 곱(누적 효과) 적용
        
        Args:
            deltas: 현재 계산된 delta 딕셔너리 (수정됨)
            aromatic_nodes: 방향족 원자 집합
            substituent_effects: _detect_ring_substituents() 결과
            adj: 인접 리스트
        """
        # 억제 계수 초기화 (기본: CHEM-1 균등 억제 0.1)
        suppress: Dict[CoordKey, float] = {node: 0.1 for node in aromatic_nodes}

        # 치환기별로 위치 계산 및 억제 계수 적용
        for sub_info in substituent_effects:
            attachment = sub_info["attachment"]
            effect = sub_info["effect"]

            ring_dist = self._bfs_ring_distances(attachment, aromatic_nodes, adj)

            for node, dist in ring_dist.items():
                if node not in suppress:
                    continue

                if effect in ("EDG", "EDG_WEAK"):
                    # 오쏘/파라 지향성: 오쏘(dist=1), 파라(dist=3) 억제 완화
                    edg_strength = 1.0 if effect == "EDG" else 0.6
                    if dist == 0:    # ipso
                        factor = 0.20 * edg_strength
                    elif dist == 1:  # ortho
                        factor = 0.50 * edg_strength
                    elif dist == 2:  # meta
                        factor = 0.05
                    elif dist == 3:  # para
                        factor = 0.50 * edg_strength
                    else:
                        factor = 0.10
                    # 더 완화된(큰) 계수 우선 (복수 치환기 시 최대값 사용)
                    suppress[node] = max(suppress[node], factor)

                elif effect == "EWG":
                    # 메타 지향성: 메타(dist=2) 억제 완화, 오쏘/파라 강억제
                    if dist == 0:    # ipso
                        factor = 0.15
                    elif dist == 1:  # ortho
                        factor = 0.05
                    elif dist == 2:  # meta
                        factor = 0.35
                    elif dist == 3:  # para
                        factor = 0.05
                    else:
                        factor = 0.10
                    # EWG: 최대값 적용 (반대 치환기와 경쟁 시 완화 우선)
                    suppress[node] = max(suppress[node], factor)

        # 억제 계수 최종 적용
        for node, factor in suppress.items():
            if node in deltas:
                deltas[node] *= factor

    # ══════════════════════════════════════════════════════════════════
    # Pi 기여 전자수 계산 (CHEM-2/3 포함)
    # ══════════════════════════════════════════════════════════════════

    def _get_node_pi_contribution(self, node: CoordKey, atoms: AtomDict,
                                  adj: AdjDict) -> float:
        """개별 원자의 Pi 시스템 기여 전자수를 반환합니다.
        
        Args:
            node: 원자 좌표
            atoms: 원자 데이터
            adj: 인접 리스트
            
        Returns:
            기여 전자수 (0.0, 0.5, 1.0, 또는 2.0)
        """
        _atom_node = atoms.get(node, {})
        if not isinstance(_atom_node, dict):
            _atom_node = {}
        _att_node = _atom_node.get("attach", {})
        if not isinstance(_att_node, dict):
            _att_node = {}
        # [해결] 양이온(+) 탄소는 파이 시스템 기여 전자 0개 (attach 딕셔너리 기반)
        if any(s == "+" for s in _att_node.values()):
            return 0.0
        # [CHEM-2] charge 필드 기반 양이온 처리 (attach와 별도 필드)
        _charge_node = _atom_node.get("charge", "")
        if not isinstance(_charge_node, str):
            _charge_node = str(_charge_node) if _charge_node is not None else ""
        if _charge_node == "+":
            return 0.0

        count = 0.0
        _adj_list = adj.get(node, [])
        if not isinstance(_adj_list, list):
            _adj_list = []
        if any(o >= 2 for _, o in _adj_list):
            count += 1
        for s in _att_node.values():
            if s in ["-", ".."]:
                count += 1
            # [CHEM-3] 라디칼 전자 반영: 단전자(·) → 1개 π 전자 기여
            elif s == "·":
                count += 1

        # [CHEM-2] charge 필드 음이온(-) 처리: 비공유전자쌍 추가
        if _charge_node == "-":
            count += 1

        return count

    # ══════════════════════════════════════════════════════════════════
    # RDKit 방향족 원자 식별 (CHEM-1)
    # ══════════════════════════════════════════════════════════════════

    def _get_aromatic_nodes_rdkit(self, island: Set[CoordKey], atoms: AtomDict,
                                   adj: AdjDict) -> Set[CoordKey]:
        """[CHEM-1] RDKit을 이용해 방향족 원자 집합을 반환합니다.
        
        RDKit의 SanitizeMol()과 GetIsAromatic()을 사용하여
        벤젠/나프탈렌/피롤/사이클로펜타디에닐 음이온/트로필리움 이온 등
        방향족 원자를 정확히 식별합니다.
        
        v5.91 수정:
        - 형식전하(charge/formal_charge) RDKit 원자에 반드시 설정
          → Cp-(음이온), Tropylium+(양이온) 등 이온성 방향족 인식 정확도 향상
        - RDKit 인식 실패 시 Hückel 4n+2 규칙 폴백 추가
        
        Args:
            island: Pi 시스템 섬 (원자 좌표 집합)
            atoms: 원자 데이터
            adj: 인접 리스트
            
        Returns:
            방향족으로 식별된 원자 좌표 집합 (RDKit 불가 시 Hückel 폴백)
        """
        try:
            from rdkit import Chem
            nodes = list(island)
            node_to_idx = {n: i for i, n in enumerate(nodes)}

            mol = Chem.RWMol()
            for n in nodes:
                _atom_rk = atoms.get(n, {})
                if not isinstance(_atom_rk, dict):
                    _atom_rk = {}
                symbol = _atom_rk.get("main") or "C"
                try:
                    atom_obj = Chem.Atom(symbol)
                except Exception as e:
                    logger.warning("Chem.Atom('%s') failed, falling back to 'C': %s", symbol, e)
                    atom_obj = Chem.Atom("C")

                # ★ [v5.91 핵심 수정] 형식전하 설정 — Cp-/Tropylium 인식 필수
                # charge 필드("+" / "-") 또는 formal_charge 정수 필드 모두 확인
                charge_str = _atom_rk.get("charge", "")
                if not isinstance(charge_str, str):
                    charge_str = str(charge_str) if charge_str is not None else ""
                fc = _atom_rk.get("formal_charge", 0)
                if not isinstance(fc, (int, float)):
                    fc = 0
                if charge_str == "+":
                    atom_obj.SetFormalCharge(1)
                elif charge_str == "-":
                    atom_obj.SetFormalCharge(-1)
                elif isinstance(fc, int) and fc != 0:
                    atom_obj.SetFormalCharge(fc)
                # attach 딕셔너리의 "+" / "-" 기호도 체크 (구형 데이터 호환)
                else:
                    _att_rk = _atom_rk.get("attach", {})
                    if not isinstance(_att_rk, dict):
                        _att_rk = {}
                    for s in _att_rk.values():
                        if s == "+":
                            atom_obj.SetFormalCharge(1)
                            break
                        elif s == "-":
                            atom_obj.SetFormalCharge(-1)
                            break

                mol.AddAtom(atom_obj)

            # 결합 추가 (중복 방지: 낮은 인덱스 → 높은 인덱스)
            added_pairs = set()
            for n in nodes:
                for m, order in adj.get(n, []):
                    if m in node_to_idx:
                        i1, i2 = node_to_idx[n], node_to_idx[m]
                        pair = (min(i1, i2), max(i1, i2))
                        if pair not in added_pairs:
                            added_pairs.add(pair)
                            bt = (Chem.rdchem.BondType.DOUBLE
                                  if order >= 2 else Chem.rdchem.BondType.SINGLE)
                            mol.AddBond(i1, i2, bt)

            try:
                final_mol = mol.GetMol()
                final_mol.UpdatePropertyCache(strict=False)
                Chem.SanitizeMol(final_mol,
                                  catchErrors=True,
                                  sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL)
            except Exception as e:
                # RDKit 정규화 실패 → Hückel 폴백
                logger.warning("RDKit SanitizeMol failed for island %s, using Hückel fallback: %s", island, e)
                return self._huckel_aromatic_fallback(island, atoms, adj)

            # GetAromaticAtoms() + GetSSSR() 기반 방향족 원자 집합 추출
            aromatic_indices = {a.GetIdx() for a in final_mol.GetAtoms()
                                if a.GetIsAromatic()}

            sssr = Chem.GetSSSR(final_mol)
            ring_aromatic_indices = set()
            for ring in sssr:
                ring_list = list(ring)
                if all(final_mol.GetAtomWithIdx(idx).GetIsAromatic()
                       for idx in ring_list):
                    ring_aromatic_indices.update(ring_list)

            confirmed = aromatic_indices & ring_aromatic_indices

            # ★ [v5.91] RDKit 인식 결과가 비어있으면 Hückel 폴백 시도
            if not confirmed:
                fallback = self._huckel_aromatic_fallback(island, atoms, adj)
                if fallback:
                    return fallback

            return {nodes[i] for i in confirmed}

        except ImportError:
            return self._huckel_aromatic_fallback(island, atoms, adj)
        except Exception as e:
            logger.warning("Aromaticity detection failed for island %s: %s", island, e)
            return set()

    # ══════════════════════════════════════════════════════════════════
    # [v5.91 신규] Hückel 4n+2 규칙 기반 방향족 폴백
    # ══════════════════════════════════════════════════════════════════

    def _huckel_aromatic_fallback(self, island: Set[CoordKey], atoms: AtomDict,
                                   adj: AdjDict) -> Set[CoordKey]:
        """RDKit 인식 실패 시 Hückel 4n+2 규칙으로 방향족 원자를 식별합니다.
        
        알고리즘:
        1. π 시스템 섬 내의 단순 고리(3~8원자)를 BFS로 탐색
        2. 고리 내 각 원자의 π 전자 기여수 합산
        3. 합이 4n+2 (n≥0) 이면 해당 고리를 방향족으로 판정
        
        대상 케이스:
        - 사이클로펜타디에닐 음이온 (C5H5-): 6 π 전자 (4×1+2) → 방향족
        - 트로필리움 이온 (C7H7+): 6 π 전자 (4×1+2) → 방향족
        - 피롤 (C4H4NH): 6 π 전자 → 방향족
        
        Args:
            island: Pi 시스템 섬
            atoms: 원자 데이터
            adj: 인접 리스트
            
        Returns:
            Hückel 방향족 원자 좌표 집합
        """
        aromatic_nodes: Set[CoordKey] = set()
        rings = self._find_rings_in_island(island, adj)

        for ring in rings:
            pi_e = sum(
                self._get_node_pi_contribution(node, atoms, adj)
                for node in ring
            )
            # 4n+2 체크 (n=0: 2e, n=1: 6e, n=2: 10e, ...)
            # 허용 오차 0.5 적용 (라디칼 등 부동소수점 처리)
            shifted = pi_e - 2
            if shifted >= -0.5 and abs(shifted % 4) < 0.5:
                aromatic_nodes.update(ring)

        return aromatic_nodes

    def _find_rings_in_island(self, island: Set[CoordKey],
                               adj: AdjDict) -> List[List[CoordKey]]:
        """π 시스템 섬 내에서 단순 고리(3~8원자)를 BFS로 탐색합니다.
        
        각 원자를 시작점으로 BFS를 수행하여 닫힌 고리를 탐색합니다.
        중복 고리 방지를 위해 원자 집합을 frozenset으로 정규화합니다.
        
        Args:
            island: Pi 시스템 섬
            adj: 인접 리스트
            
        Returns:
            고리 원자 좌표 리스트의 리스트 (중복 없음)
        """
        from collections import deque
        rings: List[List[CoordKey]] = []
        seen_rings: set = set()  # frozenset 기반 중복 제거

        for start in island:
            # BFS: (현재 노드, 경로, 방문 집합)
            queue = deque([(start, [start], {start})])
            while queue:
                current, path, visited = queue.popleft()
                if len(path) > 8:
                    continue
                # Rule N: isinstance guard for adj
                if not isinstance(adj, dict): adj = {}
                for neighbor, _ in adj.get(current, []):
                    if neighbor not in island:
                        continue
                    if neighbor == start and len(path) >= 3:
                        # 고리 발견
                        ring_key = frozenset(path)
                        if ring_key not in seen_rings:
                            seen_rings.add(ring_key)
                            rings.append(list(path))
                    elif neighbor not in visited:
                        new_visited = visited | {neighbor}
                        queue.append((neighbor, path + [neighbor], new_visited))

        return rings
