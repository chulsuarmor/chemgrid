"""
Phase 6-1B 통합 스크립트
=========================
각 에이전트의 최종 산출물을 `integrated/` 폴더로 병합합니다.

충돌 해결 (Master Plan 결정):
  1. orca_interface.py → Agent 07 버전
  2. draw.py → Agent 02 버전 (canvas.py 분리 포함)
  3. renderer.py → Agent 05 버전
  4. layer_logic.py → Agent 03 버전
  5. analyzer.py + engine_*.py → Agent 04 버전
  6. popup_3d.py → Agent 10 버전 (C2 수정)
"""
import os
import shutil
import ast

AGENTS = r"c:\chemgrid\agents"
SOURCE = r"c:\chemgrid\_source"
OUTPUT = r"c:\chemgrid\agents\10_testing_build\integrated"

# ============================================================
# 1. 에이전트 산출물 매핑 (파일 → 소스 경로)
# ============================================================
AGENT_FILES = {
    # Agent 02: 캔버스/그리기
    "draw.py": os.path.join(AGENTS, "02_canvas_interaction", "draw.py"),
    "canvas.py": os.path.join(AGENTS, "02_canvas_interaction", "canvas.py"),
    
    # Agent 07: ORCA DFT
    "orca_interface.py": os.path.join(AGENTS, "07_orca_dft", "orca_interface.py"),
    "electron_density_analyzer.py": os.path.join(AGENTS, "07_orca_dft", "electron_density_analyzer.py"),
    
    # Agent 05: 렌더링 엔진
    "renderer.py": os.path.join(AGENTS, "05_rendering_engine", "renderer.py"),
    
    # Agent 03: 루이스 구조
    "layer_logic.py": os.path.join(AGENTS, "03_lewis_structure", "layer_logic.py"),
    "lasso_selection.py": os.path.join(AGENTS, "03_lewis_structure", "lasso_selection.py"),
    
    # Agent 04: 화학 분석 엔진
    "analyzer.py": os.path.join(AGENTS, "04_analysis_engine", "analyzer.py"),
    "engine_core.py": os.path.join(AGENTS, "04_analysis_engine", "engine_core.py"),
    "engine_physics.py": os.path.join(AGENTS, "04_analysis_engine", "engine_physics.py"),
    "engine_resonance.py": os.path.join(AGENTS, "04_analysis_engine", "engine_resonance.py"),
    
    # Agent 10: 테스트/빌드 (C2 수정)
    "popup_3d.py": os.path.join(AGENTS, "10_testing_build", "fixed_popup_3d.py"),
}

# ============================================================
# 2. _source에서 가져올 파일 (에이전트가 수정하지 않은 파일)
# ============================================================
SOURCE_ONLY_FILES = [
    # 핵심 모듈 (변경 없음)
    "coord_utils.py",
    "chem_data.py",
    
    # 팝업 모듈 (Agent 06, 08 미착수)
    "popup_spectrum.py",
    "popup_nmr.py",
    "popup_uvvis.py",
    "popup_md.py",
    "popup_molorbital.py",
    
    # 유틸리티 모듈
    "batch_processor.py",
    "calculation_logger.py",
    "error_handler.py",
    "export_manager_enhanced.py",
    "history_manager.py",
    "iupac_analyzer.py",
    "molecule_comparator.py",
    "progress_tracker.py",
    "spectrum_analyzer.py",
    "spectrum_pdf_exporter.py",
    
    # 리소스
    "logo.ico",
    "logo.png",
    "bond.png",
    "eraser.png",
    "hand.png",
    "pen.png",
    "redo.png",
    "select.png",
    "undo.png",
]

# ============================================================
# 3. 통합 실행
# ============================================================
def main():
    # 출력 디렉토리 생성
    os.makedirs(OUTPUT, exist_ok=True)
    
    results = {"ok": [], "fail": [], "missing": []}
    
    print("=" * 70)
    print("Phase 6-1B 통합 빌드")
    print("=" * 70)
    
    # --- 에이전트 파일 복사 ---
    print("\n[1/3] 에이전트 산출물 복사...")
    for dest_name, src_path in AGENT_FILES.items():
        dest_path = os.path.join(OUTPUT, dest_name)
        
        if not os.path.exists(src_path):
            print(f"  ❌ MISSING: {src_path}")
            results["missing"].append(dest_name)
            continue
        
        shutil.copy2(src_path, dest_path)
        
        # Python 파일만 AST 검증
        if dest_name.endswith(".py"):
            try:
                with open(dest_path, encoding="utf-8") as f:
                    ast.parse(f.read())
                agent = os.path.basename(os.path.dirname(src_path))
                print(f"  ✅ {dest_name:40s} ← {agent}")
                results["ok"].append(dest_name)
            except SyntaxError as e:
                print(f"  ❌ SYNTAX ERROR: {dest_name} — {e}")
                results["fail"].append(dest_name)
        else:
            print(f"  ✅ {dest_name:40s} ← (resource)")
            results["ok"].append(dest_name)
    
    # --- _source 파일 복사 ---
    print("\n[2/3] _source 원본 파일 복사...")
    for fname in SOURCE_ONLY_FILES:
        src_path = os.path.join(SOURCE, fname)
        dest_path = os.path.join(OUTPUT, fname)
        
        if not os.path.exists(src_path):
            print(f"  ❌ MISSING: {src_path}")
            results["missing"].append(fname)
            continue
        
        shutil.copy2(src_path, dest_path)
        
        if fname.endswith(".py"):
            try:
                with open(dest_path, encoding="utf-8") as f:
                    ast.parse(f.read())
                print(f"  ✅ {fname:40s} ← _source")
                results["ok"].append(fname)
            except SyntaxError as e:
                print(f"  ❌ SYNTAX ERROR: {fname} — {e}")
                results["fail"].append(fname)
        else:
            print(f"  ✅ {fname:40s} ← _source (resource)")
            results["ok"].append(fname)
    
    # --- orca_history 폴더 생성 ---
    orca_hist = os.path.join(OUTPUT, "orca_history")
    os.makedirs(orca_hist, exist_ok=True)
    
    # --- .chem 샘플 파일 복사 ---
    for i in range(1, 10):
        chem = f"{i}.chem"
        src = os.path.join(SOURCE, chem)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OUTPUT, chem))
    
    # --- 결과 요약 ---
    print("\n" + "=" * 70)
    print(f"[3/3] 통합 결과 요약")
    print(f"  ✅ 성공: {len(results['ok'])}개")
    print(f"  ❌ 실패: {len(results['fail'])}개")
    print(f"  ⚠️ 누락: {len(results['missing'])}개")
    print(f"  📁 출력: {OUTPUT}")
    print("=" * 70)
    
    if results["fail"]:
        print("\n❌ 실패 파일 목록:")
        for f in results["fail"]:
            print(f"  - {f}")
    
    if results["missing"]:
        print("\n⚠️ 누락 파일 목록:")
        for f in results["missing"]:
            print(f"  - {f}")
    
    # 총 파일 수
    total = len(os.listdir(OUTPUT))
    print(f"\n통합 디렉토리 총 파일 수: {total}개")
    
    return len(results["fail"]) == 0 and len(results["missing"]) == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
