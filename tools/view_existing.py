"""기존 테스트 PNG들을 HTML에 모아서 보기"""
import os, base64

# 모든 관련 PNG 수집
files_map = {
    'root': [
        ('cp_draw.png', 'c:/chemgrid/cp_draw.png'),
        ('cp_theory2.png', 'c:/chemgrid/cp_theory2.png'),
        ('test_cp_anion.png', 'c:/chemgrid/test_cp_anion.png'),
        ('test_cp_theory.png', 'c:/chemgrid/test_cp_theory.png'),
        ('test_theory.png', 'c:/chemgrid/test_theory.png'),
        ('test_after_benzene.png', 'c:/chemgrid/test_after_benzene.png'),
        ('test_ethanol.png', 'c:/chemgrid/test_ethanol.png'),
        ('test_3d_popup.png', 'c:/chemgrid/test_3d_popup.png'),
        ('screen_test.png', 'c:/chemgrid/screen_test.png'),
    ],
    'visual_test': []
}

# visual_test_full 폴더 파일 추가
vdir = 'c:/chemgrid/docs/reports/visual_test_full'
if os.path.exists(vdir):
    for fn in sorted(os.listdir(vdir)):
        if fn.endswith('.png'):
            files_map['visual_test'].append((fn, os.path.join(vdir, fn)))

parts = ['''<!DOCTYPE html><html><head><meta charset="utf-8">
<title>ChemGrid 이미지 분석</title>
<style>
body{font-family:sans-serif;background:#0a0a1a;color:#eee;padding:15px}
.section{margin:30px 0}
.img-box{display:inline-block;margin:10px;border:2px solid #444;padding:8px;background:#111;max-width:600px;vertical-align:top}
img{max-width:580px;display:block}
h2{color:#7af;border-bottom:1px solid #333;padding-bottom:5px}
h3{color:#fa7;margin:5px 0}
.note{color:#888;font-size:12px}
</style></head><body>
<h1>ChemGrid 기존 테스트 이미지 분석</h1>
<p class="note">ISSUE-1: 전자구름 균일 분포 확인 핵심 → cp_theory 이미지 집중 확인</p>
''']

for section, items in files_map.items():
    parts.append(f'<div class="section"><h2>{section} 섹션</h2>')
    for name, path in items:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
            parts.append(f'<div class="img-box"><h3>{name}</h3>')
            parts.append(f'<img src="data:image/png;base64,{b64}">')
            parts.append('</div>')
        else:
            parts.append(f'<div class="img-box"><h3>{name}</h3><p style="color:#f44">파일 없음</p></div>')
    parts.append('</div>')

parts.append('</body></html>')

out = 'c:/chemgrid/docs/reports/existing_images.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(''.join(parts))
print(f'완료: {out}')
