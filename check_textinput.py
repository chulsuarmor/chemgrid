"""main_window.py에서 텍스트 입력 처리 경로 추적"""
c = open('c:/chemgrid/src/app/main_window.py', encoding='utf-8').read()

# 텍스트 입력 관련 키워드 검색
keywords = ['parse_input', 'TextInput', 'name_to_smiles', 'generate_molecule',
            'text_input', 'molecule_name', 'input_text', 'iupac', 'pubchem',
            '_on_text_', 'smiles_from', '_draw_from_name', '_generate']

for kw in keywords:
    lines = [(i+1, line.strip()) for i, line in enumerate(c.split('\n')) if kw.lower() in line.lower()]
    if lines:
        print(f'\n[{kw}]')
        for no, line in lines[:5]:
            print(f'  L{no}: {line}')

# iupac_analyzer.py 간략 확인
try:
    ia = open('c:/chemgrid/src/app/iupac_analyzer.py', encoding='utf-8').read()
    print('\n[iupac_analyzer.py 함수 목록]')
    import re
    for m in re.findall(r'def (\w+)\(', ia):
        print(f'  def {m}()')
    # smiles 반환 부분
    if 'pubchem' in ia.lower():
        print('  → PubChem 코드 존재')
    elif 'gemini' in ia.lower() or 'google' in ia.lower():
        print('  → Gemini 코드 존재')
    else:
        print('  → 외부 API 없음 (로컬만)')
except FileNotFoundError:
    print('[iupac_analyzer.py] 없음')
