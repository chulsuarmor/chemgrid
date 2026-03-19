# analyzer.py (v6.11 - Procrustes Alignment for Theory Coords)
import math
from PyQt6.QtCore import QPointF # [추가] QPointF NameError 해결
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
        
        # [Fix] Scan for user-drawn radicals in 'attach'
        for k, v in norm_atoms.items():
            if "attach" in v:
                for d, sym in v["attach"].items():
                    if sym == "·" or sym == ".": # Check both dot characters
                        v["is_radical"] = True
                        print(f" -> Radical detected at {k}")

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
                    _cf2 = norm_atoms.get(node, {}).get("charge", "")
                    _ac2 = sum(
                        (1 if s == "+" else (-1 if s == "-" else 0))
                        for d, s in norm_atoms.get(node, {}).get("attach", {}).items()
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
                _cf = _at.get("charge", "")
                net_formal_charge += (1 if _cf == "+" else (-1 if _cf == "-" else 0))
                net_formal_charge += sum(
                    (1 if s == "+" else (-1 if s == "-" else 0))
                    for d, s in _at.get("attach", {}).items() if d != -1
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
                            rdkit_idx = norm_atoms.get(nk, {}).get("rdkit_idx", -1)
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
                                    elem = norm_atoms.get(nk, {}).get("main", "") or "C"
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
                                print(f"[GASTEIGER] Equalized {n_equalized} resonance-equivalent atoms", flush=True)

                            print(f"[GASTEIGER] Applied RDKit charges (blended 60/40) for {len(idx_to_nk)} atoms via rdkit_idx", flush=True)
                        else:
                            print(f"[GASTEIGER] No rdkit_idx found, skipping Gasteiger blending", flush=True)
            except Exception as e_gast:
                print(f"[GASTEIGER] Fallback to custom physics: {e_gast}", flush=True)

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
                print(f"[AROMATIC FIX] Ring π-island detected: {len(pi_isl)} atoms added to all_aromatic")

        # [PLAN-CHEM-002] RDKit GetIsAromatic() fallback: 외부 smiles가 제공된 경우
        # RDKit의 방향족 판정을 직접 사용하여 all_aromatic 보강
        # 이는 캔버스에서 aromatic bond가 order=1로 저장되어 pi-island 미탐지되는 경우를 보완
        if RDKIT_AVAILABLE and smiles and not all_aromatic:
            try:
                _test_mol = Chem.MolFromSmiles(smiles)
                if _test_mol:
                    # RDKit aromatic atom idx 수집
                    rdkit_aromatic_idxs = set()
                    for atom in _test_mol.GetAtoms():
                        if atom.GetIsAromatic():
                            rdkit_aromatic_idxs.add(atom.GetIdx())
                    if rdkit_aromatic_idxs:
                        # rdkit_idx → norm_key 매핑으로 all_aromatic 보강
                        for nk, nv in norm_atoms.items():
                            rdkit_idx = nv.get("rdkit_idx", -1)
                            if rdkit_idx in rdkit_aromatic_idxs:
                                all_aromatic.add(nk)
                        if all_aromatic:
                            print(f"[AROMATIC RDKIT] RDKit GetIsAromatic() fallback: {len(all_aromatic)} atoms added to all_aromatic")
            except Exception as e_aro:
                print(f"[AROMATIC RDKIT] Fallback failed: {e_aro}")

        # [신규] 시각화를 위한 입체 중심(R/S) 분석 및 전달 데이터 확장
        # generate_smiles의 입체 인식 로직을 활용하여 결과를 추출합니다.
        smiles_str, stereo_labels, lewis_data, theory_data = self.generate_smiles(atoms, bonds)
        # [BUG-3 Fix] generate_smiles 실패 시 외부 smiles 사용 (cp-, tropylium 등 이온성 방향족)
        if not smiles_str and smiles:
            smiles_str = smiles
        
        print(f"\n[LEWIS DATA INJECTION LOG]")
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

                print(f" -> {'MATCH' if matched else 'FALLBACK'}: Lewis Data at {target} (dist: {best_dist:.2f}) | H:{extra['h_count']}, LP:{extra['lp_count']}, Charge:{formal_charge}")
            else:
                print(f" -> FAILURE: Could not find target atom for Lewis Data at {l_pt} (nearest: {best_dist:.1f}px)")

        # [v8.1] 암시적 수소에 의한 전기음성도 보정 (lewis_data 주입 후 h_count 사용 가능)
        # RDKit RemoveHs로 제거된 H 원자들의 유발 효과 반영
        from chem_data import ELEMENT_DATA as _ED
        for k in global_charges:
            at = norm_atoms.get(k, {})
            main_sym = at.get("main") or "C"
            h_count = at.get("h_count", 0)
            if h_count > 0 and main_sym not in ("C", "", "H"):
                en_atom = _ED.get(main_sym, {"negativity": 2.5})["negativity"]
                en_h = _ED.get("H", {"negativity": 2.2})["negativity"]
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
                e1 = norm_atoms.get(pk1, {}).get("main") or "C"
                e2 = norm_atoms.get(pk2, {}).get("main") or "C"
                order = v if isinstance(v, int) else 1
                is_aro = (pk1 in all_aromatic and pk2 in all_aromatic)
                bl = self.physics.get_bond_length_angstrom(e1, e2, order, is_aromatic=is_aro)
                bond_lengths[(pk1, pk2)] = bl

        return {
            "charges": global_charges,
            "islands": total_pi_islands,
            "aromatic": all_aromatic,
            "atoms": norm_atoms,
            "bonds": bonds,
            "adj": full_adj,
            "stereo": stereo_labels,
            "theory_data": theory_data,
            "bond_lengths": bond_lengths,
        }

    def _ring_topology_distance(self, start, pi_island, adj):
        """BFS로 ring 내 위상 거리 계산 (ortho=1, meta=2, para=3)"""
        distances = {start: 0}
        queue = [start]
        while queue:
            curr = queue.pop(0)
            for neighbor, _ in adj.get(curr, []):
                if neighbor in pi_island and neighbor not in distances:
                    distances[neighbor] = distances[curr] + 1
                    queue.append(neighbor)
        return distances

    def generate_smiles(self, atoms, bonds):
        # [가드] RDKit 미설치 시 빈 데이터 반환 (graceful fallback)
        if not RDKIT_AVAILABLE:
            print("[WARNING] RDKit not available — SMILES generation skipped")
            return "", {}, {}, {"coords": {}, "bonds": []}

        # [STAGE 1] 원자 및 결합 복구 (ID 기반 무결성)
        # [해결] 반올림을 2자리(0.01)로 통일하여 t_map 매칭 실패 원천 차단
        def get_pos(p): return (round(p.x(), 2), round(p.y(), 2)) if hasattr(p, 'x') else (round(p[0], 2), round(p[1], 2))
        mol = Chem.RWMol(); node_to_idx, idx_to_coord = {}, {}

        # 1. 메인 원자 생성
        sorted_keys = sorted(atoms.keys(), key=lambda k: (get_pos(k)[1], get_pos(k)[0]))
        for k in sorted_keys:
            pos = get_pos(k); data = atoms[k]
            atom = Chem.Atom(data.get("main") or "C")

            # [Fix v2] 전하 보존: 'charge' 필드 우선, attach는 d==-1 lewis주입 제외 보조
            formal_charge = 0
            _cf = data.get("charge", "")
            if _cf == "+":
                formal_charge = 1
            elif _cf == "-":
                formal_charge = -1
            else:
                for _d, _sym in data.get("attach", {}).items():
                    if _d == -1:
                        continue
                    if _sym == "+":
                        formal_charge += 1
                    elif _sym == "-":
                        formal_charge -= 1
            atom.SetFormalCharge(formal_charge)

            # [Fix v2] 라디칼 전자 반영 (attach에 "·" 기호)
            _rad = sum(1 for _d, _sym in data.get("attach", {}).items()
                       if _sym == "·" and _d != -1)
            if _rad > 0:
                atom.SetNumRadicalElectrons(_rad)

            idx = mol.AddAtom(atom)
            node_to_idx[pos] = idx; idx_to_coord[idx] = list(pos) + [0.0]
            # [Fix v2] attach H는 implicit H로 처리 (명시 원자 추가 제거 → 왜곡 방지)

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

            print("\n[CHIRALITY AUDIT LOG]")
            for atom in final_mol.GetAtoms():
                if not atom.HasProp("_CIPCode"): continue
                
                # [강력 필터] 4개 치환기의 랭킹이 중복되면(아키랄) 강제 기각
                nb_ranks = sorted([ranks[nb.GetIdx()] for nb in atom.GetNeighbors()])
                if len(set(nb_ranks)) < atom.GetDegree():
                    print(f" -> REJECTED: Atom {atom.GetIdx()} is achiral (Ranks: {nb_ranks})")
                    atom.ClearProp("_CIPCode")
                    atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
                    continue

                # 통과된 센터만 처리
                label = atom.GetProp("_CIPCode")
                tag = Chem.ChiralType.CHI_TETRAHEDRAL_CW if label == "R" else Chem.ChiralType.CHI_TETRAHEDRAL_CCW
                atom.SetChiralTag(tag)
                
                c_pos = idx_to_coord[atom.GetIdx()]
                stereo_map[(round(c_pos[0], 1), round(c_pos[1], 1) - 0.1)] = f"({label})"
                print(f" -> CONFIRMED: {label} center at {c_pos[:2]} | Ranks: {nb_ranks}")

            out_mol = Chem.RemoveHs(final_mol)
            smiles = Chem.MolToSmiles(out_mol, isomericSmiles=True)
            
            # [추가] 루이스 구조용 H 및 비공유 전자쌍 데이터 생성
            # [M4 수정] 중복 루프 통합 — 단일 루프로 lewis_map 생성
            lewis_map = {}
            print(f"\n[RDKIT ATOM ANALYSIS]")
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
                print(f" Atom {atom.GetSymbol()} at {pt_key}: Outer:{outer_elecs}, Bonded:{bonds_val}, LP:{lp}, Charge:{formal_charge}")

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
            except Exception as te: print(f"[THEORY ERROR] {te}")

            print(f">>> [FINAL RESULT] SMILES: {smiles}")
            # [해결] 루이스 정보와 이론적 최적화 데이터를 함께 반환
            return smiles, stereo_map, lewis_map, theory_data 

        except Exception as e:
            # [해결] 짝이 맞지 않던 try-except 구문 완결 및 빈 데이터 반환
            print(f"[ERROR] generate_smiles failure: {e}")
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
        print("[LogP] RDKit not available")
        return 0.0
    try:
        from rdkit.Chem import Crippen
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"[LogP] Invalid SMILES: {smiles}")
            return 0.0
        return Crippen.MolLogP(mol)
    except Exception as e:
        print(f"[LogP] Calculation error: {e}")
        return 0.0


def calculate_tpsa(smiles: str) -> float:
    """SMILES로부터 TPSA (Topological Polar Surface Area)를 계산합니다.

    Args:
        smiles: 분자의 SMILES 문자열

    Returns:
        TPSA 값 (Angstrom^2). 계산 실패 시 0.0 반환.
    """
    if not RDKIT_AVAILABLE:
        print("[TPSA] RDKit not available")
        return 0.0
    try:
        from rdkit.Chem import Descriptors
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"[TPSA] Invalid SMILES: {smiles}")
            return 0.0
        return Descriptors.TPSA(mol)
    except Exception as e:
        print(f"[TPSA] Calculation error: {e}")
        return 0.0


def calculate_rotatable_bonds(smiles: str) -> int:
    """SMILES로부터 회전 가능 결합 수를 계산합니다.

    Args:
        smiles: 분자의 SMILES 문자열

    Returns:
        회전 가능 결합 수 (int). 계산 실패 시 0 반환.
    """
    if not RDKIT_AVAILABLE:
        print("[RotBonds] RDKit not available")
        return 0
    try:
        from rdkit.Chem import Lipinski
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"[RotBonds] Invalid SMILES: {smiles}")
            return 0
        return Lipinski.NumRotatableBonds(mol)
    except Exception as e:
        print(f"[RotBonds] Calculation error: {e}")
        return 0