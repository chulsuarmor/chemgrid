# 📋 🧪 테스트/빌드 — Task List
## 최종 업데이트: 2026-03-01 01:29

### Phase 6-1A: Critical 버그 수정
- [x] C1: ORCA 경로 하드코딩 → 포터블 경로 (orca_interface.py)
- [x] C2: popup_3d.py `from PyQt6.QtOpenGL import GL` 제거
- [x] C3: draw.py `self.canvas.repaint()` → `self.update()`
- [x] C4: draw.py verification_report except 블록 메시지 분리
- [x] C5: draw.py `_analyze_dft_electron_density()` 하드코딩 경로 제거

### Phase 6-1A: Major 버그 수정
- [x] M1: draw.py 조준선 3중 렌더링 → 최상위 Z-INDEX 1회만
- [x] M2: renderer.py + draw.py 디버그 print 제거 (18 → 3개)
- [x] M5: progress_tracker Discord 보고 비활성화

### Phase 6-1B: 통합 빌드
- [x] 에이전트 산출물 분석 (07, 02, 05, 03, 04)
- [x] 충돌 이슈 1: orca_interface.py → Agent 07 채택
- [x] 충돌 이슈 2: draw.py → Agent 02 채택
- [x] 충돌 이슈 3: renderer.py → Agent 05 채택
- [x] layer_logic.py → Agent 03 채택
- [x] analyzer.py + engine_*.py → Agent 04 채택
- [x] popup_3d.py → Agent 10 채택 (C2 수정)
- [x] 통합 디렉토리 `integrated/` 생성 (48개 파일)
- [x] AST 구문 검증: 38/38 Python 파일 통과
- [x] conda import 테스트: 29/29 모듈 PASS

### Phase 6-3: 최종 통합 + 빌드
- [x] 명령 1: 에이전트 산출물 최종 병합 (26/26 파일 복사 성공, 6 신규)
- [x] base_spectrum.py metaclass 충돌 수정 (ABCMeta + sip.wrappertype 결합)
- [x] 명령 2: AST 구문 검증 36/36 PASS
- [x] 명령 2: Import 검증 전체 PASS (verify_phase63 + test_integration 29/29)
- [x] 명령 3: ChemDraw → ChemGrid 이름 변경 (19파일, 34건, 잔존 0)
- [x] AST 재검증 (이름 변경 후 통과)
- [x] 명령 3: PyInstaller 빌드 → ChemGrid.exe (110.4 MB)
- [x] ChemGrid.exe → c:\chemgrid\ChemGrid.exe 루트 복사

### Phase 6-4: v4 통합 + exe 재빌드 (NEW ✅)
- [x] 선행 에이전트 완료 확인 (01, 02, 05, 06 전원 완료)
- [x] 명령 1: Phase 6-4 병합 (9/9 파일 성공)
  - draw.py (+3258), main_window.py (+116), toolbar_setup.py (+2769)
  - canvas.py (+11145), coord_utils.py (-267)
  - renderer.py (+2444), popup_3d.py (+2779)
  - dialogs.py (변경없음), ui_utils.py (변경없음)
- [x] 명령 2: AST 구문 검증 37/37 PASS
- [x] 명령 2: Import 의존성 검증 20/20 PASS
- [x] 명령 3: ChemDraw 잔존 1건 수정 (coord_utils.py:3 → ChemGrid)
- [x] 명령 3: PyInstaller 빌드 → ChemGrid.exe (110.4 MB)
- [x] ChemGrid.exe → c:\chemgrid\ChemGrid.exe 루트 복사

### 검증 완료
- [x] 자가 검증: 4개 fixed_* 파일 AST 구문 체크 통과
- [x] 상세 검증: 27/27 테스트 PASS (verify_critical_fixes.py)
- [x] 통합 AST: 38/38 PASS (integrate_all.py)
- [x] 통합 Import: 29/29 PASS (test_integration.py, conda chemgrid)
- [x] Phase 6-3 AST: 36/36 PASS
- [x] Phase 6-3 Import: 전체 PASS
- [x] Phase 6-4 AST: 37/37 PASS
- [x] Phase 6-4 Import: 20/20 PASS
- [x] ChemGrid.exe 존재 확인: 110.4 MB

### 잔여 이슈 (비차단)
- [ ] popup_3d.py:85 — google.generativeai → google.genai FutureWarning (기능 정상)
- [x] GUI 실행 테스트 (E2E 검증 완료, _user_verification_10.py 통과)
- [ ] CI/CD 파이프라인 설계 (Phase 7)
