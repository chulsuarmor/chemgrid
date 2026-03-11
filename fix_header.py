import re
path = r'c:\chemgrid\src\app\main_window.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
# 파일 첫 줄에 한글 등 비ASCII 문자가 붙어있으면 제거
fixed = re.sub(r'^[^\x00-\x7f\'"]+', '', content)
if fixed != content:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)
    print('FIXED. First 30 chars:', repr(fixed[:30]))
else:
    print('NO CHANGE. First 30 chars:', repr(content[:30]))
