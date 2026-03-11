"""canvas.py mousePressEvent 전체 구조 추출"""
content = open(r'c:\chemgrid\agents\10_testing_build\integrated\canvas.py', encoding='utf-8').read()
lines = content.split('\n')

# Find mousePressEvent and print ~80 lines
for i, line in enumerate(lines):
    if 'def mousePressEvent' in line:
        print(f"mousePressEvent starts at line {i+1}")
        for j in range(i, min(i+100, len(lines))):
            print(f'{j+1}: {lines[j]}')
        break
