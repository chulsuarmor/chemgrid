"""main_window.py BUILTIN dict에 벤젠이 있는지 확인"""
c = open('c:/chemgrid/src/app/main_window.py', encoding='utf-8').read()
lines = c.split('\n')

# BUILTIN dict 전체 확인 (L530~635)
print('=== BUILTIN dict benzene 검색 ===')
for i, line in enumerate(lines[528:640], start=529):
    if 'benzene' in line.lower() or 'toluene' in line.lower() or 'aromatic' in line.lower():
        print(f'L{i}: {line}')

# _lookup_smiles_for_name 전체 보기
print('\n=== L630~680 (PubChem 호출부) ===')
for i, line in enumerate(lines[628:685], start=629):
    print(f'L{i}: {line}')
