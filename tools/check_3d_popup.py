"""B1/B2 버그 검증 스크립트 — 3D 팝업 로드 가능성 확인"""
import sys, os, re
sys.path.insert(0, r'c:\chemgrid\agents\10_testing_build\integrated')

print("=" * 60)
print("B2 검증: popup_3d 임포트 가능 여부")
print("=" * 60)
try:
    from popup_3d import Molecule3DData, Molecule3DPopup, OPENGL_AVAILABLE, RDKIT_AVAILABLE, MATPLOTLIB_AVAILABLE
    print(f"✅ popup_3d import OK")
    print(f"   OPENGL_AVAILABLE   : {OPENGL_AVAILABLE}")
    print(f"   RDKIT_AVAILABLE    : {RDKIT_AVAILABLE}")
    print(f"   MATPLOTLIB_AVAILABLE: {MATPLOTLIB_AVAILABLE}")
    PHASE_C_OK = True
except ImportError as e:
    print(f"❌ popup_3d import FAIL: {e}")
    PHASE_C_OK = False

print()
print("=" * 60)
print("B2 검증: Molecule3DData 생성 테스트 (벤젠)")
print("=" * 60)
if PHASE_C_OK:
    try:
        # 벤젠 원자/결합 데이터 (canvas 좌표 기반)
        atoms = {
            (100, 100): {"main": "C"},
            (140, 100): {"main": "C"},
            (160, 135): {"main": "C"},
            (140, 170): {"main": "C"},
            (100, 170): {"main": "C"},
            (80,  135): {"main": "C"},
        }
        bonds = {
            ((100,100),(140,100)): 1,
            ((140,100),(160,135)): 2,
            ((160,135),(140,170)): 1,
            ((140,170),(100,170)): 2,
            ((100,170),(80,135)):  1,
            ((80,135),(100,100)):  2,
        }
        mol = Molecule3DData(atoms=atoms, bonds=bonds, smiles="c1ccccc1")
        print(f"✅ Molecule3DData 생성 OK")
        print(f"   num_atoms  : {mol.num_atoms}")
        print(f"   num_bonds  : {mol.num_bonds}")
        print(f"   coord_source: {mol.coord_source}")
        center = mol.get_center()
        print(f"   center     : ({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f})")
    except Exception as e:
        print(f"❌ Molecule3DData 생성 FAIL: {e}")

print()
print("=" * 60)
print("B1 검증: main_window.py open_3d_popup 로직 확인")
print("=" * 60)
mw_path = r'c:\chemgrid\agents\10_testing_build\integrated\main_window.py'
mw_src = open(mw_path, encoding='utf-8').read()

# open_3d_popup 함수 추출
m = re.search(r'(    def open_3d_popup.*?)(?=\n    def |\Z)', mw_src, re.DOTALL)
if m:
    func_body = m.group(1)
    print(f"✅ open_3d_popup 함수 발견 ({len(func_body)} chars)")
    print()
    print(func_body[:3000])
else:
    print("❌ open_3d_popup 함수 미발견")

print()
print("=" * 60)
print("검증 완료")
print("=" * 60)
