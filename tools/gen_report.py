import os, base64
SAVE_DIR = r'c:\chemgrid\docs\reports\visual_test_full'
files = sorted([f for f in os.listdir(SAVE_DIR) if f.endswith('.png')])
print('파일:', files)
parts = []
parts.append('<!DOCTYPE html><html><head><meta charset="utf-8"><title>ChemGrid Test</title>')
parts.append('<style>body{font-family:sans-serif;background:#111;color:#eee;padding:20px}')
parts.append('img{max-width:100%;border:2px solid #444;display:block;margin:10px 0}')
parts.append('h3{color:#7bf;margin:20px 0 5px}.ok{color:#0f0}.fail{color:#f44}</style></head><body>')
parts.append('<h1>ChemGrid 전수 시각 테스트 2026-03-10</h1>')
parts.append('<p>핵심 확인 사항: <span class="ok">04_cp_theory = Cp- 전자구름 균일 분포?</span></p>')
for fn in files:
    path = os.path.join(SAVE_DIR, fn)
    with open(path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    tag = fn.replace('.png','')
    parts.append('<div style="margin:15px 0;border:1px solid #333;padding:10px">')
    parts.append('<h3>' + tag + '</h3>')
    parts.append('<img src="data:image/png;base64,' + b64 + '">')
    parts.append('</div>')
parts.append('</body></html>')
out = r'c:\chemgrid\docs\reports\visual_test_full.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(''.join(parts))
print('완료:', out)
print('총 이미지:', len(files))
