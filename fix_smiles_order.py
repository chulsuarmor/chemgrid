"""BUG-B: _last_drawn_smiles를 analyze() 호출 전에 설정"""
m = open('c:/chemgrid/src/app/main_window.py', encoding='utf-8').read()

# 현재 순서 (잘못됨):
#   analyze(smiles=getattr(self.cv, '_last_drawn_smiles', None))  ← 이전 smiles 사용
#   self.cv._last_drawn_smiles = smiles  ← 새 smiles 늦게 설정

old_block = (
    "self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, smiles=getattr(self.cv, '_last_drawn_smiles', None))\n"
    "                # [BUG-03 Fix] 확정된 SMILES를 태그로 저장 — 하위 파이프라인 재생성 오류 방지\n"
    "                self.cv._last_drawn_smiles = smiles\n"
    "                self.cv._last_drawn_mol_name = mol_name"
)

new_block = (
    "# [BUG-B FIX] _last_drawn_smiles를 analyze() 전에 먼저 설정해야 현재 SMILES가 주입됨\n"
    "                self.cv._last_drawn_smiles = smiles\n"
    "                self.cv._last_drawn_mol_name = mol_name\n"
    "                self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, smiles=smiles)"
)

if old_block in m:
    m = m.replace(old_block, new_block, 1)
    open('c:/chemgrid/src/app/main_window.py', 'w', encoding='utf-8').write(m)
    print('BUG-B 수정 완료: smiles 대입 순서 역전')
else:
    # 실제 공백/줄바꿈이 다를 수 있으므로 더 단순한 패턴 탐색
    import re
    pattern = r'(self\.cv\.analysis_results = self\.cv\.analyzer\.analyze\([^\)]+\))\s*\n(\s*# \[BUG-03 Fix\][^\n]*\n\s*self\.cv\._last_drawn_smiles = smiles\n\s*self\.cv\._last_drawn_mol_name = mol_name)'
    def replacer(m2):
        return (
            '# [BUG-B FIX] _last_drawn_smiles를 analyze() 전에 먼저 설정\n'
            '                self.cv._last_drawn_smiles = smiles\n'
            '                self.cv._last_drawn_mol_name = mol_name\n'
            '                self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, smiles=smiles)'
        )
    new_m, count = re.subn(pattern, replacer, m)
    if count > 0:
        open('c:/chemgrid/src/app/main_window.py', 'w', encoding='utf-8').write(new_m)
        print(f'BUG-B regex 수정 완료 ({count}회)')
    else:
        print('BUG-B 패턴 NOT found — 수동 확인 필요')
        # 정확한 위치 출력
        idx = m.find('self.cv._last_drawn_smiles = smiles')
        print(f'smiles assign at {idx}:', repr(m[max(0,idx-100):idx+80]))
