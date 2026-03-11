"""Cp- 분석 디버그 - all_aromatic 실제 값 확인"""
import sys, os
sys.path.insert(0, 'c:/chemgrid/src/app')
os.chdir('c:/chemgrid/src/app')

from analyzer import ChemicalAnalyzer

a = ChemicalAnalyzer()

# Cp⁻ 원자/결합 (5각형 방향족 음이온)
atoms_cp = {
    0: {'symbol': 'C', 'pos': (300.0, 250.0), 'charge': -1, 'aromatic': True, 'h_count': 1},
    1: {'symbol': 'C', 'pos': (350.0, 285.0), 'charge': 0,  'aromatic': True, 'h_count': 1},
    2: {'symbol': 'C', 'pos': (330.0, 340.0), 'charge': 0,  'aromatic': True, 'h_count': 1},
    3: {'symbol': 'C', 'pos': (270.0, 340.0), 'charge': 0,  'aromatic': True, 'h_count': 1},
    4: {'symbol': 'C', 'pos': (250.0, 285.0), 'charge': 0,  'aromatic': True, 'h_count': 1},
}
bonds_cp = {
    (0,1): 2, (1,2): 1, (2,3): 2, (3,4): 1, (4,0): 2
}

print("=== Cp⁻ 분석 ===")
results = a.analyze(atoms_cp, bonds_cp, smiles='[cH-]1cccc1')
print(f"all_aromatic: {results.get('all_aromatic', 'MISSING')}")
print(f"islands 수: {len(results.get('islands', []))}")
print(f"전하 결과: {results.get('charges', {})}")
print(f"결합 결과 샘플: {list(results.get('bond_orders', {}).items())[:5]}")

# renderer.py에서 사용하는 키 확인
print("\n=== renderer 관련 키들 ===")
for k in ['all_aromatic', 'rings', 'islands', 'charges', 'bond_deltas', 'electron_density']:
    v = results.get(k, 'MISSING')
    if isinstance(v, (set, list, dict)):
        print(f"  {k}: {type(v).__name__}({len(v)}개)")
    else:
        print(f"  {k}: {v}")

# Benzene 비교
print("\n=== Benzene 비교 ===")
atoms_benz = {
    i: {'symbol': 'C', 'pos': (300+50*__import__('math').cos(i*60*3.14159/180),
                                300+50*__import__('math').sin(i*60*3.14159/180)),
         'charge': 0, 'aromatic': True, 'h_count': 1}
    for i in range(6)
}
bonds_benz = {(i, (i+1)%6): (2 if i%2==0 else 1) for i in range(6)}
res_benz = a.analyze(atoms_benz, bonds_benz, smiles='c1ccccc1')
print(f"all_aromatic: {res_benz.get('all_aromatic', 'MISSING')}")
