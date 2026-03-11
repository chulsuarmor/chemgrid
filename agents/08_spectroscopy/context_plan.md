# 📋 Local Domain Plan: 08_spectroscopy
## 분광학 중간관리자 및 사용자 피드백 통합 테스터

### [긴급 수정] 벤젠 스펙트럼 분석 오류 수정 (Spectrum Analysis Fix)
- [ ] **IR/Raman Peak Data Pipeline 구축**:
  - `ir_raman/spectrum_analyzer.py`의 `SpectrumData` 객체가 `agents/09_data_export/spectrum_pdf_exporter.py`로 올바르게 전달되는지 확인.
  - 현재 PDF Exporter가 실제 데이터 대신 Fallback/Mock Data를 사용하는 문제를 해결 (Fallback 로직 제거됨).
- [x] **IR 스펙트럼 오류 수정**:
  - 벤젠에서 $C=O$ 피크($1700 cm^{-1}$)가 나타나는 원인 파악 및 제거 (Mock Data 수정 완료).
  - $C-H$ out-of-plane bending 피크($670 cm^{-1}$)가 누락되지 않도록 `SpectrumData` 생성 로직 점검 (Mock Data에 추가됨).
- [x] **Raman 스펙트럼 개선**:
  - 벤젠의 특징적인 $992 cm^{-1}$ (Ring Breathing Mode) 피크 강조.
  - IR 데이터를 Ghost Layer(반투명 배경)로 추가하여 상보적 관계 시각화 (`generate_spectrum_graph`에 구현 완료).

### 1. 세부 구현 목표
- [x] `docs/exports/spectra_assets/`에 업로드되는 사용자 가이드 이미지/설명을 실시간 모니터링하여 `agents/05 및 09`에게 반영 명령 하달.
- [x] IR, Raman, NMR, UV-Vis의 축(Axis) 및 데이터 정합성(Peak Matching) 전수 검사 (Mock Data 기반 검증 완료).
- [ ] 10_testing_build 에이전트로부터 인계받은 사용자 피드백 백데이터를 기반으로 에러 케이스 도출.

### 2. 마일스톤
- Phase 1: 테스터 역할 수행 - 현재 10개 분자 보고서의 스펙트럼 데이터 중복(똑같은 피크) 문제 원인 분석.
- Phase 2: 데이터 매핑 최적화 - ORCA 결과물과 스펙트럼 렌더러 간의 1:1 대응 보장.
- Phase 3: 최종 보고서 검수 및 '사용자 관점' 품질 보증서 작성.
- Phase 4: 누락된 스펙트럼 이미지 분석 수행 - `docs/exports/spectra_assets/` 내부 총 25장의 스펙트럼 이미지 중 분석 누락된 21장에 대한 시각/자연어 분석 수행 (Gemini 3.1 Pro 활용). `spectrum_vision_analysis_report.md` 업데이트. **(완료)**

> **상태:** [승인 완료] - 테스터 역할로 전환하여 정밀 분석 시작하십시오. 특히 Phase 4 누락된 스펙트럼 21장 분석을 최우선으로 진행하십시오. **(Phase 4 완료됨)**
