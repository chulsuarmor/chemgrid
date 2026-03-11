import os, base64
out_dir = r'c:\chemgrid\docs\reports\theory_test'
files = sorted([f for f in os.listdir(out_dir) if f.endswith('.png')]) if os.path.exists(out_dir) else []
print("캡처된 파일:", files)
html = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>ChemGrid Test After Fix</title>',
        '<style>body{background:#0d0d1e;color:#eee;font-family:sans-serif;padding:10px}',
        '.b{margin:10px 0;border:2px solid #444;padding:8px;border-radius:4px}',
        '.key{border-color:#3f3}img{max-width:100%;display:block}h3{color:#fa7;margin:3px}</style></head><body>',
        '<h1>수정 후 ChemGrid 테스트 결과</h1>',
        '<p style="color:#7f7;font-size:14px">핵심: <b>02b_cp_theory_after_fix</b> - Cp- 5개 탄소에 전자구름 균일 분포 여부</p>']
for fn in files:
    p = os.path.join(out_dir, fn)
    with open(p, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    is_key = 'AFTER_FIX' in fn or 'benzene_theory' in fn or 'tropylium_theory' in fn
    cls = 'b key' if is_key else 'b'
    html.append(f'<div class="{cls}"><h3>{"★ " if is_key else ""}{fn}</h3><img src="data:image/png;base64,{b64}"></div>')
html.append('</body></html>')
out = r'c:\chemgrid\docs\reports\after_fix.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(''.join(html))
print(f'완료: {out} ({len(files)}개)')
