import pathlib
src = pathlib.Path('agents/10_testing_build/integrated/popup_3d.py').read_text(encoding='utf-8')

def chk(name, cond):
    s = 'PASS' if cond else 'FAIL'
    print(f'[{s}] {name}')
    return cond

ok = []
ok.append(chk('BUG-H1 AddHs',                   'mol = Chem.AddHs(mol)' in src))
ok.append(chk('BUG-H1 int키(atom_positions[i])', 'atom_positions[i]' in src))
ok.append(chk('BUG-O1 rx,ry=-ny,nx x3',         src.count('rx, ry = -ny, nx') >= 3))
ok.append(chk('BUG-C1 glColor4f',               'glColor4f' in src))
ok.append(chk('BUG-SF1 SCALE = 1.0',            'SCALE = 1.0' in src))
ok.append(chk('SPEC-1 predict_spectrum함수',      'def predict_spectrum_from_smiles' in src))
ok.append(chk('SPEC-2 IR+Raman+NMR+UV-Vis+MS',  all(t in src for t in ['IR','Raman','NMR','UV-Vis','MS'])))
ok.append(chk('SPEC-3 btn_vib_link',             'btn_vib_link' in src))
ok.append(chk('SPEC-4 btn_pdf',                  'btn_pdf' in src))
ok.append(chk('AI-1 5섹션 _SECTIONS',            'functional_group' in src and 'reactivity' in src))
ok.append(chk('DOCK-1 preset_combo',             'preset_combo' in src))
ok.append(chk('DOCK-1 _search_pdb',              'def _search_pdb' in src))
ok.append(chk('DOCK-2 클래스선언',               'class DockingVisualizationWidget' in src))
ok.append(chk('DOCK-2 viz_widget 배치',          'self.viz_widget = DockingVisualizationWidget' in src))
ok.append(chk('DOCK-2 update_docking 연결',      'self.viz_widget.update_docking' in src))
ok.append(chk('DOCK-2 QPainter+paintEvent',      'QPainter' in src and 'def paintEvent' in src))

fail = ok.count(False)
print(f'\n총 {len(ok)}개 / 실패: {fail}개')
print('ALL PASS' if fail == 0 else f'FAIL {fail}개 수정 필요')
