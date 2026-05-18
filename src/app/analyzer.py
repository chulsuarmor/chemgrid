# analyzer.py (v6.12 - M628: 3-tier ESP wrapper ORCA→xtb→Gasteiger)
# M646_BINS: xtb pre-compiled binary 자동 탐지 (shutil.which + 절대경로 폴백)
# 학술 인용 (Rule NN, THEORY-AUTO-001/002):
#   Mulliken, R.S. (1955) J. Chem. Phys. 23, 1833-1840.
#   Lowdin, P.O. (1950) J. Chem. Phys. 18, 365-375.
import logging
import math
import os  # [M646_BINS] os.environ.get for XTB_PATH
import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from typing import Dict, Optional, Tuple
from PyQt6.QtCore import QPointF # [추가] QPointF NameError 해결

logger = logging.getLogger(__name__)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
try:
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
from engine_core import ConjugationEngine
from engine_physics import PhysicsEngine
from engine_resonance import ResonanceEngine

class ChemicalAnalyzer:
    def __init__(self):
        self.core = ConjugationEngine()
        self.physics = PhysicsEngine()
        self.resonance = ResonanceEngine()

    def analyze(self, atoms, bonds, smiles=None):
        # [범용 보정] 3.chem 처럼 중심 탄소가 누락된 경우를 대비해 결합 좌표를 기반으로 원자를 복구합니다. 
        full_atoms = atoms.copy()
        for k1, k2 in bonds.keys():
            for pt in [k1, k2]:
                # 좌표 키 생성 (3.chem의 리스트/튜플 혼용 대응) [cite: 9]
                pt_key = (round(pt.x(), 2), round(pt.y(), 2)) if hasattr(pt, 'x') else (round(pt[0], 2), round(pt[1], 2))
                # 기존 atoms에 없는 좌표라면 탄소(C)로 간주하고 추가합니다. 
                if pt_key not in {(round(ak[0], 2), round(ak[1], 2)) for ak in atoms.keys()}:
                    full_atoms[pt_key] = {"main": "", "attach": {}}
        
        atoms = full_atoms
        if not atoms: return {"charges": {}, "islands": [], "aromatic": set(), "atoms": {}}
        
        norm_atoms = { (round(k[0], 2), round(k[1], 2)): v for k, v in atoms.items() }
        # Rule N: 타입 가드 — norm_atoms는 dict, 각 값도 dict
        assert isinstance(norm_atoms, dict)

        # [Fix] Scan for user-drawn radicals in 'attach'
        for k, v in norm_atoms.items():
            if not isinstance(v, dict):  # Rule N
                continue
            _attach = v.get("attach")
            if isinstance(_attach, dict):
                for d, sym in _attach.items():
                    if sym == "·" or sym == ".": # Check both dot characters
                        v["is_radical"] = True
                        logger.info("Radical detected at %s", k)

        norm_keys = list(norm_atoms.keys())
        
        global_charges = {k: 0.0 for k in norm_keys}
        full_adj = self._get_adj(norm_atoms, bonds)
        molecules = self._get_molecular_islands(norm_keys, full_adj)
        
        total_pi_islands = []
        all_aromatic = set()

        for mol in molecules:
            mol_charges = {k: 0.0 for k in mol}
            mol_adj = {k: [n for n in full_adj[k] if n[0] in mol] for k in mol}
            
            # 유발 효과 (Base Layer)
            self.physics.apply_inductive(mol, norm_atoms, mol_adj, mol_charges)

            # 공명 시스템 탐색
            mol_pi = self.core.get_pi_islands_in_mol(mol, norm_atoms, mol_adj)

            # [v8.0] 방향족 고리 오쏘/파라/메타 지향성 보정
            for pi_isl in mol_pi:
                if len(pi_isl) >= 5:  # 5원환 이상의 방향족 고리
                    self.physics.apply_directing_effects(
                        set(pi_isl), norm_atoms, mol_adj, mol_charges
                    )
            total_pi_islands.extend(mol_pi)
            
            for pi_isl in mol_pi:
                # 공명 델타 합산 (Additive Model)
                res_deltas = self.resonance.calculate_resonance_deltas(pi_isl, norm_atoms, mol_adj)
                for node, delta in res_deltas.items():
                    mol_charges[node] += delta
                
                # 치환기 벡터 효과 (v4.0: ortho/para/meta 위치별 차별화)
                assert isinstance(mol_adj, dict)  # Rule N: 타입 가드
                for node in pi_isl:
                    for neighbor, _ in mol_adj.get(node, []):
                        if neighbor not in pi_isl:
                            score = self.physics.calculate_substituent_score(neighbor, pi_isl, norm_atoms, mol_adj)
                            base_force = (score * 0.75) / len(pi_isl)
                            topo_dist = self._ring_topology_distance(node, pi_isl, mol_adj)
                            for target in pi_isl:
                                dist = topo_dist.get(target, 0)
                                if dist == 0:
                                    weight = 1.5   # ipso
                                elif dist % 2 == 1:
                                    weight = 1.3   # ortho(1), para(3)
                                else:
                                    weight = 0.4   # meta(2)
                                mol_charges[target] += base_force * weight
                                mol_charges[neighbor] -= base_force * weight * 0.2

                # [Fix v2] 형식전하 → π계 전자분포 반영 (사이클로펜타다이엔일 음이온 등)
                for node in pi_isl:
                    _na_node = norm_atoms.get(node, {})
                    if not isinstance(_na_node, dict):
                        _na_node = {}
                    _cf2 = _na_node.get("charge", "")
                    _att_na = _na_node.get("attach", {})
                    if not isinstance(_att_na, dict):
                        _att_na = {}
                    _ac2 = sum(
                        (1 if s == "+" else (-1 if s == "-" else 0))
                        for d, s in _att_na.items()
                        if d != -1
                    )
                    _ion = (1 if _cf2 == "+" else (-1 if _cf2 == "-" else 0)) + _ac2
                    if _ion != 0:
                        # [v4.0 Fix] 부호 반전 수정: 음이온(-) → 음전하(RED), 양이온(+) → 양전하(BLUE)
                        _spread = (_ion * 0.25) / max(len(pi_isl), 1)
                        for target in pi_isl:
                            mol_charges[target] += _spread

            # [v4.0] 분자 전체 형식전하 오프셋: 이온성 분자의 전체 ESP 보정
            # 음이온(-1) → 모든 원자에 음전하 분배, 양이온(+1) → 양전하 분배
            # 강도: 형식전하 1단위 → 원자당 ~0.5 전하 오프셋 (강한 ESP 전환 필요)
            net_formal_charge = 0
            for node in mol_charges:
                _at = norm_atoms.get(node, {})
                if not isinstance(_at, dict):
                    _at = {}
                _cf = _at.get("charge", "")
                net_formal_charge += (1 if _cf == "+" else (-1 if _cf == "-" else 0))
                _att_fc = _at.get("attach", {})
                if not isinstance(_att_fc, dict):
                    _att_fc = {}
                net_formal_charge += sum(
                    (1 if s == "+" else (-1 if s == "-" else 0))
                    for d, s in _att_fc.items() if d != -1
                )
            if net_formal_charge != 0 and len(mol_charges) > 0:
                offset = (net_formal_charge * 2.5) / len(mol_charges)
                for k in mol_charges:
                    mol_charges[k] += offset

            for k, q in mol_charges.items(): global_charges[k] = q

        # [v8.2] RDKit Gasteiger 전하 기반 보정 — 공명 등가성 자동 반영
        # NO2 등 공명 구조에서 등가 원자들의 전하가 동일하게 계산됨
        if RDKIT_AVAILABLE and smiles:
            try:
                from rdkit.Chem import AllChem
                _mol = Chem.MolFromSmiles(smiles)
                if _mol is not None:
                    _mol_h = Chem.AddHs(_mol)
                    AllChem.ComputeGasteigerCharges(_mol_h)
                    # Gasteiger 전하 추출 (heavy atoms만, idx → charge)
                    gasteiger = {}
                    for i in range(_mol.GetNumAtoms()):
                        gc = float(_mol_h.GetAtomWithIdx(i).GetDoubleProp('_GasteigerCharge'))
                        if not (math.isnan(gc) or math.isinf(gc)):
                            gasteiger[i] = gc

                    if gasteiger:
                        # [v8.2 FIX] rdkit_idx를 사용하여 정확한 인덱스 매핑
                        idx_to_nk = {}
                        for nk in norm_keys:
                            _nk_data = norm_atoms.get(nk, {})
                            if not isinstance(_nk_data, dict):
                                _nk_data = {}
                            rdkit_idx = _nk_data.get("rdkit_idx", -1)
                            if rdkit_idx >= 0:
                                idx_to_nk[rdkit_idx] = nk

                        if idx_to_nk:
                            # 매핑된 원자들에 대해 Gasteiger 블렌딩 적용
                            mapped_custom = {nk: global_charges[nk] for nk in idx_to_nk.values()}
                            mapped_gast = {nk: gasteiger[idx] for idx, nk in idx_to_nk.items() if idx in gasteiger}

                            c_range = max((abs(v) for v in mapped_custom.values()), default=1.0)
                            g_range = max((abs(v) for v in mapped_gast.values()), default=1.0)

                            if g_range > 0.001:
                                sf = (c_range / g_range) if c_range > 0.001 else 1.0
                                for nk in mapped_gast:
                                    g_scaled = mapped_gast[nk] * sf
                                    # 블렌딩: 60% Gasteiger + 40% custom physics
                                    global_charges[nk] = 0.6 * g_scaled + 0.4 * global_charges[nk]

                            # [v8.3] 공명 등가 원자 균등화: 같은 Gasteiger 전하 → 같은 최종 전하
                            # NO2의 두 O, 카복실레이트의 두 O 등이 자동으로 균등화됨
                            from collections import defaultdict
                            equiv_groups = defaultdict(list)
                            for idx, nk in idx_to_nk.items():
                                if idx in gasteiger:
                                    _eq_data = norm_atoms.get(nk, {})
                                    if not isinstance(_eq_data, dict):
                                        _eq_data = {}
                                    elem = _eq_data.get("main", "") or "C"
                                    # Gasteiger 전하를 3자리까지 반올림하여 그룹핑 키 생성
                                    g_key = (elem, round(gasteiger[idx], 3))
                                    equiv_groups[g_key].append(nk)

                            n_equalized = 0
                            for g_key, members in equiv_groups.items():
                                if len(members) >= 2:
                                    avg_charge = sum(global_charges[m] for m in members) / len(members)
                                    for m in members:
                                        global_charges[m] = avg_charge
                                    n_equalized += len(members)
                            if n_equalized > 0:
                                logger.info("[GASTEIGER] Equalized %d resonance-equivalent atoms", n_equalized)

                            logger.info("[GASTEIGER] Applied RDKit charges (blended 60/40) for %d atoms via rdkit_idx", len(idx_to_nk))
                        else:
                            logger.warning("[GASTEIGER] No rdkit_idx found, skipping Gasteiger blending")
                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            except Exception as e_gast:
                logger.warning("[GASTEIGER] Fallback to custom physics: %s", e_gast)

        # [P0-3 FIX v2] Post-Gasteiger resonance correction for EDG-substituted aromatics
        # Problem: Gasteiger charges only capture sigma-inductive effects. For EDGs like -OH,
        # -NH2, the heteroatom's high electronegativity makes inductive withdrawal dominate
        # in Gasteiger, but in reality lone-pair resonance donation (pi-conjugation) makes
        # ring carbons electron-RICH (should be RED in ESP).
        #
        # Chemistry basis (McMurry Ch.16, Clayden Ch.22):
        #   - EDG (+M effect) donates electron density INTO the ring via pi-resonance
        #   - Ortho/para positions get MORE density (directing effect)
        #   - Meta positions also get enriched, just less than ortho/para
        #   - The entire ring becomes electron-rich relative to unsubstituted benzene
        #
        # Solution: Apply corrections strong enough to overcome Gasteiger inductive bias.
        # Typical Gasteiger charge on ring C adjacent to OH: +0.02 to +0.08
        # We need corrections > this magnitude to flip sign to negative (RED).
        # Convention: RED = electron-rich (negative), BLUE = electron-poor (positive)
        for pi_isl in total_pi_islands:
            if len(pi_isl) < 5:  # only aromatic rings (5+ atoms)
                continue
            pi_set = set(pi_isl)
            # Check if this is a ring (edge_count >= node_count)
            edge_count = sum(
                sum(1 for item in full_adj.get(nd, []) if (item[0] if isinstance(item, (tuple, list)) else item) in pi_set)
                for nd in pi_isl
            ) // 2
            if edge_count < len(pi_isl):
                continue  # not a ring
            # Find substituents on this ring and apply resonance correction
            for ring_node in pi_isl:
                for neighbor, order in full_adj.get(ring_node, []):
                    if neighbor in pi_set:
                        continue
                    nb_data = norm_atoms.get(neighbor, {})
                    if not isinstance(nb_data, dict):
                        continue
                    sub_main = nb_data.get("main", "") or "C"
                    if sub_main == "H":
                        continue
                    # EDG check: O, N, S with single bond = lone pair donors
                    # These atoms have lone pairs that conjugate with the aromatic pi system
                    # GUARD: Must exclude EWG cases where the heteroatom is part of
                    # a withdrawing group (NO2, C=O, SO2, CN etc.)
                    is_edg = False
                    if sub_main == 'O' and order == 1:
                        # -OH, -OR: EDG unless part of C=O (ester/acid attached O)
                        # Check if O has a double bond to C (then it's C=O oxygen, not -OH)
                        has_double_to_c = False
                        for nb3, o3 in full_adj.get(neighbor, []):
                            if nb3 == ring_node:
                                continue
                            nb3_data = norm_atoms.get(nb3, {})
                            if not isinstance(nb3_data, dict):
                                continue
                            nb3_main = nb3_data.get("main", "") or "C"
                            if nb3_main in ('', 'C') and o3 >= 2:
                                has_double_to_c = True
                                break
                        if not has_double_to_c:
                            is_edg = True
                    elif sub_main == 'N' and order == 1:
                        # -NH2, -NHR, -NR2: EDG
                        # EXCLUDE -NO2 (N with double-bonded O neighbor) and -C≡N
                        has_double_o = False
                        for nb3, o3 in full_adj.get(neighbor, []):
                            if nb3 == ring_node:
                                continue
                            nb3_data = norm_atoms.get(nb3, {})
                            if not isinstance(nb3_data, dict):
                                continue
                            nb3_main = nb3_data.get("main", "") or "C"
                            if nb3_main == 'O' and o3 >= 2:
                                has_double_o = True
                                break
                        # Also check if N has positive formal charge (as in R-NO2)
                        nb_charge = nb_data.get("charge", "")
                        if not has_double_o and nb_charge != "+":
                            is_edg = True
                    elif sub_main == 'S' and order == 1:
                        # -SH, -SR: EDG, but exclude -SO2R, -SO3H (S with 2+ O neighbors)
                        o_neighbors = 0
                        for nb3, _ in full_adj.get(neighbor, []):
                            if nb3 == ring_node:
                                continue
                            nb3_data = norm_atoms.get(nb3, {})
                            if not isinstance(nb3_data, dict):
                                continue
                            if nb3_data.get("main", "") == 'O':
                                o_neighbors += 1
                        if o_neighbors < 2:
                            is_edg = True
                    if is_edg:
                        # Resonance correction per position (must overcome Gasteiger bias)
                        # [P0-3 FIX v3] Values strengthened to ensure catechol/aniline rings
                        # show RED (electron-rich) in ESP after 60% Gasteiger blending.
                        # Gasteiger ring-C near OH: +0.02~+0.08 (BLUE). Corrections must
                        # exceed blended Gasteiger to flip to RED. catechol: 2x cumulative.
                        # Basis: McMurry Ch.16 (activating groups), Clayden Ch.22 (+M effect)
                        if sub_main == 'N':
                            # -NH2/-NHR/-NR2: strong +M (lone pair on N, less electronegative)
                            corr_ipso = -0.08   # ipso: strong (N lone pair into ring)
                            corr_ortho = -0.16  # ortho: maximum enrichment
                            corr_meta = -0.07   # meta: enriched via through-space effect
                            corr_para = -0.16   # para: maximum enrichment (resonance equiv.)
                        elif sub_main == 'O':
                            # -OH/-OR: medium +M (lone pair on O, competes with inductive)
                            # Strengthened to guarantee sign flip vs Gasteiger (catechol needs 2x)
                            corr_ipso = -0.08   # ipso: moderate-strong (was -0.05)
                            corr_ortho = -0.15  # ortho: significant enrichment (was -0.10)
                            corr_meta = -0.06   # meta: mild enrichment (was -0.04)
                            corr_para = -0.15   # para: significant enrichment (was -0.10)
                        else:
                            # -SH/-SR: weak +M, poor 3p-2p orbital overlap with 2p ring
                            corr_ipso = -0.05   # ipso: mild (was -0.04)
                            corr_ortho = -0.09  # ortho: moderate enrichment (was -0.07)
                            corr_meta = -0.04   # meta: slight enrichment (was -0.03)
                            corr_para = -0.09   # para: moderate enrichment (was -0.07)
                        # BFS to find distances from substituent attachment point
                        distances = {ring_node: 0}
                        queue = deque([ring_node])
                        while queue:
                            curr = queue.popleft()
                            for nb2, _ in full_adj.get(curr, []):
                                if nb2 in pi_set and nb2 not in distances:
                                    distances[nb2] = distances[curr] + 1
                                    queue.append(nb2)
                        for target in pi_isl:
                            dist = distances.get(target, 0)
                            if dist == 0:      # ipso (substituent attached carbon)
                                global_charges[target] += corr_ipso
                            elif dist == 1:    # ortho
                                global_charges[target] += corr_ortho
                            elif dist == 2:    # meta
                                global_charges[target] += corr_meta
                            elif dist == 3:    # para
                                global_charges[target] += corr_para
                            else:
                                # dist > 3: fused rings — apply weak correction
                                global_charges[target] += corr_meta * 0.5

        # [Fix v3: 2026-03-10] all_aromatic 채우기 — π-island 링 위상 검사
        # 방법: π-island 서브그래프에서 edge_count >= node_count 이면 고리(방향족)
        # 근거: 링 시스템은 모든 원자가 ≥2개의 이웃을 갖고, edge_count = node_count (단순 링)
        for pi_isl in total_pi_islands:
            if len(pi_isl) < 4:  # 4원자 미만은 링 방향족 없음
                continue
            pi_set = set(pi_isl)
            edge_count = sum(
                sum(1 for item in full_adj.get(nd, []) if (item[0] if isinstance(item, (tuple, list)) else item) in pi_set)
                for nd in pi_isl
            ) // 2
            if edge_count >= len(pi_isl):
                all_aromatic.update(pi_isl)
                logger.info("[AROMATIC FIX] Ring pi-island detected: %d atoms added to all_aromatic", len(pi_isl))

        # [PLAN-CHEM-002] RDKit GetIsAromatic() fallback: 외부 smiles가 제공된 경우
        # RDKit의 방향족 판정을 직접 사용하여 all_aromatic 보강
        # 이는 캔버스에서 aromatic bond가 order=1로 저장되어 pi-island 미탐지되는 경우를 보완
        if RDKIT_AVAILABLE and smiles and not all_aromatic:
            try:
                _test_mol = Chem.MolFromSmiles(smiles)
                if _test_mol is not None:  # Rule L: None guard
                    # RDKit aromatic atom idx 수집
                    rdkit_aromatic_idxs = set()
                    for atom in _test_mol.GetAtoms():
                        if atom.GetIsAromatic():
                            rdkit_aromatic_idxs.add(atom.GetIdx())
                    if rdkit_aromatic_idxs:
                        # rdkit_idx → norm_key 매핑으로 all_aromatic 보강
                        for nk, nv in norm_atoms.items():
                            if not isinstance(nv, dict):
                                continue
                            rdkit_idx = nv.get("rdkit_idx", -1)
                            if rdkit_idx in rdkit_aromatic_idxs:
                                all_aromatic.add(nk)
                        if all_aromatic:
                            logger.info("[AROMATIC RDKIT] RDKit GetIsAromatic() fallback: %d atoms added to all_aromatic", len(all_aromatic))
                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            except Exception as e_aro:
                logger.warning("[AROMATIC RDKIT] Fallback failed: %s", e_aro)

        # [신규] 시각화를 위한 입체 중심(R/S) 분석 및 전달 데이터 확장
        # generate_smiles의 입체 인식 로직을 활용하여 결과를 추출합니다.
        smiles_str, stereo_labels, lewis_data, theory_data = self.generate_smiles(atoms, bonds)
        # [BUG-3 Fix] generate_smiles 실패 시 외부 smiles 사용 (cp-, tropylium 등 이온성 방향족)
        if not smiles_str and smiles:
            smiles_str = smiles
        
        logger.debug("[LEWIS DATA INJECTION LOG]")
        # [해결v2] 거리 기반 매칭 + nearest fallback (lp_count 누락 방지)
        for l_pt, extra in lewis_data.items():
            matched = False
            best_n_pt = None
            best_dist = float('inf')
            for n_pt in norm_atoms.keys():
                dist = math.hypot(l_pt[0] - n_pt[0], l_pt[1] - n_pt[1])
                if dist < best_dist:
                    best_dist = dist
                    best_n_pt = n_pt
                if dist < 8.0:  # 8픽셀 이내면 동일 원자
                    matched = True
                    break

            # [FIX] 8px 이내 매칭 실패 시 → 가장 가까운 원자에 강제 매칭 (15px 이내)
            target = n_pt if matched else (best_n_pt if best_dist < 15.0 else None)
            if target:
                norm_atoms[target].update(extra)

                # [TASK 2] 전하 복원: formal_charge를 attach 딕셔너리에 +/- 기호로 추가
                # [v8.1 FIX] charge 필드가 이미 설정되어 있으면 attach[-1] 중복 추가 방지
                formal_charge = extra.get("formal_charge", 0)
                existing_charge = norm_atoms[target].get("charge", "")
                if formal_charge != 0 and not existing_charge:
                    if "attach" not in norm_atoms[target]:
                        norm_atoms[target]["attach"] = {}
                    if formal_charge > 0:
                        norm_atoms[target]["attach"][-1] = "+"
                    elif formal_charge < 0:
                        norm_atoms[target]["attach"][-1] = "-"

                logger.debug("Lewis Data %s at %s (dist: %.2f) | H:%s, LP:%s, Charge:%s",
                             "MATCH" if matched else "FALLBACK", target, best_dist,
                             extra['h_count'], extra['lp_count'], formal_charge)
            else:
                logger.warning("Lewis Data FAILURE: could not find target atom for %s (nearest: %.1fpx)", l_pt, best_dist)

        # [v8.1] 암시적 수소에 의한 전기음성도 보정 (lewis_data 주입 후 h_count 사용 가능)
        # RDKit RemoveHs로 제거된 H 원자들의 유발 효과 반영
        from chem_data import ELEMENT_DATA as _ED
        for k in global_charges:
            at = norm_atoms.get(k, {})
            if not isinstance(at, dict):
                at = {}
            main_sym = at.get("main") or "C"
            h_count = at.get("h_count", 0)
            if h_count > 0 and main_sym not in ("C", "", "H"):
                _ed_atom = _ED.get(main_sym, {})
                en_atom = _ed_atom.get("negativity", 2.5) if isinstance(_ed_atom, dict) else 2.5  # Rule N
                _ed_h = _ED.get("H", {})
                en_h = _ed_h.get("negativity", 2.2) if isinstance(_ed_h, dict) else 2.2  # Rule N
                delta = (en_h - en_atom) * 0.3 * h_count
                global_charges[k] += delta  # O: 3.44 > H: 2.2 → delta 음수 → O가 δ⁻

        # [PLAN-CHEM-001] 결합 길이 Angstrom 계산
        bond_lengths = {}
        for (k1, k2), v in bonds.items():
            c1 = (round(k1[0], 2), round(k1[1], 2)) if not hasattr(k1, 'x') else (round(k1.x(), 2), round(k1.y(), 2))
            c2 = (round(k2[0], 2), round(k2[1], 2)) if not hasattr(k2, 'x') else (round(k2.x(), 2), round(k2.y(), 2))
            pk1 = self.core.find_matching_atom(c1, norm_keys)
            pk2 = self.core.find_matching_atom(c2, norm_keys)
            if pk1 and pk2:
                _bl1 = norm_atoms.get(pk1, {})
                _bl2 = norm_atoms.get(pk2, {})
                e1 = (_bl1.get("main") if isinstance(_bl1, dict) else None) or "C"
                e2 = (_bl2.get("main") if isinstance(_bl2, dict) else None) or "C"
                order = v if isinstance(v, int) else 1
                is_aro = (pk1 in all_aromatic and pk2 in all_aromatic)
                bl = self.physics.get_bond_length_angstrom(e1, e2, order, is_aromatic=is_aro)
                bond_lengths[(pk1, pk2)] = bl

        # [FIX-RINGS] 고리 목록 생성 — draw_pi_cloud_halo에서 사용
        # all_aromatic과 인접 리스트를 사용하여 개별 방향족 고리를 분리
        detected_rings = self._detect_rings(all_aromatic, full_adj)

        # [B9-2 / M222] ESP 스타일 계산 — sp3 halogen 얕게, 나머지 sp3 숨김
        # 규칙 근거: CLAUDE.md Rule O (렌더링 품질) + 사용자 피드백 uf_feedback47 B9-2
        # - sp2/sp: ESP 정상 (π-시스템, 방향족)
        # - sp3 halogen (F/Cl/Br/I): 얕게 (유도효과 약한 구름)
        # - 기타 sp3: 숨김 (포화 탄화수소는 ESP 무의미)
        esp_style_per_atom = self._build_esp_style_map(
            norm_atoms, bonds, all_aromatic, total_pi_islands, smiles,
        )

        return {
            "charges": global_charges,
            "islands": total_pi_islands,
            "aromatic": all_aromatic,
            "rings": detected_rings,
            "atoms": norm_atoms,
            "bonds": bonds,
            "adj": full_adj,
            "stereo": stereo_labels,
            "theory_data": theory_data,
            "bond_lengths": bond_lengths,
            "esp_style_per_atom": esp_style_per_atom,
        }

    # ══════════════════════════════════════════════════════════════════
    # [B9-2 / M222] ESP 표시 규칙 (sp3 halogen 얕게)
    # ══════════════════════════════════════════════════════════════════
    # Rule I: 매직넘버 주석 필수 — alpha/radius 팩터는 McMurry 교과서 ESP 맵 관찰 기반.
    # 17족 halogen (F/Cl/Br/I) 주기율표 참조. Astatine(At)은 방사성이라 제외.
    # [주의] 이 헬퍼는 class 내부 static / 인스턴스 양쪽에서 호출 가능하게 staticmethod.

    @staticmethod
    def _compute_esp_style(atom_key, element, hybridization):
        """ESP 표시 스타일 계산 (sp3 halogen 특화 규칙).

        Rule O (렌더링 품질): sp3 포화 원자는 ESP 숨김이 기본. 단, halogen은
        유도효과(C-X polar bond) 때문에 얕게 표시해야 교과서(McMurry Ch.2)와 일치.

        Args:
            atom_key: (x, y) 좌표 튜플 (Rule N: 타입 가드용)
            element: 원자 기호 ('' 탄소 포함, Rule I)
            hybridization: 'sp' / 'sp2' / 'sp3' / '' (unknown)

        Returns:
            {
              "alpha_scale": float,   # 기본 alpha에 곱할 팩터 (0.0 = 숨김)
              "radius_scale": float,  # 기본 radius에 곱할 팩터 (0.0 = 숨김)
              "show_esp": bool,       # False이면 렌더러가 continue
            }

        규칙 매트릭스:
          sp / sp2            → 정상 (1.0, 1.0, True)  — π-시스템
          sp3 + halogen       → 얕게 (0.3, 1.3, True)  — C-X 유도효과 (넓고 얕게)
          sp3 + C/H           → 숨김 (0.0, 0.0, False) — 포화 탄화수소
          sp3 + 기타 hetero   → 유지 (1.0, 1.0, True)  — O/N 등 lone pair는 표시
          unknown             → fallback (0.5, 0.8, True)
        """
        # Rule N: 타입 가드
        if not isinstance(element, str):
            element = ""
        if not isinstance(hybridization, str):
            hybridization = ""

        # 17족 halogen frozenset (주기율표 기준, At 방사성 제외)
        HALOGENS = frozenset({'F', 'Cl', 'Br', 'I'})

        # sp / sp2: π 시스템이므로 ESP 정상 표시 (방향족, 카보닐, 알킨 등)
        if hybridization in ('sp', 'sp2'):
            return {"alpha_scale": 1.0, "radius_scale": 1.0, "show_esp": True}

        # sp3 halogen: 얕게 (alpha 0.3 = 30% 투명도, radius 1.3x = 30% 넓게)
        # 근거: 사용자 피드백 B9-2 "넓고 얕게" + C-X 유도효과 교과서 도식
        if hybridization == 'sp3' and element in HALOGENS:
            return {"alpha_scale": 0.3, "radius_scale": 1.3, "show_esp": True}

        # sp3 + C/H: 숨김 (포화 탄화수소, ESP 무의미)
        # element == '' = Carbon (Rule I). 'H' 명시적 포함.
        if hybridization == 'sp3' and element in ('', 'C', 'H'):
            return {"alpha_scale": 0.0, "radius_scale": 0.0, "show_esp": False}

        # sp3 + 기타 hetero (O, N, S, P 등): lone pair 가시화 유지 (정상)
        if hybridization == 'sp3':
            return {"alpha_scale": 1.0, "radius_scale": 1.0, "show_esp": True}

        # fallback: hybridization 인식 실패 시 경고 로깅 + 중간값
        # Rule M: silent return 금지 - 원인 파악을 위해 경고 출력
        logger.warning("[ESP-STYLE WARN] Unknown hybridization '%s' for element '%s' at %s - using fallback",
                       hybridization, element, atom_key)
        return {"alpha_scale": 0.5, "radius_scale": 0.8, "show_esp": True}

    def _build_esp_style_map(self, norm_atoms, bonds, aromatic_set,
                              total_pi_islands, smiles):
        """전체 원자에 대한 ESP 스타일 맵 구축.

        Args:
            norm_atoms: dict {atom_key: {"main": str, ...}}
            bonds: dict {(k1,k2): order}
            aromatic_set: set of aromatic atom keys
            total_pi_islands: list of lists — π-island 집합
            smiles: Optional[str] — RDKit 하이브리다이제이션 조회용

        Returns:
            dict {atom_key: {"alpha_scale", "radius_scale", "show_esp"}}
        """
        # Rule N: 타입 가드
        if not isinstance(norm_atoms, dict):
            return {}
        if not isinstance(bonds, dict):
            bonds = {}

        result = {}

        # 1) RDKit 기반 hybridization 맵 (smiles 있을 때)
        #    aromatic 원자도 함께 수집해 폴백 개선에 활용.
        rdkit_hybrid_by_idx = {}
        rdkit_aromatic_idxs = set()
        if RDKIT_AVAILABLE and smiles:
            try:
                _hmol = Chem.MolFromSmiles(smiles)
                if _hmol is not None:  # Rule L: MolFromSmiles None guard
                    for atom in _hmol.GetAtoms():
                        hyb = atom.GetHybridization()
                        # RDKit HybridizationType → 문자열 정규화
                        if hyb == Chem.rdchem.HybridizationType.SP:
                            hyb_str = "sp"
                        elif hyb == Chem.rdchem.HybridizationType.SP2:
                            hyb_str = "sp2"
                        elif hyb == Chem.rdchem.HybridizationType.SP3:
                            hyb_str = "sp3"
                        else:
                            hyb_str = ""
                        rdkit_hybrid_by_idx[atom.GetIdx()] = hyb_str
                        # 방향족 원자는 RDKit 기준으로 sp2 강제 (benzene 등)
                        if atom.GetIsAromatic():
                            rdkit_aromatic_idxs.add(atom.GetIdx())
                            # aromatic atom은 반드시 sp2
                            rdkit_hybrid_by_idx[atom.GetIdx()] = "sp2"
                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            except Exception as e_hyb:
                # Rule M: silent failure 금지 - 경고 출력 (fallback 계속 진행)
                logger.warning("[ESP-STYLE WARN] RDKit hybridization failed: %s", e_hyb)

        # 2) π-island 멤버십 맵 (폴백 hybridization 추정용)
        pi_member = set()
        for isl in total_pi_islands:
            for k in isl:
                pi_member.add(k)

        # 3) 각 원자에 대해 hybridization 결정 후 style 계산
        for pt_key, at_data in norm_atoms.items():
            # Rule N: at_data dict 타입 가드
            if not isinstance(at_data, dict):
                at_data = {}

            element = at_data.get("main", "") or ""
            # Rule N: element str 가드
            if not isinstance(element, str):
                element = ""

            # hybridization 추정:
            #   (a) RDKit rdkit_idx 있으면 정확한 값 사용
            #   (b) 없으면 aromatic/π-island/결합차수 기반 폴백
            hybridization = ""
            rdkit_idx = at_data.get("rdkit_idx", -1)
            if isinstance(rdkit_idx, int) and rdkit_idx >= 0:
                hybridization = rdkit_hybrid_by_idx.get(rdkit_idx, "")

            if not hybridization:
                # 폴백: aromatic → sp2, π-island 멤버 → sp2 추정
                if pt_key in aromatic_set or pt_key in pi_member:
                    hybridization = "sp2"
                else:
                    # 결합 차수 조사: 3중 결합 있으면 sp, 2중 있으면 sp2, 전부 단일이면 sp3
                    max_order = 1
                    for (k1, k2), bdata in bonds.items():
                        if k1 == pt_key or k2 == pt_key:
                            bo = bdata if isinstance(bdata, (int, float)) else 1
                            if bo > max_order:
                                max_order = bo
                    if max_order >= 3:
                        hybridization = "sp"
                    elif max_order >= 2:
                        hybridization = "sp2"
                    else:
                        hybridization = "sp3"

            # style 계산
            result[pt_key] = ChemicalAnalyzer._compute_esp_style(
                pt_key, element, hybridization,
            )

        return result

    def _ring_topology_distance(self, start, pi_island, adj):
        """BFS로 ring 내 위상 거리 계산 (ortho=1, meta=2, para=3)"""
        # [M152 FIX] 로컬 재할당 금지: 함수 내 'adj = {}' 대입은 UnboundLocalError 유발.
        _adj_safe = adj if isinstance(adj, dict) else {}
        distances = {start: 0}
        queue = [start]
        while queue:
            curr = queue.pop(0)
            for neighbor, _ in _adj_safe.get(curr, []):
                if neighbor in pi_island and neighbor not in distances:
                    distances[neighbor] = distances[curr] + 1
                    queue.append(neighbor)
        return distances

    def _detect_rings(self, aromatic_atoms, adj):
        """방향족 원자 집합에서 개별 고리(ring)를 분리하여 리스트로 반환.

        알고리즘: 방향족 서브그래프에서 BFS 기반 최소 고리 탐지.
        각 고리는 원자 좌표 튜플의 리스트.

        Args:
            aromatic_atoms: set of (x, y) tuples — 방향족 원자
            adj: {atom_key: [(neighbor_key, bond_info), ...]} — 인접 리스트

        Returns:
            list[list[tuple]]: 각 원소가 하나의 고리를 구성하는 원자 키 리스트
        """
        if not aromatic_atoms or not adj:
            return []

        # [M152 FIX] 로컬 재할당 금지: 루프 내 'adj = {}' / 'aro_adj = {}' 대입은
        # Python이 해당 이름 전체를 로컬로 처리 → 첫 접근 시 UnboundLocalError.
        _adj_safe = adj if isinstance(adj, dict) else {}

        # 방향족 원자만의 서브그래프 인접 리스트 구성
        aro_adj = {}
        for node in aromatic_atoms:
            neighbors = []
            for nb, _ in _adj_safe.get(node, []):
                if nb in aromatic_atoms:
                    neighbors.append(nb)
            aro_adj[node] = neighbors

        # Rule N: aro_adj는 위에서 구축한 dict (isinstance 가드)
        if not isinstance(aro_adj, dict):
            aro_adj = {}
        # 모든 최소 고리를 찾기 위한 BFS 기반 알고리즘
        # 각 에지에 대해 에지를 제외한 최단 경로가 있으면 고리
        found_rings = []
        found_ring_sets = []  # 중복 검사용

        for start_node in aromatic_atoms:
            for neighbor in aro_adj.get(start_node, []):
                # start_node → neighbor 직접 연결을 제외하고 우회 최단경로 탐색
                # 최대 8원자 고리까지
                from collections import deque
                visited = {start_node}
                queue = deque([(start_node, [start_node])])
                while queue:
                    current, path = queue.popleft()
                    for nb in aro_adj.get(current, []):
                        if current == start_node and nb == neighbor:
                            continue  # 직접 연결 제외
                        if nb == neighbor and len(path) >= 2:
                            ring = path + [neighbor]
                            if len(ring) <= 8:  # 8원자 고리까지
                                ring_set = frozenset(ring)
                                if ring_set not in found_ring_sets:
                                    found_ring_sets.append(ring_set)
                                    found_rings.append(list(ring_set))
                            break
                        if nb not in visited and len(path) < 8:
                            visited.add(nb)
                            queue.append((nb, path + [nb]))

        return found_rings

    def generate_smiles(self, atoms, bonds):
        # [가드] RDKit 미설치 시 빈 데이터 반환 (graceful fallback)
        if not RDKIT_AVAILABLE:
            logger.warning("[WARNING] RDKit not available - SMILES generation skipped")
            return "", {}, {}, {"coords": {}, "bonds": []}

        # [STAGE 1] 원자 및 결합 복구 (ID 기반 무결성)
        # [해결] 반올림을 2자리(0.01)로 통일하여 t_map 매칭 실패 원천 차단
        def get_pos(p): return (round(p.x(), 2), round(p.y(), 2)) if hasattr(p, 'x') else (round(p[0], 2), round(p[1], 2))
        mol = Chem.RWMol(); node_to_idx, idx_to_coord = {}, {}

        # 1. 메인 원자 생성
        sorted_keys = sorted(atoms.keys(), key=lambda k: (get_pos(k)[1], get_pos(k)[0]))
        for k in sorted_keys:
            pos = get_pos(k); data = atoms[k]
            if not isinstance(data, dict):
                data = {}
            atom = Chem.Atom(data.get("main") or "C")

            # [Fix v2] 전하 보존: 'charge' 필드 우선, attach는 d==-1 lewis주입 제외 보조
            formal_charge = 0
            _cf = data.get("charge", "")
            if _cf == "+":
                formal_charge = 1
            elif _cf == "-":
                formal_charge = -1
            else:
                _att_gs = data.get("attach", {})
                if not isinstance(_att_gs, dict):
                    _att_gs = {}
                for _d, _sym in _att_gs.items():
                    if _d == -1:
                        continue
                    if _sym == "+":
                        formal_charge += 1
                    elif _sym == "-":
                        formal_charge -= 1
            atom.SetFormalCharge(formal_charge)

            # [Fix v2] 라디칼 전자 반영 (attach에 "·" 기호)
            _att_rad = data.get("attach", {})
            if not isinstance(_att_rad, dict):
                _att_rad = {}
            _rad = sum(1 for _d, _sym in _att_rad.items()
                       if _sym == "·" and _d != -1)
            if _rad > 0:
                atom.SetNumRadicalElectrons(_rad)

            idx = mol.AddAtom(atom)
            node_to_idx[pos] = idx; idx_to_coord[idx] = list(pos) + [0.0]

            # [M764 A70-W1 F5-1 item4] attach H → SetNumExplicitHs (Rule L+M)
            # 사용자 격분: "우측 말단 산소만 수소 안붙어서 나온다"
            # Fix v2에서 implicit H로만 처리했으나 터미널 산소처럼 RDKit valence가
            # 이미 채워진 원자에서 explicit H가 SMILES에 반영되지 않는 문제 존재.
            # 해결: attach["H"] 개수만큼 SetNumExplicitHs + SetNoImplicit(True)로 강제 기록.
            # Rule L: MolFromSmiles+None체크는 STAGE 3 sanitize에서 이미 처리됨.
            _att_h = data.get("attach", {})
            if not isinstance(_att_h, dict):
                _att_h = {}
            _explicit_h_count = sum(1 for _d2, _sym2 in _att_h.items()
                                    if _sym2 == "H" and _d2 != -1)
            if _explicit_h_count > 0:
                _at_ref = mol.GetAtomWithIdx(idx)
                _at_ref.SetNumExplicitHs(_explicit_h_count)  # [MAGIC: attach H count] M764
                _at_ref.SetNoImplicit(True)  # [MAGIC: True] implicit H 자동 추가 차단 → 중복 방지
                logger.debug(
                    "[M764] %s pos=%r attach explicit H=%d 설정 완료",
                    data.get("main", "C"), pos, _explicit_h_count
                )

        # [STAGE 2] 결합 주입 및 '역방향 입체 논리' 적용
        for (k1, k2), v in bonds.items():
            i1, i2 = node_to_idx.get(get_pos(k1)), node_to_idx.get(get_pos(k2))
            if i1 is not None and i2 is not None:
                b_type = v[2] if (isinstance(v, tuple) and len(v) > 2) else "Bond"
                order = v[1] if isinstance(v, tuple) else (v if isinstance(v, int) else 1)
                mol.AddBond(i1, i2, Chem.rdchem.BondType.SINGLE if order != 2 else Chem.rdchem.BondType.DOUBLE)
                
                # 판별 논리: 그리기 방향(i1->i2)과 중심 탄소 위치에 따른 Z축 결정
                # i1: 뾰족한 곳, i2: 넓은 면
                if b_type == "Wedge":
                    # Wedge가 중심에서 뻗어나가면(i1=Center) 끝점이 Forward(+1.5)
                    idx_to_coord[i2][2] = 1.5
                    # Wedge가 중심으로 들어오면(i2=Center) 시작점이 Backward(-1.5)
                    idx_to_coord[i1][2] = -1.5
                elif b_type == "Dash":
                    # Dash가 중심에서 뻗어나가면(i1=Center) 끝점이 Backward(-1.5)
                    idx_to_coord[i2][2] = -1.5
                    # Dash가 중심으로 들어오면(i2=Center) 시작점이 Forward(+1.5)
                    idx_to_coord[i1][2] = 1.5

        # [STAGE 3] RDKit 3D 분석 및 SMILES 동기화
        try:
            final_mol = mol.GetMol(); final_mol.UpdatePropertyCache(strict=False)
            conf = Chem.Conformer(final_mol.GetNumAtoms())
            for idx, c3d in idx_to_coord.items():
                # [핵심] Y축 반전에 따른 거울상 오류 해결을 위해 Z축 부호도 반전 (-c3d[2])
                conf.SetAtomPosition(idx, (c3d[0]/20.0, -c3d[1]/20.0, -c3d[2]))
            final_mol.AddConformer(conf)
            
            # 3D 입체 배향 분석
            Chem.AssignStereochemistryFrom3D(final_mol)
            ranks = list(Chem.rdmolfiles.CanonicalRankAtoms(final_mol, breakTies=False))
            stereo_map = {}

            logger.debug("[CHIRALITY AUDIT LOG]")
            for atom in final_mol.GetAtoms():
                if not atom.HasProp("_CIPCode"): continue

                # [강력 필터] 4개 치환기의 랭킹이 중복되면(아키랄) 강제 기각
                nb_ranks = sorted([ranks[nb.GetIdx()] for nb in atom.GetNeighbors()])
                if len(set(nb_ranks)) < atom.GetDegree():
                    logger.debug("CHIRALITY REJECTED: Atom %d is achiral (Ranks: %s)", atom.GetIdx(), nb_ranks)
                    atom.ClearProp("_CIPCode")
                    atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
                    continue

                # 통과된 센터만 처리
                label = atom.GetProp("_CIPCode")
                tag = Chem.ChiralType.CHI_TETRAHEDRAL_CW if label == "R" else Chem.ChiralType.CHI_TETRAHEDRAL_CCW
                atom.SetChiralTag(tag)

                c_pos = idx_to_coord[atom.GetIdx()]
                stereo_map[(round(c_pos[0], 1), round(c_pos[1], 1) - 0.1)] = f"({label})"
                logger.debug("CHIRALITY CONFIRMED: %s center at %s | Ranks: %s", label, c_pos[:2], nb_ranks)

            out_mol = Chem.RemoveHs(final_mol)
            smiles = Chem.MolToSmiles(out_mol, isomericSmiles=True)

            # [M722-5 F4-0 item1] R/S 재발 방지 교차 검증.
            # 사용자 격분: "R배열 S배열 표현이 반대로 되고 있지 않은지 코드 확인이 필요"
            # 3D conformer 기반 AssignStereochemistryFrom3D 결과와 SMILES @/@@ 표기가 일치하는지
            # 교차 검증하여 Y축 반전 오류 재발 시 즉시 logger.warning으로 탐지.
            # 학술 근거: Cahn-Ingold-Prelog 1966 Angew. Chem. 78:413 (CIP 우선순위 규칙).
            try:
                _v_mol = Chem.MolFromSmiles(smiles)
                if _v_mol is not None:
                    Chem.AssignStereochemistry(_v_mol, cleanIt=True, force=True)
                    _smiles_cip = {
                        int(at.GetIdx()): at.GetProp("_CIPCode")
                        for at in _v_mol.GetAtoms()
                        if at.HasProp("_CIPCode")
                    }
                    # 3D 기반 stereo_map의 label 목록
                    _3d_labels = set(v.strip("()") for v in stereo_map.values())
                    _smiles_labels = set(_smiles_cip.values())
                    if _3d_labels and _smiles_labels and _3d_labels != _smiles_labels:
                        logger.warning(
                            "[M722-5] R/S 교차검증 불일치 — 3D 기반=%s, SMILES 기반=%s. "
                            "Y축 반전 오류 재발 가능성. conf Y=-c3d[1] 설정 확인 요망.",
                            sorted(_3d_labels), sorted(_smiles_labels)
                        )
                    else:
                        logger.debug("[M722-5] R/S 교차검증 일치 — 3D=%s == SMILES=%s",
                                     sorted(_3d_labels), sorted(_smiles_labels))
                else:
                    logger.warning("[Rule L] MolFromSmiles 실패: %r", smiles)
            except Exception as _v_e:
                logger.debug("[M722-5] R/S 교차검증 예외 (무시): %s", _v_e)

            # [추가] 루이스 구조용 H 및 비공유 전자쌍 데이터 생성
            # [M4 수정] 중복 루프 통합 — 단일 루프로 lewis_map 생성
            lewis_map = {}
            logger.debug("[RDKIT ATOM ANALYSIS]")
            for atom in final_mol.GetAtoms():
                if atom.GetSymbol() == "H": continue
                pos = idx_to_coord[atom.GetIdx()]
                pt_key = (round(pos[0], 2), round(pos[1], 2))

                outer_elecs = Chem.GetPeriodicTable().GetNOuterElecs(atom.GetAtomicNum())
                bonds_val = atom.GetTotalValence()
                formal_charge = atom.GetFormalCharge()
                lp = max(0, (outer_elecs - bonds_val - formal_charge) // 2)

                # [TASK 2] 전하 보존: formal_charge를 lewis_map에 저장
                lewis_map[pt_key] = {
                    "h_count": atom.GetTotalNumHs(),
                    "lp_count": int(lp),
                    "formal_charge": formal_charge
                }
                logger.debug("Atom %s at %s: Outer:%d, Bonded:%d, LP:%d, Charge:%d",
                             atom.GetSymbol(), pt_key, outer_elecs, bonds_val, lp, formal_charge)

            # [Step 3 개선] Procrustes 정렬 기반 이론적 좌표 산출 (v6.11)
            theory_data = {"coords": {}, "bonds": []}
            try:
                temp_mol = Chem.Mol(final_mol)
                rdDepictor.Compute2DCoords(temp_mol)
                conf = temp_mol.GetConformer()
                
                # 1. 분자별 연결 성분 탐색 (각 독립 분자를 개별 처리)
                from rdkit.Chem import rdmolops
                mol_frags = rdmolops.GetMolFrags(temp_mol, asMols=False)
                
                theory_map = {}
                
                # 2. 각 분자 조각마다 Procrustes 정렬로 방향/스케일 보존
                for frag_atoms in mol_frags:
                    if not frag_atoms:
                        continue
                    
                    # 2-1. 원본 좌표 수집 (screen 좌표계)
                    orig_pts = [(idx_to_coord[i][0], idx_to_coord[i][1]) for i in frag_atoms]
                    
                    # 2-2. RDKit 좌표 수집 (y축 반전하여 screen 좌표계로 변환)
                    rdkit_pts = [(conf.GetAtomPosition(i).x, -conf.GetAtomPosition(i).y) for i in frag_atoms]
                    
                    # 2-3. Procrustes 정렬 (회전 + 스케일 + 평행이동)
                    if NUMPY_AVAILABLE and len(frag_atoms) >= 2:
                        aligned = self._align_to_original(orig_pts, rdkit_pts)
                    else:
                        # numpy 미설치 fallback: 평행이동만 수행 (기존 동작)
                        orig_cx = sum(p[0] for p in orig_pts) / len(orig_pts)
                        orig_cy = sum(p[1] for p in orig_pts) / len(orig_pts)
                        rdk_cx = sum(p[0] for p in rdkit_pts) / len(rdkit_pts)
                        rdk_cy = sum(p[1] for p in rdkit_pts) / len(rdkit_pts)
                        # fallback에서는 원본 결합길이 기반 동적 스케일 사용
                        _fb_scale = self._compute_dynamic_scale(orig_pts, rdkit_pts)
                        aligned = [(orig_cx + (rx - rdk_cx) * _fb_scale, 
                                    orig_cy + (ry - rdk_cy) * _fb_scale) for rx, ry in rdkit_pts]
                    
                    # 2-4. 정렬된 좌표를 theory_data에 저장
                    for idx_in_frag, i in enumerate(frag_atoms):
                        orig_pt = (round(idx_to_coord[i][0], 2), round(idx_to_coord[i][1], 2))
                        ax, ay = aligned[idx_in_frag]
                        new_pos = QPointF(round(ax, 2), round(ay, 2))
                        theory_data["coords"][i] = new_pos
                        theory_map[orig_pt] = new_pos

                theory_data["map"] = theory_map
                
                # 3. 최적화된 결합 목록 추출
                for bond in temp_mol.GetBonds():
                    theory_data["bonds"].append((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), bond.GetBondType()))
            except Exception as te:
                logger.warning("[THEORY ERROR] %s", te)

            logger.info("[FINAL RESULT] SMILES: %s", smiles)
            # [해결] 루이스 정보와 이론적 최적화 데이터를 함께 반환
            return smiles, stereo_map, lewis_map, theory_data

        except Exception as e:
            # [해결] 짝이 맞지 않던 try-except 구문 완결 및 빈 데이터 반환
            logger.warning("[ERROR] generate_smiles failure: %s", e)
            return "", {}, {}, {"coords": {}, "bonds": []}

    def _align_to_original(self, orig_coords, rdkit_coords):
        """Procrustes 정렬: RDKit 좌표를 원본 그리기 좌표의 방향/스케일에 맞춤 (SVD 기반)
        
        Args:
            orig_coords: list of (x, y) — 원본 그리기 좌표 (target)
            rdkit_coords: list of (x, y) — RDKit 생성 좌표 (source)
        
        Returns:
            list of [x, y] — 정렬된 좌표
        """
        if len(orig_coords) < 2 or len(rdkit_coords) < 2:
            return rdkit_coords
        
        P = np.array(orig_coords, dtype=float)   # 원본 (target)
        Q = np.array(rdkit_coords, dtype=float)   # RDKit (source)
        
        # 1. 중심점 계산
        P_center = P.mean(axis=0)
        Q_center = Q.mean(axis=0)
        
        # 2. 중심을 원점으로 이동
        P_centered = P - P_center
        Q_centered = Q - Q_center
        
        # 3. 스케일 계산 (원본 스케일 유지)
        P_scale = np.sqrt((P_centered ** 2).sum() / len(P))
        Q_scale = np.sqrt((Q_centered ** 2).sum() / len(Q))
        
        if Q_scale < 1e-10:
            return rdkit_coords
        
        scale = P_scale / Q_scale
        Q_scaled = Q_centered * scale
        
        # 4. 최적 회전 행렬 계산 (SVD)
        H = Q_scaled.T @ P_centered
        U, S, Vt = np.linalg.svd(H)
        
        # 반전 방지 (거울상 허용 안 함)
        d = np.linalg.det(Vt.T @ U.T)
        sign_matrix = np.eye(2)
        sign_matrix[1, 1] = np.sign(d)
        
        R = Vt.T @ sign_matrix @ U.T  # 회전 행렬
        
        # 5. 변환 적용: 스케일된 좌표 회전 → 원본 중심으로 이동
        aligned = (Q_scaled @ R.T) + P_center
        
        return aligned.tolist()

    @staticmethod
    def _compute_dynamic_scale(orig_pts, rdkit_pts):
        """원본/RDKit 좌표 간 평균 결합길이 비율로 동적 스케일 계산 (numpy 미설치 fallback)
        
        Args:
            orig_pts: list of (x, y) — 원본 좌표
            rdkit_pts: list of (x, y) — RDKit 좌표
        
        Returns:
            float — 스케일 팩터 (기본값 45.0)
        """
        if len(orig_pts) < 2 or len(rdkit_pts) < 2:
            return 45.0
        
        # 원본 좌표 쌍 간 평균 거리
        orig_dists = []
        rdk_dists = []
        for i in range(len(orig_pts)):
            for j in range(i + 1, len(orig_pts)):
                od = math.hypot(orig_pts[i][0] - orig_pts[j][0], orig_pts[i][1] - orig_pts[j][1])
                rd = math.hypot(rdkit_pts[i][0] - rdkit_pts[j][0], rdkit_pts[i][1] - rdkit_pts[j][1])
                if rd > 1e-10:
                    orig_dists.append(od)
                    rdk_dists.append(rd)
        
        if not rdk_dists:
            return 45.0
        
        avg_orig = sum(orig_dists) / len(orig_dists)
        avg_rdk = sum(rdk_dists) / len(rdk_dists)
        
        return avg_orig / avg_rdk if avg_rdk > 1e-10 else 45.0

    def _get_adj(self, atoms, bonds):
        adj = {k: [] for k in atoms.keys()}
        atom_keys = list(atoms.keys())
        for (k1, k2), v in bonds.items():
            # [수정] 3.chem의 리스트 형식 좌표와 부동 소수점 오차(0.0000000002)를 모두 해결
            # 좌표가 리스트인 경우를 대비해 인덱스로 접근하여 정규화합니다.
            c1 = (round(k1[0], 2), round(k1[1], 2))
            c2 = (round(k2[0], 2), round(k2[1], 2))
            
            # find_matching_atom을 통해 미세 오차 범위 내의 원자를 탐색합니다.
            pk1 = self.core.find_matching_atom(c1, atom_keys)
            pk2 = self.core.find_matching_atom(c2, atom_keys)
            
            if pk1 and pk2:
                order = v if isinstance(v, int) else 1
                adj[pk1].append((pk2, order)); adj[pk2].append((pk1, order))
        return adj

    def _get_molecular_islands(self, keys, adj):
        visited = set(); mols = []
        for node in keys:
            if node not in visited:
                mol = set(); stack = [node]
                while stack:
                    curr = stack.pop()
                    if curr not in mol:
                        mol.add(curr); visited.add(curr)
                        for n, _ in adj.get(curr, []): stack.append(n)
                mols.append(mol)
        return mols


# ══════════════════════════════════════════════════════════════════
# [NEW] 분자 물성 계산 함수 (RDKit 기반)
# ══════════════════════════════════════════════════════════════════

def calculate_logp(smiles: str) -> float:
    """SMILES로부터 LogP (Wildman-Crippen partition coefficient)를 계산합니다.

    Args:
        smiles: 분자의 SMILES 문자열

    Returns:
        LogP 값 (float). 계산 실패 시 0.0 반환.
    """
    if not RDKIT_AVAILABLE:
        logger.warning("[LogP] RDKit not available")
        return 0.0
    try:
        from rdkit.Chem import Crippen
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[LogP] Invalid SMILES: %s", smiles)
            return 0.0
        return Crippen.MolLogP(mol)
    except Exception as e:
        logger.warning("[LogP] Calculation error: %s", e)
        return 0.0


def calculate_tpsa(smiles: str) -> float:
    """SMILES로부터 TPSA (Topological Polar Surface Area)를 계산합니다.

    Args:
        smiles: 분자의 SMILES 문자열

    Returns:
        TPSA 값 (Angstrom^2). 계산 실패 시 0.0 반환.
    """
    if not RDKIT_AVAILABLE:
        logger.warning("[TPSA] RDKit not available")
        return 0.0
    try:
        from rdkit.Chem import Descriptors
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[TPSA] Invalid SMILES: %s", smiles)
            return 0.0
        return Descriptors.TPSA(mol)
    except Exception as e:
        logger.warning("[TPSA] Calculation error: %s", e)
        return 0.0


def calculate_rotatable_bonds(smiles: str) -> int:
    """SMILES로부터 회전 가능 결합 수를 계산합니다.

    Args:
        smiles: 분자의 SMILES 문자열

    Returns:
        회전 가능 결합 수 (int). 계산 실패 시 0 반환.
    """
    if not RDKIT_AVAILABLE:
        logger.warning("[RotBonds] RDKit not available")
        return 0
    try:
        from rdkit.Chem import Lipinski
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("[RotBonds] Invalid SMILES: %s", smiles)
            return 0
        return Lipinski.NumRotatableBonds(mol)
    except Exception as e:
        logger.warning("[RotBonds] Calculation error: %s", e)
        return 0


# ===========================================================================
# [M628] 3-Tier Electron Density Wrapper: ORCA -> xtb -> Gasteiger
# ===========================================================================
# Academic citations (Rule NN):
#   Tier 1 - Mulliken: Mulliken, R.S. (1955) J. Chem. Phys. 23, 1833.
#             Lowdin: Lowdin, P.O. (1950) J. Chem. Phys. 18, 365.
#   Tier 2 - GFN2-xTB: Bannwarth, C.; Ehlert, S.; Grimme, S. (2019)
#             J. Chem. Theory Comput. 15, 1652-1671.
#   Tier 3 - Gasteiger: Gasteiger, J.; Marsili, M. (1980)
#             Tetrahedron 36, 3219-3228.
# ===========================================================================

_TIER_RESULT_TIER1 = "ORCA_MULLIKEN"   # ORCA DFT Mulliken population analysis
_TIER_RESULT_TIER2 = "XTB_MULLIKEN"    # GFN2-xTB semi-empirical Mulliken charges
_TIER_RESULT_TIER3 = "GASTEIGER"       # Gasteiger-Marsili empirical (simulation)

# FP-15 R-20: Tier 3 (Gasteiger) 사용 시 반드시 시뮬레이션 배너 표시
SIMULATION_MODE_BANNER = (
    "[SIMULATION] Gasteiger 전하 (경험적 추정, ORCA/xtb 미설치). "
    "정밀 DFT 전자분포는 데스크톱 ChemGrid에서 ORCA 설치 후 이용하십시오. "
    "Gasteiger & Marsili, Tetrahedron 1980, 36, 3219-3228."
)


def compute_electron_density_3tier(
    smiles,
    atoms=None,
    orca_population_data=None,
    charge=0,
    timeout_xtb=60,  # [MAGIC: 60s] xtb 계산 최대 허용 시간
):
    """3-tier ESP 전자밀도/부분전하 계산.

    Tier 1 (ORCA DFT Mulliken): orca_population_data 제공 시 즉시 반환.
    Tier 2 (GFN2-xTB Mulliken): xtb CLI 설치 시 subprocess 실행.
    Tier 3 (Gasteiger): fallback — RDKit Gasteiger 전하 (SIMULATION_MODE 배너).

    Rule M: silent failure 금지.
    Rule N: 외부 입력 isinstance 가드.
    Rule L: SMILES 파싱 후 None 체크 필수.

    Returns:
        (charges_dict, tier_name, citation)
        charges_dict: {atom_idx(int): float}, tier_name: str, citation: str
    """
    # Rule N: SMILES 타입 가드
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("[M628] compute_electron_density_3tier: smiles 비어있음")
        return {}, _TIER_RESULT_TIER3, SIMULATION_MODE_BANNER

    # --- Tier 1: ORCA Mulliken ---
    if isinstance(orca_population_data, dict) and len(orca_population_data) > 0:
        charges = {}
        valid = True
        for k, v in orca_population_data.items():
            if not isinstance(k, int) or not isinstance(v, dict):
                valid = False
                break
            c = v.get("mulliken_charge")
            if not isinstance(c, (int, float)):
                valid = False
                break
            charges[k] = float(c)
        if valid and charges:
            logger.debug("[M628] Tier 1 (ORCA Mulliken): %d atoms", len(charges))
            citation = (
                "Mulliken, R.S. (1955) J. Chem. Phys. 23, 1833. "
                "Lowdin, P.O. (1950) J. Chem. Phys. 18, 365."
            )
            return charges, _TIER_RESULT_TIER1, citation
        logger.warning("[M628] Tier 1 orca_population_data 형식 오류 -> Tier 2 폴백")

    # --- Tier 2: GFN2-xTB Mulliken ---
    xtb_charges = _try_xtb_mulliken(
        smiles=smiles, atoms=atoms, charge=charge, timeout=timeout_xtb
    )
    if xtb_charges:
        logger.debug("[M628] Tier 2 (GFN2-xTB Mulliken): %d atoms", len(xtb_charges))
        citation = (
            "Bannwarth, C.; Ehlert, S.; Grimme, S. (2019) "
            "J. Chem. Theory Comput. 15, 1652-1671."
        )
        return xtb_charges, _TIER_RESULT_TIER2, citation

    # --- Tier 3: Gasteiger fallback ---
    gasteiger_charges = _try_gasteiger_charges(smiles)
    if gasteiger_charges:
        logger.warning("[M628] Tier 3 (Gasteiger fallback) SIMULATION_MODE")
        citation = (
            "Gasteiger, J.; Marsili, M. (1980) Tetrahedron 36, 3219-3228. "
            "[SIMULATION - ORCA/xtb 미설치 경험적 추정값]"
        )
        return gasteiger_charges, _TIER_RESULT_TIER3, citation

    logger.warning("[M628] 3-tier 모두 실패 -> 빈 dict")
    return {}, _TIER_RESULT_TIER3, SIMULATION_MODE_BANNER


def _try_xtb_mulliken(smiles, atoms=None, charge=0, timeout=60):
    """GFN2-xTB CLI 호출 -> Mulliken 전하.

    Rule JJ: cmd 창 노출 금지 - CREATE_NO_WINDOW + STARTF_USESHOWWINDOW.
    Rule M: 실패시 logger.warning + 빈 dict.
    M158: text=False + decode('utf-8', errors='replace') - cp949 크래시 방지.
    """
    # [M646_BINS] xtb 자동 탐지: shutil.which → CHEMGRID 절대경로 폴백 → .env XTB_PATH → WSL
    xtb_exe = shutil.which("xtb")
    if xtb_exe is None:
        # Rule I: 매직넘버 주석 — ChemGrid 표준 bin 절대경로 (M646_BINS)
        _CHEMGRID_XTB_FALLBACK = r"C:/chemgrid/bin/xtb/xtb-6.7.1/bin/xtb.exe"
        if Path(_CHEMGRID_XTB_FALLBACK).is_file():
            xtb_exe = _CHEMGRID_XTB_FALLBACK
            logger.debug("[M646_BINS] xtb 절대경로 폴백 사용: %s", xtb_exe)
    if xtb_exe is None:
        # .env XTB_PATH 변수 시도 (사용자 정의 경로)
        _env_xtb = os.environ.get("XTB_PATH", "").strip()
        if _env_xtb and Path(_env_xtb).is_file():
            xtb_exe = _env_xtb
            logger.debug("[M646_BINS] xtb env path 사용: %s", xtb_exe)
    if xtb_exe is None:
        xtb_exe = _find_xtb_wsl()
    if xtb_exe is None:
        # Rule M: silent failure 금지 - logger.warning 의무
        logger.warning("[M628] xtb 미설치 - Tier 2 건너뜀 (fallback: Gasteiger). "
                       "설치: C:/chemgrid/bin/xtb/xtb-6.7.1/bin/xtb.exe 또는 .env XTB_PATH")
        return {}

    if not RDKIT_AVAILABLE:
        logger.warning("[M628] RDKit 미설치 - xtb XYZ 생성 불가")
        return {}

    # Rule L: SMILES 파싱 + None 체크
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("[M628] xtb: SMILES 파싱 실패: %s", smiles)
        return {}

    try:
        xyz_content = _smiles_to_xyz_content(mol, charge)
    except Exception as e:
        logger.warning("[M628] XYZ 생성 실패: %s", e)
        return {}

    with tempfile.TemporaryDirectory(prefix="chemgrid_m628_") as tmpdir:
        xyz_path = Path(tmpdir) / "mol.xyz"
        xyz_path.write_text(xyz_content, encoding="utf-8")

        # Rule JJ: cmd 창 노출 금지
        si = None
        creationflags = 0
        import sys as _sys
        if _sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        cmd = [xtb_exe, str(xyz_path), "--gfn", "2",
               "--chrg", str(charge), "--norestart"]
        try:
            # M158: text=False + bytes decode -> cp949 크래시 방지
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=timeout,
                cwd=tmpdir,
                startupinfo=si,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired:
            logger.warning("[M628] xtb 타임아웃 (%ds)", timeout)
            return {}
        except Exception as e:
            logger.warning("[M628] xtb 실행 오류: %s", e)
            return {}

        if result.returncode != 0:
            stderr_txt = result.stderr.decode("utf-8", errors="replace")
            logger.warning("[M628] xtb 비정상 종료 (rc=%d): %s",
                           result.returncode, stderr_txt[:200])
            return {}

        stdout_txt = result.stdout.decode("utf-8", errors="replace")
        charges = _parse_xtb_stdout_charges(stdout_txt)
        if not charges:
            logger.warning("[M628] xtb stdout Mulliken 파싱 결과 없음")
        return charges


def _find_xtb_wsl():
    """WSL에서 xtb 경로 탐색. 없으면 None.

    Rule JJ: cmd 창 없음.
    M158: text=False + decode.
    """
    import sys as _sys
    si = None
    creationflags = 0
    if _sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        creationflags = 0x08000000
    try:
        result = subprocess.run(
            ["wsl", "--", "which", "xtb"],
            capture_output=True, text=False, timeout=5,
            startupinfo=si, creationflags=creationflags,
        )
        path = result.stdout.decode("utf-8", errors="replace").strip()
        if path and path.startswith("/"):
            return "wsl::" + path
    except Exception as e:
        logger.debug("[M628] WSL xtb 탐색 실패: %s", e)
    return None


def _smiles_to_xyz_content(mol, charge=0):
    """RDKit mol -> XYZ 문자열 (MMFF 3D 최적화).

    Rule L: mol None 체크는 호출부 책임 (assert으로 명시).
    """
    from rdkit.Chem import AllChem
    assert mol is not None, "mol must not be None"  # Rule N

    mol_h = AllChem.AddHs(mol)
    embed_result = AllChem.EmbedMolecule(mol_h, AllChem.ETKDGv3())
    if embed_result != 0:
        embed_result = AllChem.EmbedMolecule(mol_h, AllChem.ETKDG())
    if embed_result != 0:
        raise ValueError("3D embedding 실패 (embed_result=%d)" % embed_result)

    # [MAGIC: 200] MMFF 최대 최적화 스텝 (빠른 수렴 우선)
    ff_result = AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
    if ff_result == -1:
        logger.warning("[M628] MMFF 최적화 불가 - 최적화 전 좌표 사용")

    conf = mol_h.GetConformer()
    n_atoms = mol_h.GetNumAtoms()
    lines = [str(n_atoms), "charge=%d XYZ (ChemGrid M628)" % charge]
    for i in range(n_atoms):
        pos = conf.GetAtomPosition(i)
        sym = mol_h.GetAtomWithIdx(i).GetSymbol()
        lines.append("%-2s  %12.6f  %12.6f  %12.6f" % (sym, pos.x, pos.y, pos.z))
    return "\n".join(lines)


def _parse_xtb_stdout_charges(stdout):
    """xtb stdout -> {atom_idx: mulliken_charge} 파싱.

    xtb GFN2 출력 형식 패턴 2종:
      Pattern A (Mulliken/CM5 블록):
        Mulliken/CM5 charges         n(s)   n(p)   n(d)
           1 C     -0.1234  0.0000  ...
      Pattern B (#Z covCN q 헤더):
        #   Z          covCN         q      C6AA      alpha(0)
           1   6 C   3.xxx   -0.123  ...

    Rule N: 파싱 실패시 빈 dict (호출부에서 logger.warning).
    """
    charges = {}
    in_mulliken_block = False
    in_charges_block = False

    for line in stdout.splitlines():
        stripped = line.strip()

        # Pattern A 블록 진입
        if "Mulliken/CM5 charges" in stripped:
            in_mulliken_block = True
            in_charges_block = False
            continue

        # Pattern B 헤더 진입
        if (stripped.startswith("#") and "Z" in stripped
                and "covCN" in stripped and "q" in stripped):
            in_charges_block = True
            in_mulliken_block = False
            continue

        # 블록 종료
        if in_mulliken_block or in_charges_block:
            if stripped == "" or stripped.startswith("--"):
                in_mulliken_block = False
                in_charges_block = False
                continue

        if in_mulliken_block:
            # "   1 C     -0.1234  0.0000  ..."
            parts = stripped.split()
            if len(parts) >= 3:
                try:
                    idx = int(parts[0]) - 1  # 0-indexed (xtb 1-indexed)
                    charge_val = float(parts[2])
                    charges[idx] = charge_val
                except (ValueError, IndexError):
                    continue

        elif in_charges_block:
            # "   1   6 C   3.xxx   -0.123  ..."
            parts = stripped.split()
            if len(parts) >= 5:
                try:
                    idx = int(parts[0]) - 1
                    charge_val = float(parts[3])
                    charges[idx] = charge_val
                except (ValueError, IndexError):
                    continue

    return charges


def _try_gasteiger_charges(smiles):
    """RDKit Gasteiger-Marsili 전하 (Tier 3 fallback).

    Rule L: MolFromSmiles + None 체크.
    Rule M: 실패시 logger.warning + 빈 dict.

    Returns:
        {heavy_atom_idx(0-indexed): gasteiger_charge}
    """
    if not RDKIT_AVAILABLE:
        logger.warning("[M628] Gasteiger: RDKit 미설치")
        return {}

    # Rule L
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("[M628] Gasteiger: SMILES 파싱 실패: %s", smiles)
        return {}

    try:
        from rdkit.Chem import AllChem
        import math as _math
        mol_h = AllChem.AddHs(mol)
        AllChem.ComputeGasteigerCharges(mol_h)
        charges = {}
        heavy_idx = 0
        for i in range(mol_h.GetNumAtoms()):
            atom = mol_h.GetAtomWithIdx(i)
            if atom.GetAtomicNum() == 1:  # 수소 제외
                continue
            gc = atom.GetDoubleProp("_GasteigerCharge")
            # Rule N: 숫자 확인
            if not isinstance(gc, (int, float)):
                logger.warning("[M628] Gasteiger 전하 타입 오류 (idx=%d)", i)
                heavy_idx += 1
                continue
            # NaN/Inf -> 0 (극한 치환기 경우, Rule M)
            if _math.isnan(gc) or _math.isinf(gc):
                logger.warning("[M628] Gasteiger NaN/Inf (atom=%s idx=%d) -> 0.0",
                               atom.GetSymbol(), i)
                gc = 0.0
            charges[heavy_idx] = float(gc)
            heavy_idx += 1
        return charges
    except Exception as e:
        logger.warning("[M628] Gasteiger 계산 실패: %s", e)
        return {}
