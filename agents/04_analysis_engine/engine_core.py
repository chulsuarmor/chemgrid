# engine_core.py (v2.81 - Dispatcher Added)
import math
import sys
import subprocess
from pathlib import Path
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
            is_participant = (any(o >= 2 for _, o in adj.get(node, [])) or 
                             any(s in ["+", "-", "·", ".."] for s in at.get("attach", {}).values()))
            
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
                                if (any(o >= 2 for _, o in adj.get(n, [])) or 
                                    any(s in ["+", "-", "·", ".."] for s in n_at.get("attach", {}).values())):
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
        
        # [v4.2] 양전하(+) 반영 및 라디칼 계산 정확화
        # v4.83: 양전하(+)는 p 오비탈 비우기만 하며 전자 기여 없음
        ex = sum(2 for n in r if any(s in ["-", ".."] 
                   for s in atoms[n].get("attach", {}).values()) 
                   or atoms[n].get("charge") == "-")
        # 양전하(+) 원자는 계산에서 제외 (전자 수 변경 없음)
        # ex -= sum(1 for n in r if atoms[n].get("charge") == "+")  # 주석 처리
        rad = sum(1 for n in r if "·" in atoms[n].get("attach", {}).values())
        
        # 양전하(+)는 비어있는 p오비탈 제공 (전자는 0개 기여)이므로 합산에는 제외하지만,
        # Huckel 고리 내에 위치할 수 있으므로 계산을 통과하게 함.
        # Cyclopentadienyl anion (-): pi(0) + ex(2) = 6개 (aromatic)
        # Tropylium cation (+): pi(6) + ex(0) = 6개 (aromatic)
        
        total_pi = pi + ex + rad
        return total_pi in [2, 6, 10, 14, 18, 22, 26]


class QuantumChemistryValidator:
    """ORCA/RDKit 검증 시스템"""
    
    def validate_orca_connection(self):
        import subprocess
        try:
            result = subprocess.run(['orca', '--version'], capture_output=True, text=True)
            return "ORCA Version" in result.stdout
        except FileNotFoundError:
            return False

    def run_validation_test(self):
        from rdkit import Chem
        test_mol = Chem.MolFromSmiles('CCO')
        return self._run_calculation(test_mol)

class SpectrumDispatcher:
    """하위 분광학 에이전트들에게 수정 명령을 하달하는 디스패처"""
    
    def __init__(self):
        # 현재 파일 위치: agents/04_analysis_engine/engine_core.py
        # root_dir: c:/chemgrid
        self.root_dir = Path(__file__).resolve().parent.parent.parent
        self.spectroscopy_dir = self.root_dir / "agents" / "08_spectroscopy"

    def dispatch_fix_orders(self, fix_version: str = "v4.83"):
        """각 하위 에이전트에게 버전별 수정 명령 전달
        
        Args:
            fix_version: 적용할 패치 버전 (예: v4.83)
        """
        
        targets = [
            self.spectroscopy_dir / "ir_raman" / "_patch_fix.py",
            self.spectroscopy_dir / "uvvis" / "_patch_fix.py",
            self.spectroscopy_dir / "nmr" / "_patch_fix.py",
            self.root_dir / "agents" / "09_data_export" / "_patch_fix.py"
        ]

        print("=== [Manager AI] Dispatching fix orders to sub-agents ===")
        print(f"Root dir: {self.root_dir}")
        print(f"Spectroscopy dir: {self.spectroscopy_dir}")
        
        success_count = 0
        
        for target in targets:
            if target.exists():
                print(f"Executing order: {target.name} in {target.parent.name}...")
                try:
                    # cwd를 target의 부모 디렉토리로 설정하여 상대 경로 import 문제 해결
                    result = subprocess.run([sys.executable, target.name], 
                                          cwd=str(target.parent),
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        print(f"  [SUCCESS] {target.parent.name} agent reported success.")
                        print(f"  Log: {result.stdout.strip()}")
                        success_count += 1
                    else:
                        print(f"  [FAILURE] {target.parent.name} agent failed.")
                        print(f"  Error: {result.stderr.strip()}")
                        print(f"  Output: {result.stdout.strip()}")
                except Exception as e:
                    print(f"  [CRITICAL] Failed to execute {target}: {e}")
            else:
                print(f"  [WARNING] Order script not found: {target}")
        
        if success_count == len(targets):
            print("All agents executed successfully.")
            sys.exit(0)
        else:
            print(f"Some agents failed. Success: {success_count}/{len(targets)}")
            sys.exit(1)

if __name__ == "__main__":
    print("Engine Core Main Started")
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dispatch", action="store_true", help="Dispatch fix orders")
    parser.add_argument("--validate", choices=['orca', 'rdkit'], help="Run validation tests")
    args = parser.parse_args()

    if args.dispatch:
        try:
            print("Initializing Dispatcher...")
            dispatcher = SpectrumDispatcher()
            dispatcher.dispatch_fix_orders()
        except Exception as e:
            print(f"Dispatcher error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("No dispatch flag provided.")
        # 기존 테스트 코드 또는 아무것도 안 함
        pass
