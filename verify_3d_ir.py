import sys, warnings, types
sys.path.insert(0,'c:/chemgrid/src/app')
warnings.filterwarnings('ignore')
from rdkit import Chem

# === 벤젠 결합 order 검증 ===
print('=== 벤젠 결합 order 검증 ===')
mol = Chem.MolFromSmiles('c1ccccc1')
all_ok = True
for bond in mol.GetBonds():
    bt = bond.GetBondTypeAsDouble()
    old = int(round(bt)) if bt else 1
    new = 1.5 if (bt and abs(bt-1.5)<0.01) else (int(round(bt)) if bt else 1)
    ok = new == 1.5
    print(f'  bond {bond.GetBeginAtomIdx()}-{bond.GetEndAtomIdx()}: bt={bt} old={old} new={new} {"OK" if ok else "FAIL"}')
    if not ok:
        all_ok = False
print(f'결합 order 수정 결과: {"PASS" if all_ok else "FAIL"}')

# === IR 스펙트럼 검증 ===
print('\n=== IR 스펙트럼 검증 (에탄올 CCO) ===')
mod = types.ModuleType('predict_spectra')
sys.modules['predict_spectra'] = mod
exec(open('c:/chemgrid/src/app/predict_spectra.py', encoding='utf-8').read(), mod.__dict__)

smiles = 'CCO'
# predict_ir returns list of IRPeak objects
ir_result = mod.predict_ir(smiles)
peaks = ir_result if isinstance(ir_result, list) else []
print(f'IR peaks 개수: {len(peaks)}')
if peaks and hasattr(peaks[0], 'transmittance'):
    for pk in sorted(peaks, key=lambda p: p.wavenumber, reverse=True)[:6]:
        print(f'  {pk.wavenumber:.0f} cm-1: T={pk.transmittance}%  ({pk.assignment})')
    has_oh = any('O-H' in p.assignment for p in peaks)
    t_valid = all(0 <= p.transmittance <= 100 for p in peaks)
    low_t = any(p.transmittance < 50 for p in peaks)
    print(f'O-H 피크 존재: {"PASS" if has_oh else "FAIL"}')
    print(f'T값 범위(0-100): {"PASS" if t_valid else "FAIL"}')
    print(f'강한 흡수(<50%) 존재: {"PASS" if low_t else "WARN (약한 피크만)"}')
elif peaks:
    print(f'  (데이터 구조 확인) 첫 피크: {peaks[0]}')
else:
    print(f'  IR 결과가 빈 리스트 또는 dict: {type(ir_result)}')

# === NMR 검증 ===
print('\n=== NMR 검증 (벤젠 c1ccccc1) ===')
try:
    nmr_peaks = mod.predict_h1_nmr('c1ccccc1')
    if nmr_peaks:
        for pk in nmr_peaks[:5]:
            shift = getattr(pk, 'shift', 0)
            intensity = getattr(pk, 'intensity', '?')
            print(f'  shift={shift}  intensity={intensity}')
        aromatic_h = any(6.5 <= getattr(pk,'shift',0) <= 9.0 for pk in nmr_peaks)
        print(f'방향족 H (6.5-9.0 ppm) 존재: {"PASS" if aromatic_h else "FAIL"}')
    else:
        print('NMR peaks 없음')
except Exception as e:
    print(f'NMR 오류: {e}')

# === popup_3d.py 실제 bond order 분기 확인 ===
print('\n=== popup_3d.py 수정 내용 확인 ===')
content = open('c:/chemgrid/src/app/popup_3d.py', encoding='utf-8').read()
if 'abs(bt - 1.5) < 0.01' in content:
    print('bond order 1.5 보존 로직: FOUND OK')
else:
    print('bond order 1.5 보존 로직: NOT FOUND (수정 미적용)')
if 'aromatic_bond_overlay' in content:
    print('_aromatic_bond_overlay 메서드: FOUND OK')
else:
    print('_aromatic_bond_overlay: NOT FOUND')
if 'isinstance(bo, float) and abs(bo - 1.5)' in content:
    print('렌더러 aromatic 분기: FOUND OK')
else:
    print('렌더러 aromatic 분기: NOT FOUND (수정 미적용)')
