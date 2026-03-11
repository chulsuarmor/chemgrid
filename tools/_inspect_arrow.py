"""canvas.py의 화살표 관련 코드 추출"""
content = open(r'c:\chemgrid\agents\10_testing_build\integrated\canvas.py', encoding='utf-8').read()
lines = content.split('\n')

print("=== _draw_arrow METHOD ===")
for i, line in enumerate(lines):
    if 'def _draw_arrow' in line:
        for j in range(i, min(i+40, len(lines))):
            print(f'{j+1}: {lines[j]}')
        break

print("\n=== ARROW PAINT in paintEvent ===")
for i, line in enumerate(lines):
    if 'if self.arrows or' in line:
        for j in range(max(0,i-2), min(i+25, len(lines))):
            print(f'{j+1}: {lines[j]}')
        break

print("\n=== ARROW mousePressEvent ===")
for i, line in enumerate(lines):
    if 'Arrow' in line and 'mode' in line and 'Press' not in line and 'def ' not in line:
        if 'elif' in line or 'if' in line:
            for j in range(max(0,i-1), min(i+8, len(lines))):
                print(f'{j+1}: {lines[j]}')
            print('...')

print("\n=== GRID SNAP CODE ===")
for i, line in enumerate(lines):
    if 'snap' in line.lower() or 'grid' in line.lower():
        if 'arrow' in lines[max(0,i-5):i+1].__repr__().lower():
            print(f'{i+1}: {line}')
