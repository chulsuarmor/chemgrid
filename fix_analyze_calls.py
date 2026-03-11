# canvas.py: analyze() 호출에 _last_drawn_smiles 주입
c = open('c:/chemgrid/src/app/canvas.py', encoding='utf-8').read()
old = 'self.analysis_results = self.analyzer.analyze(self.atoms, self.bonds)'
new = "self.analysis_results = self.analyzer.analyze(self.atoms, self.bonds, smiles=getattr(self, '_last_drawn_smiles', None))"
if old in c:
    c = c.replace(old, new, 1)
    open('c:/chemgrid/src/app/canvas.py', 'w', encoding='utf-8').write(c)
    print('canvas.py OK')
else:
    print('canvas.py pattern NOT found')
    idx = c.find('analyzer.analyze(')
    print(f'  found at idx={idx}: {repr(c[idx:idx+80])}')

# main_window.py: analyze() 호출에 _last_drawn_smiles 주입
m = open('c:/chemgrid/src/app/main_window.py', encoding='utf-8').read()
old2 = 'self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds)'
new2 = "self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, smiles=getattr(self.cv, '_last_drawn_smiles', None))"
if old2 in m:
    m = m.replace(old2, new2, 1)
    open('c:/chemgrid/src/app/main_window.py', 'w', encoding='utf-8').write(m)
    print('main_window.py OK')
else:
    print('main_window.py pattern NOT found')
    # 유사 패턴 탐색
    import re
    hits = [(x.start(), x.group()) for x in re.finditer(r'analyzer\.analyze\(', m)]
    for pos, hit in hits:
        print(f'  found: {repr(m[pos-30:pos+100])}')
