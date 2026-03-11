# 📋 Local Domain Plan: 05_rendering_engine
## 분광학 그래프 정밀 렌더링 엔진 구축 계획

### [긴급 수정] UV-Vis 듀얼 뷰 및 축 변환 구현
- [ ] **UV-Vis Dual-View 구현**:
  - `agents/09_data_export/spectrum_pdf_exporter.py`의 UV-Vis 그래프 생성 함수(`generate_spectrum_graph`)를 수정하여 두 개의 서브플롯(Subplot)을 생성.
  - 좌측: $\epsilon$ (Molar Absorptivity) vs Wavelength.
  - 우측: $\log \epsilon$ vs Wavelength.
- [ ] **축 단위 변환 모듈 개발**:
  - Absorbance 데이터를 $\epsilon$ 및 $\log \epsilon$으로 변환하는 수식 적용 ($A = \epsilon \cdot c \cdot l$).
  - 농도($c$)와 경로 길이($l$)에 대한 기본값 설정 (e.g., $10^{-4} M$, $1 cm$).

### 1. 세부 구현 목표
- [ ] 하위 분석 엔진으로부터 넘어오는 원시 데이터(Raw data)를 사용자 정의 형식에 맞춰 렌더링하는 범용 `SpectraPlotter` 모듈 개발.
- [ ] IR: 피크 거꾸로(Transmittance) 및 Absorbance 모드 지원.
- [ ] NMR: ppm 단위 적용 및 Multiplet 패턴 시각화 개선.
- [ ] UV-Vis: nm 단위 파장 기반 밴드 렌더링.

### 2. 단계별 마일스톤
- Phase 1: `SpectraPlotter` 기본 클래스 설계
- Phase 2: 분광법별(IR, NMR, Raman, UV) 특화 렌더링 로직 추가
- Phase 3: `docs/exports/spectra_assets/`의 사용자 가이드를 읽어 파라미터 자동 설정 기능 구현

> **상태:** [대기 중 / 승인 완료] - Manager 컨택 후 작업 시작
