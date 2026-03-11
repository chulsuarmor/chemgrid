"""
ChemGrid 프로젝트 재구조화 스크립트
Manager AI가 실행하여 루트 파일을 정리하고 에이전트 워크스페이스를 구축합니다.
"""
import os
import shutil
from pathlib import Path

ROOT = Path(r"c:\chemgrid")
SOURCE = ROOT / "_source"
AGENTS = ROOT / "agents"
DOCS = ROOT / "docs"
TOOLS = ROOT / "tools"
EXTERNAL = ROOT / "external"

# ============================================================
# STEP 1: 폴더 구조 생성
# ============================================================
folders_to_create = [
    DOCS / "ai" / "skills",
    DOCS / "reports",
    DOCS / "references",
    TOOLS,
    EXTERNAL,
    AGENTS / "01_ui_design",
    AGENTS / "02_canvas_interaction",
    AGENTS / "03_lewis_structure",
    AGENTS / "04_analysis_engine",
    AGENTS / "05_rendering_engine",
    AGENTS / "06_3d_structure",
    AGENTS / "07_orca_dft",
    AGENTS / "08_spectroscopy" / "ir_raman",
    AGENTS / "08_spectroscopy" / "nmr",
    AGENTS / "08_spectroscopy" / "uvvis",
    AGENTS / "08_spectroscopy" / "orbital_md",
    AGENTS / "09_data_export",
    AGENTS / "10_testing_build",
]

for folder in folders_to_create:
    folder.mkdir(parents=True, exist_ok=True)
    print(f"[CREATE] {folder}")

# ============================================================
# STEP 2: 루트 파일 분류 및 이동
# ============================================================

# .md 문서 → docs/reports/ (Manager 전용 문서 제외)
md_to_reports = [
    "4_CORE_FIXES_COMPLETE.md",
    "4_TASKS_COMPLETION_REPORT.md",
    "BUGFIX_COMPLETION_REPORT.md",
    "CODE_CHANGES_VERIFICATION.md",
    "CRITICAL_BUGFIX_SUMMARY.md",
    "DELIVERABLES_CHECKLIST.md",
    "DETAILED_CODE_CHANGES.md",
    "DFT_ELECTRON_DENSITY_IMPLEMENTATION.md",
    "DFT_INTEGRATION_CHECKLIST.md",
    "DFT_QUICK_REFERENCE.md",
    "EPSILON_TOLERANCE_IMPLEMENTATION_REPORT.md",
    "EVALUATION_REPORT.md",
    "FEATURE_COMPLETION_REPORT.md",
    "FINAL_100_COMPLETION.md",
    "FINAL_PHYSICAL_INTEGRITY_REPORT.md",
    "FINAL_SUBMISSION_SUMMARY.md",
    "FOLDER_REORGANIZATION_GUIDE.md",
    "IMPROVEMENT_PLAN.md",
    "INTEGRATION_CHECKLIST.md",
    "INTEGRATION_COMPLETE.md",
    "METHODOLOGY.md",
    "MISSING_FEATURES_LIST.md",
    "PROJECT_INDEX.md",
    "README_EVALUATION.md",
    "README.md",
    "SPECTROSCOPY_REFERENCE.md",
    "SUBAGENT_COMPLETION_SUMMARY.txt",
    "SUBAGENT_DFT_COMPLETION_REPORT.md",
    "SUBAGENT_FINAL_REPORT_BUGFIX.md",
    "SUBAGENT_FINAL_REPORT.txt",
    "TECHNICAL_SPECIFICATIONS.md",
    "V3_2_ACTUAL_FIXES.md",
    "V3_2_FINAL_FIXES.md",
    "V3_2_FINAL_PHYSICAL_FIXES.md",
    "V3_2_QUICK_REFERENCE.md",
    "VISUAL_ENGINE_V3_1_AGGRESSIVE_FIX.md",
    "VISUAL_ENGINE_V3_2_INTERPRETIVE.md",
    "VISUAL_ENGINE_V3_REFACTORING_REPORT.md",
    "VISUAL_REFACTORING_SUMMARY.md",
    "WORK_SUMMARY.md",
    "작업_완료_보고서.md",
]

# .txt 문서 → docs/reports/
txt_to_reports = [
    "4_TASKS_SUMMARY.txt",
    "ACTUAL_FIX_PROOF.txt",
    "CODE_VERIFICATION.txt",
    "COMPLETION_STATUS.txt" if (ROOT / "COMPLETION_STATUS.txt").exists() else None,
    "EXECUTION_SUMMARY.txt",
    "FINAL_100_POINT_CERTIFICATION.txt",
    "GREP_VERIFICATION.txt",
    "IMPLEMENTATION_COMPLETE.txt",
    "output.txt",
    "RENDERER_ACTUAL_CODE.py",
    "VERIFICATION_OUTPUT.txt",
    "VERIFICATION_PROOF.txt",
]

# 도구/스크립트 → tools/
to_tools = [
    "build_chemdraw_en.bat",
    "build_chemdraw.bat",
    "build_chemgrid.bat",
    "run_progress.bat",
    "run_test.bat",
    "run_validator.bat",
    "test_4_fixes.bat",
    "test_4_tasks.bat",
    "check_syntax.py",
    "test_syntax.py",
    "diagnose.py",
    "verify_4_fixes.py",
    "_move_files.py",
    "requirements_advanced.txt",
    "ChemDraw.spec",
    "ChemGrid.spec",
]

# 외부 도구 참조 → external/ (바이너리는 이동하지 않고 .lnk만)
to_external = [
    "Anaconda Prompt.lnk",
    "Visual Studio Code.lnk",
]

# AI 관련 파일 (루트에 유지하거나 정리)
ai_files_to_keep_root = [
    # Manager 전용 - 루트에 유지
    # master_plan.md (새로 생성)
    # context_list.md (새로 생성)  
    # context_note.md (새로 생성)
    # .clinerules (기존 유지)
]

ai_files_to_remove = [
    # 기존 AI 관련 파일 → docs/ 로 이동
    "AGENTS.md",
    "BOOTSTRAP.md",
    "CLAUDE.md",
    "HEARTBEAT.md",
    "IDENTITY.md",
    "SOUL.md",
    "TOOLS.md",
    "USER.md",
    "_SUBAGENT_READY.txt",
]

def safe_move(src, dst):
    """파일 안전 이동 (존재하면 이동, 없으면 스킵)"""
    src_path = ROOT / src
    if src_path.exists():
        dst_path = dst / src
        if not dst_path.exists():
            shutil.move(str(src_path), str(dst_path))
            print(f"[MOVE] {src} → {dst.relative_to(ROOT)}/")
        else:
            print(f"[SKIP] {src} (이미 존재)")
    else:
        print(f"[SKIP] {src} (파일 없음)")

# 실행
print("\n" + "="*60)
print("STEP 2: 루트 파일 이동")
print("="*60)

for f in md_to_reports:
    safe_move(f, DOCS / "reports")

for f in txt_to_reports:
    if f: safe_move(f, DOCS / "reports")

for f in to_tools:
    safe_move(f, TOOLS)

for f in to_external:
    safe_move(f, EXTERNAL)

for f in ai_files_to_remove:
    safe_move(f, DOCS / "ai")

# ============================================================
# STEP 3: 에이전트 폴더에 소스 파일 복사
# ============================================================
print("\n" + "="*60)
print("STEP 3: 에이전트 폴더에 소스 파일 복사")
print("="*60)

agent_files = {
    "01_ui_design": [
        "draw.py", "chem_data.py",
        "logo.ico", "logo.png",
        "bond.png", "pen.png", "hand.png", "eraser.png", "select.png",
        "undo.png", "redo.png",
    ],
    "02_canvas_interaction": [
        "draw.py", "chem_data.py", "coord_utils.py",
    ],
    "03_lewis_structure": [
        "layer_logic.py", "analyzer.py", "chem_data.py",
        "engine_core.py", "engine_physics.py", "engine_resonance.py",
    ],
    "04_analysis_engine": [
        "analyzer.py", "engine_core.py", "engine_physics.py", "engine_resonance.py",
        "chem_data.py",
    ],
    "05_rendering_engine": [
        "renderer.py", "layer_logic.py", "chem_data.py", "coord_utils.py",
    ],
    "06_3d_structure": [
        "popup_3d.py", "chem_data.py",
    ],
    "07_orca_dft": [
        "orca_interface.py", "electron_density_analyzer.py",
    ],
    "08_spectroscopy/ir_raman": [
        "spectrum_analyzer.py", "popup_spectrum.py",
    ],
    "08_spectroscopy/nmr": [
        "popup_nmr.py",
    ],
    "08_spectroscopy/uvvis": [
        "popup_uvvis.py",
    ],
    "08_spectroscopy/orbital_md": [
        "popup_molorbital.py", "popup_md.py",
    ],
    "09_data_export": [
        "molecule_comparator.py", "history_manager.py", "batch_processor.py",
        "calculation_logger.py", "export_manager_enhanced.py",
        "spectrum_pdf_exporter.py", "smiles_validator.py",
        "iupac_analyzer.py", "error_handler.py",
    ],
    "10_testing_build": [
        "build_exe.py",
        "comprehensive_test.py", "quick_test.py", "quick_test_pyridine.py",
        "simple_test.py", "manual_test.py", "minimal_test.py",
        "test_comprehensive.py", "test_dft_analyzer.py",
        "test_hydrogen_parsing.py", "test_import.py", "test_orca.py",
        "test_parser_standalone.py", "test_phase4.py",
        "test_pyridine_fix.py", "test_pyridine_only.py",
        "test_pyridine_hydrogen_fix.py", "test_run.py",
        "test_simple_import.py", "test_simple.py",
        "test_strict_column_check.py", "test_syntax.py",
        "test_additional_molecules.py",
        "run_test.py", "run_test.bat", "run_tests.bat",
        "run_single_test.py", "run_test_simple.py",
        "run_debug.bat", "run_final_test.bat",
        "run_validation.bat", "run_verification.bat",
        "validate_fix.py", "validate_molecules.py",
        "validate_phase_integration.py", "validate_syntax.py",
        "verify_and_build_exe.py", "verify_atom5_fix.py",
        "verify_charges.py", "verify_fix.py",
        "verification_report.py", "visual_verify_v32.py",
        "quick_build.py", "quick_validate.py",
        "molecule_validator.py", "smiles_validator.py",
        "debug_extract.py", "debug_test.py",
        "diagnose_issue.py", "find_and_fix_exe.py",
        "STEP1_IMPORT_VALIDATION.py", "STEP1_SYNTAX_CHECK.py",
        "STEP2_MOLECULE_TEST.py",
        "progress_tracker.py", "phase_a_progress.py",
    ],
}

# 분광학 중간관리자 폴더에 공통 파일 복사
agent_files["08_spectroscopy"] = [
    "spectrum_pdf_exporter.py", "phase_integration.py",
]

for agent_path, files in agent_files.items():
    agent_dir = AGENTS / agent_path
    agent_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        src = SOURCE / f
        dst = agent_dir / f
        if src.exists() and not dst.exists():
            shutil.copy2(str(src), str(dst))
            print(f"[COPY] {f} → agents/{agent_path}/")
        elif not src.exists():
            print(f"[SKIP] {f} (소스 없음)")

# _source 내 .md 파일들도 docs/reports로 복사
print("\n[INFO] _source 내 문서 파일 → docs/reports/ 복사")
for f in SOURCE.glob("*.md"):
    dst = DOCS / "reports" / f.name
    if not dst.exists():
        shutil.copy2(str(f), str(dst))
        print(f"[COPY] _source/{f.name} → docs/reports/")

# .chem 샘플 파일 → _source에 유지 (이미 있음)

print("\n" + "="*60)
print("재구조화 완료!")
print("="*60)

# 남은 루트 파일 목록 출력
print("\n[INFO] 루트에 남은 파일:")
for item in sorted(ROOT.iterdir()):
    if item.is_file() and item.name not in [".clinerules", ".clineignore", "_reorganize.py"]:
        print(f"  - {item.name}")
