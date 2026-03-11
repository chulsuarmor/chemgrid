"""main_window.py 텍스트 입력 → 분자 그리기 경로 상세 분석"""
c = open('c:/chemgrid/src/app/main_window.py', encoding='utf-8').read()
lines = c.split('\n')

# L480~550: PubChem 경로 2 코드
print('=== L480~560 (PubChem 통로 2) ===')
for i, line in enumerate(lines[478:560], start=479):
    print(f'L{i}: {line}')

print('\n=== _build_smiles_from_graph (L913~970) ===')
for i, line in enumerate(lines[911:975], start=912):
    print(f'L{i}: {line}')
