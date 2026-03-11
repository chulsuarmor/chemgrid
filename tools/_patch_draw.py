"""draw.py의 인라인 툴바 코드를 setup_toolbars(self) 호출로 교체"""
import re

filepath = r'c:\chemgrid\agents\10_testing_build\integrated\draw.py'
content = open(filepath, encoding='utf-8').read()
lines = content.split('\n')

# 1. toolbar_setup import 추가 (아직 없다면)
if 'from toolbar_setup import setup_toolbars' not in content:
    # from ui_utils import load_icon 바로 다음에 추가
    for i, line in enumerate(lines):
        if 'from ui_utils import load_icon' in line:
            # 이 줄 뒤에 없으면 삽입
            break
    # draw.py에 ui_utils import가 없을 수도 있으므로, chem_data import 뒤에 삽입
    for i, line in enumerate(lines):
        if 'from chem_data import' in line:
            lines.insert(i+1, 'from toolbar_setup import setup_toolbars')
            print(f"Added import at line {i+2}")
            break

# 2. 인라인 툴바 코드 영역 찾기 (self.setStyleSheet ... 부터 원소 선택 뒤까지)
start_line = None
end_line = None

for i, line in enumerate(lines):
    # 시작: self.setStyleSheet("QToolButton 
    if start_line is None and 'self.setStyleSheet("QToolButton' in line:
        start_line = i
    # 끝: self.view_container = QWidget
    if start_line is not None and 'self.view_container = QWidget' in line:
        end_line = i
        break

if start_line is None or end_line is None:
    print(f"ERROR: Could not find toolbar section. start={start_line}, end={end_line}")
    exit(1)

print(f"Replacing lines {start_line+1}~{end_line} with setup_toolbars(self)")
print(f"  Original: {end_line - start_line} lines")

# 3. 교체: 인라인 코드 → setup_toolbars(self)
replacement = [
    "        # ========== 툴바 설정 (toolbar_setup.py로 분리) ==========",
    "        setup_toolbars(self)",
    "",
]

new_lines = lines[:start_line] + replacement + lines[end_line:]

# 4. 저장
with open(filepath, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"DONE. Total lines: {len(lines)} → {len(new_lines)}")
