"""
Phase 6-3 최종 통합 스크립트
모든 에이전트 산출물을 integrated/ 폴더에 병합
"""
import shutil
import os

AGENTS_ROOT = r"c:\chemgrid\agents"
INTEGRATED = os.path.join(AGENTS_ROOT, "10_testing_build", "integrated")

# Agent별 파일 복사 목록 (context_plan.md 병합 우선순위 기반)
copies = [
    # Agent 07: ORCA DFT
    (os.path.join(AGENTS_ROOT, "07_orca_dft", "orca_interface.py"), os.path.join(INTEGRATED, "orca_interface.py")),
    (os.path.join(AGENTS_ROOT, "07_orca_dft", "electron_density_analyzer.py"), os.path.join(INTEGRATED, "electron_density_analyzer.py")),
    
    # Agent 04: 화학 분석 엔진
    (os.path.join(AGENTS_ROOT, "04_analysis_engine", "analyzer.py"), os.path.join(INTEGRATED, "analyzer.py")),
    (os.path.join(AGENTS_ROOT, "04_analysis_engine", "engine_core.py"), os.path.join(INTEGRATED, "engine_core.py")),
    (os.path.join(AGENTS_ROOT, "04_analysis_engine", "engine_physics.py"), os.path.join(INTEGRATED, "engine_physics.py")),
    (os.path.join(AGENTS_ROOT, "04_analysis_engine", "engine_resonance.py"), os.path.join(INTEGRATED, "engine_resonance.py")),
    
    # Agent 05: 렌더링 엔진
    (os.path.join(AGENTS_ROOT, "05_rendering_engine", "renderer.py"), os.path.join(INTEGRATED, "renderer.py")),
    
    # Agent 03: 루이스 구조
    (os.path.join(AGENTS_ROOT, "03_lewis_structure", "layer_logic.py"), os.path.join(INTEGRATED, "layer_logic.py")),
    (os.path.join(AGENTS_ROOT, "03_lewis_structure", "lasso_selection.py"), os.path.join(INTEGRATED, "lasso_selection.py")),
    
    # Agent 02: 캔버스/그리기
    (os.path.join(AGENTS_ROOT, "02_canvas_interaction", "canvas.py"), os.path.join(INTEGRATED, "canvas.py")),
    (os.path.join(AGENTS_ROOT, "02_canvas_interaction", "coord_utils.py"), os.path.join(INTEGRATED, "coord_utils.py")),
    
    # Agent 06: 3D 구조
    (os.path.join(AGENTS_ROOT, "06_3d_structure", "popup_3d.py"), os.path.join(INTEGRATED, "popup_3d.py")),
    
    # Agent 01: UI/디자인 (draw.py 포함 — 최우선순위)
    (os.path.join(AGENTS_ROOT, "01_ui_design", "draw.py"), os.path.join(INTEGRATED, "draw.py")),
    (os.path.join(AGENTS_ROOT, "01_ui_design", "main_window.py"), os.path.join(INTEGRATED, "main_window.py")),
    (os.path.join(AGENTS_ROOT, "01_ui_design", "dialogs.py"), os.path.join(INTEGRATED, "dialogs.py")),
    (os.path.join(AGENTS_ROOT, "01_ui_design", "toolbar_setup.py"), os.path.join(INTEGRATED, "toolbar_setup.py")),
    (os.path.join(AGENTS_ROOT, "01_ui_design", "ui_utils.py"), os.path.join(INTEGRATED, "ui_utils.py")),
    
    # Agent 08: 분광학
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "base_spectrum.py"), os.path.join(INTEGRATED, "base_spectrum.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "ir_raman", "popup_spectrum.py"), os.path.join(INTEGRATED, "popup_spectrum.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "ir_raman", "spectrum_analyzer.py"), os.path.join(INTEGRATED, "spectrum_analyzer.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "nmr", "popup_nmr.py"), os.path.join(INTEGRATED, "popup_nmr.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "uvvis", "popup_uvvis.py"), os.path.join(INTEGRATED, "popup_uvvis.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "orbital_md", "popup_molorbital.py"), os.path.join(INTEGRATED, "popup_molorbital.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "orbital_md", "popup_md.py"), os.path.join(INTEGRATED, "popup_md.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "spectrum_pdf_exporter.py"), os.path.join(INTEGRATED, "spectrum_pdf_exporter.py")),
    (os.path.join(AGENTS_ROOT, "08_spectroscopy", "phase_integration.py"), os.path.join(INTEGRATED, "phase_integration.py")),
]

# Agent 09: 분석만 완료, 코드는 통합본 유지 (복사 불필요)
# chem_data.py: 통합본 유지 (변경 없음)

print("=" * 60)
print("Phase 6-3 최종 통합: 에이전트 산출물 병합")
print("=" * 60)

ok_count = 0
fail_count = 0
new_files = []

for src, dst in copies:
    basename = os.path.basename(dst)
    if os.path.exists(src):
        is_new = not os.path.exists(dst)
        shutil.copy2(src, dst)
        status = "NEW" if is_new else "UPD"
        if is_new:
            new_files.append(basename)
        print(f"  ✅ [{status}] {basename} ← {os.path.relpath(src, AGENTS_ROOT)}")
        ok_count += 1
    else:
        print(f"  ❌ MISSING: {src}")
        fail_count += 1

print(f"\n{'=' * 60}")
print(f"결과: {ok_count} 복사 성공, {fail_count} 실패")
if new_files:
    print(f"신규 파일: {', '.join(new_files)}")
print(f"{'=' * 60}")

# 최종 파일 카운트
py_files = [f for f in os.listdir(INTEGRATED) if f.endswith('.py')]
all_files = os.listdir(INTEGRATED)
print(f"\nintegrated/ 현황: {len(py_files)} Python 파일, {len(all_files)} 전체 파일/폴더")
