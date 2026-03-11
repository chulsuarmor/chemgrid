"""에이전트별 .clinerules + context_plan/list/note.md 일괄 생성"""
import os
from pathlib import Path

ROOT = Path(r"c:\chemgrid")
AGENTS = ROOT / "agents"

# Worker용 .clinerules 템플릿 (공통 부분)
CLINERULES_TEMPLATE = """# AI Worker Instructions — ChemGrid Agent
# 이 파일은 {agent_name} 에이전트의 Cline 지침입니다.

## Role
당신은 ChemGrid 프로젝트의 **{agent_name}** Worker 에이전트입니다.
{role_desc}

## 🔗 절대 경로 참조 (반드시 읽으십시오)
- **Master Plan:** `c:\\chemgrid\\master_plan.md`
- **실수 기록:** `c:\\chemgrid\\docs\\ai\\mistakes.md`
- **원본 소스 (읽기 전용):** `c:\\chemgrid\\_source\\`
- **공유 보고서:** `c:\\chemgrid\\docs\\reports\\`

## Session Start Checklist
1. `c:\\chemgrid\\master_plan.md` 읽기 → Manager 지시 확인
2. 현재 폴더의 `context_plan.md`, `context_list.md`, `context_note.md` 읽기
3. `c:\\chemgrid\\docs\\ai\\mistakes.md` 읽기 → 이전 실수 확인
4. 작업 재개

## 핵심 규칙
1. **계획 먼저:** 코드 수정 전 계획 수립 → 사용자 승인 후 진행
2. **자가 검증:** 작업 후 `py -c "import ast; ast.parse(open('파일').read())"` 구문 체크
3. **도메인 격리:** {domain_files}만 수정 가능. 다른 에이전트 파일 절대 건드리지 말 것
4. **공유 파일:** {shared_note}
5. **원본 보존:** `_source/` 폴더는 읽기 전용 — 절대 수정 금지
6. **Python 실행:** `python` 아닌 `py` 명령어 사용
7. **좌표 정밀도:** 모든 좌표 `round(coord, 2)` — 0.01 단위

## Session End Checklist
1. 자가 검증 완료
2. `context_list.md`, `context_note.md` 업데이트
3. 실수 있으면 `c:\\chemgrid\\docs\\ai\\mistakes.md`에 추가
4. "Task Completed" 선언 후 세션 종료
"""

agents = {
    "01_ui_design": {
        "name": "🎨 UI/디자인",
        "role": "ChemGrid의 메인 윈도우(MainWindow), 툴바, 다이얼로그, 아이콘, 스타일을 전담합니다.",
        "domain": "draw.py(MainWindow 클래스), chem_data.py, *.png, *.ico",
        "shared": "draw.py는 Agent 02와 공유 — MainWindow 부분만 수정 (MoleculeCanvas 건드리지 말 것)",
        "plan": """# 📋 Agent 01: UI/디자인 — Context Plan
## 상위 Master Plan 기반 세부 실행 계획

### 1. 세부 구현 목표
- draw.py에서 MainWindow 클래스를 별도 파일(main_window.py)로 분리
- 6개 Dialog 클래스(FormulaDialog, SMILESDialog, IUPACDialog 등)를 dialogs.py로 분리
- 툴바 구성 로직을 toolbar.py로 분리
- 아이콘 리소스를 resources/ 폴더로 정리

### 2. 단계별 마일스톤
- Phase 1: draw.py 구조 분석 및 클래스 목록 정리
- Phase 2: MainWindow 분리
- Phase 3: Dialog 클래스 분리
- Phase 4: 자가 검증 (임포트 테스트)

> **상태:** 대기 중 — 승인 전 코드 수정 금지""",
        "tasks": """- [ ] draw.py의 MainWindow 클래스 구조 분석
- [ ] MainWindow → main_window.py 분리
- [ ] Dialog 클래스 → dialogs.py 분리
- [ ] 툴바 로직 → toolbar.py 분리
- [ ] 아이콘 리소스 정리
- [ ] 임포트 테스트 통과 확인""",
    },
    "02_canvas_interaction": {
        "name": "🖱️ 캔버스/그리기",
        "role": "화학 캔버스(MoleculeCanvas)의 마우스 이벤트, 선택, Undo/Redo, 줌/팬을 전담합니다.",
        "domain": "draw.py(MoleculeCanvas 클래스), coord_utils.py",
        "shared": "draw.py는 Agent 01과 공유 — MoleculeCanvas 부분만 수정",
        "plan": """# 📋 Agent 02: 캔버스/그리기 — Context Plan
## 세부 실행 계획

### 1. 목표
- draw.py에서 MoleculeCanvas 클래스를 별도 파일(canvas.py)로 분리
- 마우스 이벤트 핸들러 정리 (mousePressEvent, mouseMoveEvent 등)
- Undo/Redo 시스템 독립 모듈화
- coord_utils.py 개선 (그리드 스냅, 좌표 변환)

### 2. 마일스톤
- Phase 1: MoleculeCanvas 분석
- Phase 2: canvas.py로 분리
- Phase 3: Undo/Redo 모듈화
- Phase 4: 자가 검증

> **상태:** 대기 중""",
        "tasks": """- [ ] MoleculeCanvas 클래스 구조 분석
- [ ] MoleculeCanvas → canvas.py 분리
- [ ] Undo/Redo 시스템 모듈화
- [ ] coord_utils.py 개선
- [ ] 임포트 테스트 통과 확인""",
    },
    "03_lewis_structure": {
        "name": "🔬 루이스 구조",
        "role": "루이스 구조 레이어(VSEPR, 수소 배치, 전하 표시, 고립전자쌍)를 전담합니다.",
        "domain": "layer_logic.py(LewisRenderer), analyzer.py(Lewis 관련), chem_data.py",
        "shared": "layer_logic.py는 Agent 05와 공유(Lewis 부분만), analyzer.py는 Agent 04와 공유",
        "plan": """# 📋 Agent 03: 루이스 구조 — Context Plan

### 1. 목표
- layer_logic.py의 LewisRenderer 부분 정리 (VSEPR 기하구조, H 배치 알고리즘)
- 전하 표시 정확성 개선 (형식전하 계산)
- analyzer.py의 Lewis 데이터 생성 부분 리팩토링
- 고립전자쌍 렌더링 정밀도 향상

### 2. 마일스톤
- Phase 1: LewisRenderer 함수 목록 및 흐름도 작성
- Phase 2: H 배치 알고리즘 리팩토링
- Phase 3: 전하 표시 로직 정리
- Phase 4: 자가 검증 (분자 5종 테스트)

> **상태:** 대기 중""",
        "tasks": """- [ ] layer_logic.py LewisRenderer 구조 분석
- [ ] VSEPR H 배치 알고리즘 리팩토링
- [ ] 형식전하 계산 로직 정리
- [ ] 고립전자쌍 렌더링 개선
- [ ] 분자 5종 테스트 통과 확인""",
    },
    "04_analysis_engine": {
        "name": "⚗️ 화학 분석 엔진",
        "role": "SMILES 생성/검증, 공명구조, 물리적 특성 계산, 핵심 화학 알고리즘을 전담합니다.",
        "domain": "analyzer.py(핵심 알고리즘), engine_core.py, engine_physics.py, engine_resonance.py",
        "shared": "analyzer.py는 Agent 03과 공유 — 핵심 알고리즘 함수만 수정",
        "plan": """# 📋 Agent 04: 화학 분석 엔진 — Context Plan

### 1. 목표
- analyzer.py의 generate_smiles() 리팩토링 (1함수 → 단계별 분리)
- engine_core.py 정리 (원자 속성, 결합 분석)
- engine_physics.py 정리 (열역학, 에너지 계산)
- engine_resonance.py 정리 (공명 구조 알고리즘)

### 2. 마일스톤
- Phase 1: analyzer.py 함수별 책임 분석
- Phase 2: generate_smiles 단계 분리
- Phase 3: engine 모듈 통일성 확보
- Phase 4: 자가 검증 (SMILES 10종 비교)

> **상태:** 대기 중""",
        "tasks": """- [ ] analyzer.py 함수 목록 및 책임 분석
- [ ] generate_smiles() 리팩토링
- [ ] engine_core.py 정리
- [ ] engine_physics.py 정리
- [ ] engine_resonance.py 정리
- [ ] SMILES 10종 비교 검증""",
    },
    "05_rendering_engine": {
        "name": "🌈 렌더링 엔진",
        "role": "전자구름, ESP 맵, 이론적 구조(Theory) 렌더링, 오버레이 시각화를 전담합니다.",
        "domain": "renderer.py, layer_logic.py(TheoryRenderer), coord_utils.py",
        "shared": "layer_logic.py는 Agent 03과 공유(Theory 부분만), coord_utils.py는 Agent 02와 공유",
        "plan": """# 📋 Agent 05: 렌더링 엔진 — Context Plan

### 1. 목표
- renderer.py의 draw_clouds() 분리 (200줄 → 단계별 함수)
- v3.0/v3.1/v3.2 렌더링 코드 통합 정리
- 조준선(crosshair) 3중 렌더링 → 단일 책임으로 통합
- ESP 컬러맵 개선

### 2. 마일스톤
- Phase 1: renderer.py 함수 흐름도
- Phase 2: draw_clouds 분리
- Phase 3: 조준선 통합
- Phase 4: 시각 품질 검증

> **상태:** 대기 중""",
        "tasks": """- [ ] renderer.py 구조 분석
- [ ] draw_clouds() 단계별 분리
- [ ] v3.x 렌더링 코드 통합
- [ ] 조준선 3중 렌더링 → 단일 통합
- [ ] ESP 컬러맵 개선
- [ ] 시각 품질 검증""",
    },
    "06_3d_structure": {
        "name": "🧊 입체 구조(3D)",
        "role": "OpenGL 3D 분자 뷰어를 전담합니다.",
        "domain": "popup_3d.py, chem_data.py(반지름/색상 데이터)",
        "shared": "chem_data.py는 여러 에이전트 공유 — 반지름/색상 데이터 부분만 수정",
        "plan": """# 📋 Agent 06: 입체 구조(3D) — Context Plan

### 1. 목표
- popup_3d.py의 OpenGL 뷰어 코드 정리
- 회전/줌 조작 개선
- Ball-and-Stick + Space-filling 모드 전환
- 조명/셰이딩 개선

### 2. 마일스톤
- Phase 1: popup_3d.py 구조 분석
- Phase 2: 뷰어 컨트롤 리팩토링
- Phase 3: 렌더링 모드 정리
- Phase 4: 시각 검증

> **상태:** 대기 중""",
        "tasks": """- [ ] popup_3d.py 구조 분석
- [ ] OpenGL 뷰어 컨트롤 리팩토링
- [ ] 렌더링 모드 정리
- [ ] 조명/셰이딩 개선
- [ ] 시각 검증""",
    },
    "07_orca_dft": {
        "name": "⚛️ ORCA DFT",
        "role": "ORCA 6.1.1 인터페이스, DFT 계산 실행, 결과 파싱을 전담합니다.",
        "domain": "orca_interface.py, electron_density_analyzer.py",
        "shared": "독립 모듈 — 공유 파일 없음",
        "plan": """# 📋 Agent 07: ORCA DFT — Context Plan

### 1. 목표
- orca_interface.py 리팩토링 (인풋 생성 / 실행 / 파싱 분리)
- 에러 처리 강화 (ORCA 실행 실패, 수렴 실패 등)
- electron_density_analyzer.py 정리
- ORCA 경로: `c:\\chemgrid\\Orca.6.1.1\\orca.exe`

### 2. 마일스톤
- Phase 1: 현재 ORCA 인터페이스 분석
- Phase 2: 인풋/실행/파싱 3단계 분리
- Phase 3: 에러 처리 강화
- Phase 4: H2O 분자 DFT 테스트

> **상태:** 대기 중""",
        "tasks": """- [ ] orca_interface.py 구조 분석
- [ ] 인풋 생성 / 실행 / 파싱 분리
- [ ] 에러 처리 강화
- [ ] electron_density_analyzer.py 정리
- [ ] H2O DFT 테스트 통과""",
    },
    "08_spectroscopy": {
        "name": "📈 분광학 (중간관리자)",
        "role": "IR/Raman, NMR, UV-Vis, 오비탈/MD 4개 하위 에이전트를 조율하는 중간 관리자입니다.",
        "domain": "spectrum_pdf_exporter.py, phase_integration.py",
        "shared": "하위 에이전트(ir_raman, nmr, uvvis, orbital_md) 작업 검토 및 통합",
        "plan": """# 📋 Agent 08: 분광학 중간관리자 — Context Plan

### 1. 목표
- 4개 분광학 모듈의 공통 인터페이스 통일
- spectrum_pdf_exporter.py 정리 (PDF 내보내기)
- phase_integration.py 정리 (draw.py와의 연동 지점)
- 하위 에이전트 작업 결과 통합 검증

### 2. 마일스톤
- Phase 1: 공통 인터페이스 설계
- Phase 2: 하위 에이전트 활성화 및 조율
- Phase 3: 통합 테스트

> **상태:** 대기 중""",
        "tasks": """- [ ] 4개 분광학 모듈 공통 인터페이스 분석
- [ ] spectrum_pdf_exporter.py 정리
- [ ] phase_integration.py 정리
- [ ] 하위 에이전트 작업 결과 통합 검증""",
    },
    "08_spectroscopy/ir_raman": {
        "name": "🔴 IR/Raman 분광학",
        "role": "IR/Raman 스펙트럼 파싱, 시각화, ORCA 출력 연동을 전담합니다.",
        "domain": "spectrum_analyzer.py, popup_spectrum.py",
        "shared": "상위 Agent 08(중간관리자)의 지시를 따름",
        "plan": """# 📋 Agent 08a: IR/Raman — Context Plan

### 1. 목표
- spectrum_analyzer.py 리팩토링 (IR/Raman 파싱 로직)
- popup_spectrum.py 정리 (PyQt6 스펙트럼 다이얼로그)
- 피크 검출 알고리즘 개선
- 그래프 렌더링 품질 향상

### 2. 마일스톤
- Phase 1: 현재 코드 분석
- Phase 2: 파싱 로직 리팩토링
- Phase 3: UI 개선
- Phase 4: 샘플 분자 검증

> **상태:** 대기 중""",
        "tasks": """- [ ] spectrum_analyzer.py 분석
- [ ] IR/Raman 파싱 로직 리팩토링
- [ ] popup_spectrum.py UI 개선
- [ ] 피크 검출 알고리즘 검증""",
    },
    "08_spectroscopy/nmr": {
        "name": "🟢 NMR 분광학",
        "role": "NMR 시뮬레이션(¹H, ¹³C)을 전담합니다.",
        "domain": "popup_nmr.py",
        "shared": "상위 Agent 08의 지시를 따름",
        "plan": """# 📋 Agent 08b: NMR — Context Plan
### 1. 목표: popup_nmr.py 리팩토링, 화학적 이동 예측 개선
### 2. 마일스톤: 코드 분석 → 리팩토링 → 검증
> **상태:** 대기 중""",
        "tasks": """- [ ] popup_nmr.py 구조 분석
- [ ] NMR 시뮬레이션 로직 리팩토링
- [ ] 화학적 이동 예측 정확도 검증""",
    },
    "08_spectroscopy/uvvis": {
        "name": "🟣 UV-Vis 분광학",
        "role": "UV-Vis 흡수 스펙트럼 시뮬레이션을 전담합니다.",
        "domain": "popup_uvvis.py",
        "shared": "상위 Agent 08의 지시를 따름",
        "plan": """# 📋 Agent 08c: UV-Vis — Context Plan
### 1. 목표: popup_uvvis.py 리팩토링, 전이 에너지 계산 개선
### 2. 마일스톤: 코드 분석 → 리팩토링 → 검증
> **상태:** 대기 중""",
        "tasks": """- [ ] popup_uvvis.py 구조 분석
- [ ] UV-Vis 시뮬레이션 리팩토링
- [ ] 흡수 스펙트럼 시각화 검증""",
    },
    "08_spectroscopy/orbital_md": {
        "name": "🟠 분자 오비탈/MD",
        "role": "분자 오비탈 시각화 및 MD 궤적 애니메이션을 전담합니다.",
        "domain": "popup_molorbital.py, popup_md.py",
        "shared": "상위 Agent 08의 지시를 따름",
        "plan": """# 📋 Agent 08d: 오비탈/MD — Context Plan
### 1. 목표: popup_molorbital.py, popup_md.py 리팩토링
### 2. 마일스톤: 코드 분석 → 리팩토링 → 검증
> **상태:** 대기 중""",
        "tasks": """- [ ] popup_molorbital.py 분석 및 리팩토링
- [ ] popup_md.py 분석 및 리팩토링
- [ ] 시각화 품질 검증""",
    },
    "09_data_export": {
        "name": "📦 데이터/내보내기",
        "role": "분자 비교, 히스토리, 배치 처리, 내보내기, IUPAC 분석, 에러 핸들링을 전담합니다.",
        "domain": "molecule_comparator, history_manager, batch_processor, calculation_logger, export_manager_enhanced, spectrum_pdf_exporter, smiles_validator, iupac_analyzer, error_handler",
        "shared": "독립 모듈 — 공유 파일 없음",
        "plan": """# 📋 Agent 09: 데이터/내보내기 — Context Plan
### 1. 목표: 9개 유틸리티 모듈 정리 및 통합
### 2. 마일스톤: 모듈 분석 → 중복 제거 → API 통일 → 검증
> **상태:** 대기 중""",
        "tasks": """- [ ] 9개 모듈 구조 분석
- [ ] 중복 기능 식별 및 통합
- [ ] 공통 API 인터페이스 설계
- [ ] error_handler.py 에러 처리 통일
- [ ] 내보내기 기능 검증""",
    },
    "10_testing_build": {
        "name": "🧪 테스트/빌드",
        "role": "테스트 프레임워크 구축, CI/CD, PyInstaller 빌드를 전담합니다.",
        "domain": "모든 test_*.py, build_exe.py, validate_*.py, verify_*.py, run_*.bat",
        "shared": "모든 에이전트의 코드를 테스트 — 읽기 전용으로 참조",
        "plan": """# 📋 Agent 10: 테스트/빌드 — Context Plan
### 1. 목표: 테스트 체계 정리 (40+개 파일 → pytest 구조), 빌드 파이프라인
### 2. 마일스톤: 테스트 분석 → pytest 전환 → 빌드 검증
> **상태:** 대기 중""",
        "tasks": """- [ ] 기존 테스트 파일 40+ 분석
- [ ] pytest 기반 테스트 구조 설계
- [ ] 핵심 테스트 케이스 정리
- [ ] PyInstaller 빌드 스크립트 정리
- [ ] CI/CD 파이프라인 설계""",
    },
}

# 각 에이전트 폴더에 문서 생성
for agent_path, info in agents.items():
    agent_dir = AGENTS / agent_path
    agent_dir.mkdir(parents=True, exist_ok=True)
    
    # .clinerules
    rules = CLINERULES_TEMPLATE.format(
        agent_name=info["name"],
        role_desc=info["role"],
        domain_files=info["domain"],
        shared_note=info["shared"],
    )
    (agent_dir / ".clinerules").write_text(rules, encoding="utf-8")
    print(f"[OK] {agent_path}/.clinerules")
    
    # context_plan.md
    (agent_dir / "context_plan.md").write_text(info["plan"].strip() + "\n", encoding="utf-8")
    print(f"[OK] {agent_path}/context_plan.md")
    
    # context_list.md
    list_content = f"# 📋 {info['name']} — Task List\n## 최종 업데이트: 2026-02-28\n\n{info['tasks'].strip()}\n\n### 블로커\n- (없음)\n"
    (agent_dir / "context_list.md").write_text(list_content, encoding="utf-8")
    print(f"[OK] {agent_path}/context_list.md")
    
    # context_note.md
    note_content = f"# 📝 {info['name']} — Technical Notes\n## 기술적 판단 및 결정 기록\n\n(아직 기록 없음 — 작업 시작 후 여기에 기록)\n"
    (agent_dir / "context_note.md").write_text(note_content, encoding="utf-8")
    print(f"[OK] {agent_path}/context_note.md")

print("\n✅ 모든 에이전트 문서 생성 완료!")
