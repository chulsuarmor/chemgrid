# analyzer.py (v6.00 - RDKit Integration)
import math
from PyQt6.QtCore import QPointF # [추가] QPointF NameError 해결
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

    def analyze(self, atoms, bonds):
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
            total_pi_islands.extend(mol_pi)
            
            for pi_isl in mol_pi:
                # 공명 델타 합산 (Additive Model)
                res_deltas = self.resonance.calculate_resonance_deltas(pi_isl, norm_atoms, mol_adj)
                for node, delta in res_deltas.items():
                    mol_charges[node] += delta
                
                # 치환기 벡터 효과
                for node in pi_isl:
                    for neighbor, _ in mol_adj.get(node, []):
                        if neighbor not in pi_isl:
                            score = self.physics.calculate_substituent_score(neighbor, pi_isl, norm_atoms, mol_adj)
                            pull_force = (score * 0.75) / len(pi_isl)
                            for target in pi_isl:
                                mol_charges[target] += pull_force
                                mol_charges[neighbor] -= pull_force * 0.2
            
            # [analyzer.py] Line 70 부근 (analyze 함수 마지막)
            for k, q in mol_charges.items(): global_charges[k] = q

        # [신규] 시각화를 위한 입체 중심(R/S) 분석 및 전달 데이터 확장
        # generate_smiles의 입체 인식 로직을 활용하여 결과를 추출합니다.
        smiles_str, stereo_labels, lewis_data, theory_data = self.generate_smiles(atoms, bonds)
        
        print(f"\n[LEWIS DATA INJECTION LOG]")
        # [해결] 단순 키 매칭이 아닌 거리 기반(8px 이내) 매칭으로 무결성 확보
        for l_pt, extra in lewis_data.items():
            matched = False
            for n_pt in norm_atoms.keys():
                dist = math.hypot(l_pt[0] - n_pt[0], l_pt[1] - n_pt[1])
                if dist < 8.0: # 8픽셀 이내면 동일 원자로 판단
                    norm_atoms[n_pt].update(extra)

                    # [TASK 2] 전하 복원: formal_charge를 attach 딕셔너리에 +/- 기호로 추가
                    formal_charge = extra.get("formal_charge", 0)
                    if formal_charge != 0:
                        if "attach" not in norm_atoms[n_pt]:
                            norm_atoms[n_pt]["attach"] = {}
                        # 양전하는 direction -1에 + 기호
                        if formal_charge > 0:
                            for i in range(abs(formal_charge)):
                                norm_atoms[n_pt]["attach"][-1] = "+"
                        # 음전하는 direction -1에 - 기호
                        elif formal_charge < 0:
                            for i in range(abs(formal_charge)):
                                norm_atoms[n_pt]["attach"][-1] = "-"

                    print(f" -> SUCCESS: Matched Lewis Data at {n_pt} (dist: {dist:.2f}) | H:{extra['h_count']}, LP:{extra['lp_count']}, Charge:{formal_charge}")
                    matched = True
                    break
            if not matched:
                print(f" -> FAILURE: Could not find target atom for Lewis Data at {l_pt}")

        return {
            "charges": global_charges, 
            "islands": total_pi_islands, 
            "aromatic": all_aromatic, 
            "atoms": norm_atoms,
            "bonds": bonds, 
            "adj": full_adj, 
            "stereo": stereo_labels,
            "theory_data": theory_data #
        }

    def generate_smiles(self, atoms, bonds):
        # [STAGE 1] 원자 및 결합 복구 (ID 기반 무결성)
        # [해결] 반올림을 2자리(0.01)로 통일하여 t_map 매칭 실패 원천 차단
        def get_pos(p): return (round(p.x(), 2), round(p.y(), 2)) if hasattr(p, 'x') else (round(p[0], 2), round(p[1], 2))
        mol = Chem.RWMol(); node_to_idx, idx_to_coord = {}, {}

        # 1. 메인 원자 생성
        sorted_keys = sorted(atoms.keys(), key=lambda k: (get_pos(k)[1], get_pos(k)[0]))
        for k in sorted_keys:
            pos = get_pos(k); data = atoms[k]
            atom = Chem.Atom(data.get("main") or "C")

            # [TASK 2] 전하 보존: attach 딕셔너리에서 +/- 기호 개수 세기
            formal_charge = 0
            for d, sym in data.get("attach", {}).items():
                if sym == "+":
                    formal_charge += 1
                elif sym == "-":
                    formal_charge -= 1

            atom.SetFormalCharge(formal_charge)
            idx = mol.AddAtom(atom)
            node_to_idx[pos] = idx; idx_to_coord[idx] = list(pos) + [0.0]

            # 2. 'attach' 내의 수소(H)를 실제 원자로 승격 및 결합
            for d, sym in data.get("attach", {}).items():
                if sym == "H":
                    h_idx = mol.AddAtom(Chem.Atom("H"))
                    mol.AddBond(idx, h_idx, Chem.rdchem.BondType.SINGLE)
                    ang = math.radians(d * 60)
                    idx_to_coord[h_idx] = [pos[0] + math.cos(ang)*20, pos[1] + math.sin(ang)*20, 0.0]

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
            lewis_map = {}
            print(f"\n[RDKIT ATOM ANALYSIS]")
            for atom in final_mol.GetAtoms():
                if atom.GetSymbol() == "H": continue
                pos = idx_to_coord[atom.GetIdx()]
                
                # 가전자(Default Valence) - (명시적 결합 + 암시적 결합) - 전하
                atomic_num = atom.GetAtomicNum()
                # 산소(8) -> 6, 질소(7) -> 5, 탄소(6) -> 4 등 실제 가전자수 획득
                outer_elecs = Chem.GetPeriodicTable().GetNOuterElecs(atomic_num)
                bonds_val = atom.GetTotalValence()
                lp = max(0, (outer_elecs - bonds_val - atom.GetFormalCharge()) // 2)
                
            for atom in final_mol.GetAtoms():
                if atom.GetSymbol() == "H": continue
                pos = idx_to_coord[atom.GetIdx()]
                # [해결] pt_key를 먼저 정의하여 참조 오류 방지
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

            # [Step 3 개선] MMFF94/2D 최적화 좌표 산출 - 분자별 독립 배치
            theory_data = {"coords": {}, "bonds": []}
            try:
                temp_mol = Chem.Mol(final_mol)
                rdDepictor.Compute2DCoords(temp_mol)
                conf = temp_mol.GetConformer()
                
                # 1. 분자별 연결 성분 탐색 (각 독립 분자를 개별 처리)
                from rdkit.Chem import rdmolops
                mol_frags = rdmolops.GetMolFrags(temp_mol, asMols=False)
                
                theory_map = {}
                
                # 2. 각 분자 조각마다 독립적으로 중심점 계산 및 배치
                for frag_atoms in mol_frags:
                    if not frag_atoms:
                        continue
                    
                    # 2-1. 원본 좌표의 중심점 (그리기 레이어에서의 배치)
                    orig_pts = [idx_to_coord[i][:2] for i in frag_atoms]
                    orig_center = QPointF(sum(p[0] for p in orig_pts)/len(orig_pts),
                                         sum(p[1] for p in orig_pts)/len(orig_pts))
                    
                    # 2-2. RDKit 최적화 좌표의 중심점
                    rdkit_pts = [conf.GetAtomPosition(i) for i in frag_atoms]
                    rdkit_cx = sum(p.x for p in rdkit_pts) / len(rdkit_pts)
                    rdkit_cy = sum(p.y for p in rdkit_pts) / len(rdkit_pts)
                    
                    # 2-3. 각 원자를 원본 중심 기준으로 재배치
                    for i in frag_atoms:
                        pos = conf.GetAtomPosition(i)
                        orig_pt = (round(idx_to_coord[i][0], 2), round(idx_to_coord[i][1], 2))
                        # 최적화된 형태(정다각형)를 유지하되, 원본 위치로 평행이동
                        new_pos = QPointF(orig_center.x() + (pos.x - rdkit_cx) * 45.0, 
                                         orig_center.y() - (pos.y - rdkit_cy) * 45.0)
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