"""
통합 빌드 import 테스트
========================
conda chemgrid 환경에서 각 모듈의 import를 테스트합니다.
PyQt6, RDKit, PyOpenGL이 설치된 환경에서 실행해야 합니다.
"""
import sys
import os
import traceback

# 통합 디렉토리를 sys.path에 추가
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

print("=" * 70)
print("통합 빌드 Import 테스트")
print(f"Python: {sys.version}")
print(f"경로: {SCRIPT_DIR}")
print("=" * 70)

# 테스트할 모듈 목록 (의존성 순서)
MODULES = [
    # 1단계: 의존성 없는 기본 모듈
    ("chem_data", "화학 데이터"),
    ("coord_utils", "좌표 유틸리티"),
    ("engine_core", "분석 엔진 코어"),
    ("engine_physics", "분석 엔진 물리"),
    ("engine_resonance", "분석 엔진 공명"),
    
    # 2단계: 1단계에 의존
    ("analyzer", "분석기"),
    ("lasso_selection", "Lasso 선택"),
    
    # 3단계: PyQt6 의존
    ("renderer", "렌더러 (CloudRenderer)"),
    ("layer_logic", "레이어 로직 (LewisRenderer)"),
    ("canvas", "캔버스 (MoleculeCanvas)"),
    
    # 4단계: 복합 의존
    ("electron_density_analyzer", "전자 밀도 분석"),
    ("orca_interface", "ORCA 인터페이스"),
    ("popup_3d", "3D 팝업"),
    
    # 5단계: 유틸리티
    ("error_handler", "오류 핸들러"),
    ("calculation_logger", "계산 로거"),
    ("history_manager", "히스토리 매니저"),
    ("iupac_analyzer", "IUPAC 분석기"),
    ("molecule_comparator", "분자 비교기"),
    ("batch_processor", "배치 프로세서"),
    ("export_manager_enhanced", "내보내기 관리자"),
    ("spectrum_analyzer", "스펙트럼 분석기"),
    ("spectrum_pdf_exporter", "스펙트럼 PDF 내보내기"),
    ("progress_tracker", "진행 추적기"),
    
    # 6단계: 팝업 (스펙트럼)
    ("popup_spectrum", "스펙트럼 팝업"),
    ("popup_nmr", "NMR 팝업"),
    ("popup_uvvis", "UV-Vis 팝업"),
    ("popup_md", "MD 팝업"),
    ("popup_molorbital", "분자 오비탈 팝업"),
    
    # 7단계: 메인
    ("draw", "메인 윈도우 (draw.py)"),
]

results = {"pass": [], "fail": [], "warn": []}

for mod_name, desc in MODULES:
    try:
        mod = __import__(mod_name)
        print(f"  ✅ PASS  {mod_name:30s}  ({desc})")
        results["pass"].append(mod_name)
    except ImportError as e:
        # import 오류 → 의존 패키지 문제일 수 있음
        err_msg = str(e)
        if any(pkg in err_msg for pkg in ["PyQt6", "rdkit", "OpenGL", "matplotlib"]):
            print(f"  ⚠️ WARN  {mod_name:30s}  패키지 미설치: {err_msg}")
            results["warn"].append(mod_name)
        else:
            print(f"  ❌ FAIL  {mod_name:30s}  {err_msg}")
            results["fail"].append(mod_name)
    except Exception as e:
        print(f"  ❌ FAIL  {mod_name:30s}  {type(e).__name__}: {e}")
        results["fail"].append(mod_name)

print("\n" + "=" * 70)
print(f"결과 요약:")
print(f"  ✅ PASS: {len(results['pass'])}개")
print(f"  ⚠️ WARN: {len(results['warn'])}개 (패키지 의존성)")
print(f"  ❌ FAIL: {len(results['fail'])}개")
print("=" * 70)

if results["fail"]:
    print("\n❌ 실패 모듈 상세:")
    for mod_name in results["fail"]:
        print(f"\n--- {mod_name} ---")
        try:
            __import__(mod_name)
        except Exception:
            traceback.print_exc()

sys.exit(1 if results["fail"] else 0)
