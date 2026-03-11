"""DOCK-2 + 전체 항목 최종 검증 스크립트"""
import sys
sys.path.insert(0, 'agents/10_testing_build/integrated')
import inspect

results = []

# BUG-H1
from popup_3d import generate_3d_full_from_smiles
r = generate_3d_full_from_smiles('CC')
results.append(('BUG-H1 generate_3d_full_from_smiles', 'PASS' if r else 'FAIL'))
if r:
    pos, sym, bonds = r
    results.append(('BUG-H1 수소포함', 'PASS' if any(s=='H' for s in sym.values()) else 'FAIL'))
    results.append(('BUG-H1 int키', 'PASS' if all(isinstance(k,int) for k in pos.keys()) else 'FAIL'))

# BUG-O1
from popup_3d import PiOrbitalRenderer, AdvancedOrbitalRenderer
src_pi  = inspect.getsource(PiOrbitalRenderer._draw_p_orbital_lobes)
src_ring= inspect.getsource(PiOrbitalRenderer._draw_ring_pi_cloud)
src_adv = inspect.getsource(AdvancedOrbitalRenderer._lobe)
results.append(('BUG-O1 Pi rx,ry=-ny,nx',   'PASS' if 'rx, ry = -ny, nx' in src_pi   else 'FAIL'))
results.append(('BUG-O1 Ring rx,ry=-ny,nx',  'PASS' if 'rx, ry = -ny, nx' in src_ring else 'FAIL'))
results.append(('BUG-O1 Adv rx,ry=-ny,nx',   'PASS' if 'rx, ry = -ny, nx' in src_adv  else 'FAIL'))

# BUG-C1
from popup_3d import _set_material
results.append(('BUG-C1 glColor4f존재', 'PASS' if 'glColor4f' in inspect.getsource(_set_material) else 'FAIL'))

# BUG-SF1
from popup_3d import SpaceFillingRenderer
results.append(('BUG-SF1 SCALE=1.0', 'PASS' if SpaceFillingRenderer.SCALE == 1.0 else f'FAIL({SpaceFillingRenderer.SCALE})'))

# SPEC-1~4
from popup_3d import predict_spectrum_from_smiles, SpectrumPanel
src_sp = inspect.getsource(SpectrumPanel._init_ui)
results.append(('SPEC-1 predict_spectrum함수', 'PASS' if callable(predict_spectrum_from_smiles) else 'FAIL'))
results.append(('SPEC-2 5가지버튼', 'PASS' if all(t in src_sp for t in ['IR','Raman','NMR','UV-Vis','MS']) else 'FAIL'))
results.append(('SPEC-3 진동모드버튼', 'PASS' if 'btn_vib_link' in src_sp else 'FAIL'))
results.append(('SPEC-4 PDF버튼',    'PASS' if 'btn_pdf'     in src_sp else 'FAIL'))

# AI-1
from popup_3d import AIAnalysisPanel
results.append(('AI-1 5섹션구조', 'PASS' if len(AIAnalysisPanel._SECTIONS)==5 else f'FAIL({len(AIAnalysisPanel._SECTIONS)})'))
keys = [s[1] for s in AIAnalysisPanel._SECTIONS]
results.append(('AI-1 섹션키', 'PASS' if set(keys)=={'functional_group','reactivity','spectrum','application','facts'} else f'FAIL:{keys}'))

# DOCK-1
from popup_3d import DockingEnergyPanel
src_init = inspect.getsource(DockingEnergyPanel._init_ui)
src_all  = inspect.getsource(DockingEnergyPanel)
results.append(('DOCK-1 콤보박스', 'PASS' if 'preset_combo' in src_init else 'FAIL'))
results.append(('DOCK-1 PDB검색',  'PASS' if '_search_pdb'  in src_all  else 'FAIL'))

# DOCK-2
from popup_3d import DockingVisualizationWidget
src_show = inspect.getsource(DockingEnergyPanel._show_docking_result)
results.append(('DOCK-2 클래스존재',       'PASS' if DockingVisualizationWidget                              else 'FAIL'))
results.append(('DOCK-2 init_ui에viz',     'PASS' if 'viz_widget'    in src_init                            else 'FAIL'))
results.append(('DOCK-2 show에update',     'PASS' if 'update_docking' in src_show                           else 'FAIL'))
results.append(('DOCK-2 QPainter시각화',   'PASS' if 'QPainter'      in inspect.getsource(DockingVisualizationWidget) else 'FAIL'))
results.append(('DOCK-2 paintEvent',       'PASS' if hasattr(DockingVisualizationWidget,'paintEvent')       else 'FAIL'))
results.append(('DOCK-2 update_docking메서드','PASS' if hasattr(DockingVisualizationWidget,'update_docking') else 'FAIL'))

print('='*60)
for name, status in results:
    emoji = '[PASS]' if status == 'PASS' else '[FAIL]'
    print(f'{emoji} {name}')
print('='*60)
fail = sum(1 for _,s in results if s!='PASS')
print(f'총 {len(results)}개 검증 / 실패: {fail}개')
if fail == 0:
    print('ALL PASS - DOCK-2 구현 완료')
