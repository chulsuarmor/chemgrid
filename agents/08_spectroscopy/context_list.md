# 📋 📈 분광학 (중간관리자) — Task List
## 최종 업데이트: 2026-02-28 23:56

### Phase 1: 분석 및 현황 파악 (중간관리자)
- [x] 전체 코드 분석 (8개 파일) — 원본과 100% 동일 확인
- [x] 이슈 9건 식별 (S1~S9: Critical 2, Major 4, Minor 3)
- [x] master_plan.md 최신 현황 반영 확인
- [x] context_note.md 기술 판단 기록

### Phase 2: BaseSpectrumPopup 공통 인터페이스 설계 (중간관리자)
- [x] base_spectrum.py 설계 확정 (context_plan.md에 초안 존재)
- [x] 각 popup 클래스의 공통/개별 메서드 분류 확정
- [x] ✅ base_spectrum.py 생성 완료 — AST 검증 OK

### Phase 3: 하위 에이전트 작업 하달 및 조율
- [x] 08a (IR/Raman): context_plan.md에 작업 시작 지시 완료
- [x] 08b (NMR): context_plan.md에 작업 시작 지시 완료
- [x] 08c (UV-Vis): context_plan.md에 작업 시작 지시 완료
- [x] 08d (오비탈/MD): context_plan.md에 작업 시작 지시 완료

### Phase 4: 중간관리자 직접 담당
- [x] ✅ S2 수정: spectrum_pdf_exporter.py QListWidget() → QListWidgetItem() — AST 검증 OK
- [x] ✅ phase_integration.py print→logging 교체 — AST 검증 OK
- [x] ✅ spectrum_pdf_exporter.py import logging 추가 — AST 검증 OK

### Phase 4.5: 하위 에이전트 미착수 → 중간관리자 직접 S1~S9 패치 수행
- [x] ✅ ir_raman/spectrum_analyzer.py — S1(절대경로→argparse), S3(backend_qtagg), S5(logging 7건), S9(Raman scatter 정규화 2곳) — AST OK
- [x] ✅ ir_raman/popup_spectrum.py — S5(logging 추가), S6(try relative/absolute import) — AST OK
- [x] ✅ nmr/popup_nmr.py — S3(backend_qtagg), S5(logging 1건), S7(setSizePolicy→QSizePolicy enum) — AST OK
- [x] ✅ uvvis/popup_uvvis.py — S3(backend_qtagg), S5(logging 1건) — AST OK
- [x] ✅ orbital_md/popup_molorbital.py — S3(backend_qtagg), S5(logging 1건), S8(plt.colorbar→fig.colorbar 2곳) — AST OK
- [x] ✅ orbital_md/popup_md.py — S3(backend_qtagg), S5(logging 1건) — AST OK

### Phase 5: 통합 검증
- [x] 전체 9개 파일 AST 구문 검증 OK (conda chemgrid Python 3.12.12)
- [ ] 런타임 import 검증 (PyQt6 GUI 필요 — 런타임 검증 별도)
- [ ] PDF 내보내기 통합 테스트

### Phase 6: 스펙트럼 시각/자연어 통합 분석 (Manager 긴급지시)
- [x] `docs/exports/spectra_assets/` 내부 누락된 21장 시각/자연어 분석 수행 (Gemini 3.1 Pro 활용)
- [x] `docs/reports/spectrum_vision_analysis_report.md` 업데이트 완료

### 잔여 작업 (Phase 7에서 진행)
- [ ] BaseSpectrumPopup 상속 적용 (5개 클래스 리팩토링 — Agent 06 3D 팝업 통합 시 수행)
- [ ] Agent 07 ORCA 파서 인터페이스 연동 확인

### 블로커 해결 현황
- ~~**PyQt6/matplotlib 미설치**~~ → ✅ conda 환경 `chemgrid`에 설치 완료
- ~~**하위 에이전트 미착수**~~ → ✅ 중간관리자가 간단 패치(S1~S9) 직접 수행 완료
- [ ] **Agent 07 산출물 미확인** → ORCA 파서 인터페이스 변경 여부 확인 필요
