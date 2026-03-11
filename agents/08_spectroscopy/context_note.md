# 📋 Local Domain Note: Task Transfer & Error Analysis
## 10_testing_build -> 08_spectroscopy 역할 인계 및 분석 결과

### 1. 전역 시스템 오류 분석 (Master Context)
- **현상**: 10개 분자 보고서(`docs/exports/reports_20260301_061803`)의 스펙트럼 피크가 모두 동일함.
- **원인 추정**: 
  - `agents/09/spectrum_pdf_exporter.py`가 개별 ORCA 결과 폴더를 참조하지 않고, 고정된 테스트 더미 데이터를 반복 출력 중.
  - `agents/03/Theoretical_Structures_All.pdf` 내 이미지 누락은 렌더링 버퍼 쓰기 실패로 판단됨.

### 2. '사용자 관점 피드백' 가이드라인 (에이전트 08 전용)
- **축 형식**:
  - IR: Wavenumber (x) vs Transmittance/Absorbance (y). Peak가 거꾸로(아래쪽) 내려오는 형태가 표준.
  - Raman: Raman Shift (x) vs Relative Raman Intensity (y). 
  - NMR: δ ppm (x). 
  - UV-Vis: Wavelength nm (x) vs Absorbance (y).
- **인계된 백데이터 위치**:
  - 오류 로그: `docs/reports/user_testing_report_2026-03-01.md`
  - 검증 결과: `_verification_results.json`
  - 산출물: `docs/exports/reports_20260301_061803/`

### 3. 최종 명령 (To 08_spectroscopy)
- 당신은 이제 분광학 중간관리자이자 **최종 UX 테스터**입니다.
- `docs/exports/spectra_assets/`에 사용자가 업로드할 레퍼런스 이미지와 텍스트를 최우선으로 분석하여 05(렌더링), 09(익스포트) 에이전트에게 구현 사양을 하달하십시오.
- 모든 스펙트럼의 x축, y축 라벨링이 전공 수준에 맞게 정확히 표시되는지 검증하십시오.
