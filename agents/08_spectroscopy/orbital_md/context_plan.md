# 📋 Agent 08d: 오비탈/MD — Context Plan
## 최종 업데이트: 2026-02-28 22:36 / 중간관리자(08) 지시

### 1. 역할
- 분자 오비탈 + 분자동역학(MD) 모듈 리팩토링 담당
- 담당 파일: `popup_molorbital.py`, `popup_md.py`
- 상위: Agent 08 (분광학 중간관리자)

### 2. 현재 상태
- **두 파일 모두 `_source/` 원본과 100% 동일 — 수정 0%**
- 이슈 3건 할당 (S3, S5, S8) + BaseSpectrumPopup 적용

### 3. 작업 지시 (우선순위 순)

| # | 우선순위 | 이슈 | 파일 | 작업 내용 |
|---|---------|------|------|----------|
| 1 | 🟡 | S3 | 두 파일 모두 | `from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas` → `from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas` |
| 2 | 🟡 | S8 | `popup_molorbital.py` | `plt.colorbar(contour, ax=self.ax, label=...)` → `self.figure.colorbar(contour, ax=self.ax, label=...)` (2곳: `plot_charge_distribution()`, `plot_molecular_potential()`). pyplot 전역 상태 의존 제거 |
| 3 | 🟡 | S5 | 두 파일 모두 | `print()` → `import logging; logger = logging.getLogger(__name__); logger.info/debug()` 교체 |
| 4 | 🟢 | 리팩토링 | 두 파일 | `MolecularOrbitalPopup(QDialog)` → `MolecularOrbitalPopup(BaseSpectrumPopup)`, `MDPopup(QDialog)` → `MDPopup(BaseSpectrumPopup)` 상속 적용. `_parse_data()`, `_setup_ui()`, `get_spectrum_data_for_pdf()` 구현 |

### 4. 공통 규칙 (MANDATORY)
- 절대 경로 금지 → `__file__` 기반 상대 경로 필수
- Python: `py` 명령어 사용
- 자가 검증: 
  - `py -c "import ast; ast.parse(open('popup_molorbital.py', encoding='utf-8').read())"`
  - `py -c "import ast; ast.parse(open('popup_md.py', encoding='utf-8').read())"`
- 원본 `_source/` 절대 수정 금지

### 5. 마일스톤
- Phase 1: 코드 분석 (중간관리자 완료)
- Phase 2: S3(backend) + S8(plt.colorbar) 수정
- Phase 3: S5(logging) 수정
- Phase 4: BaseSpectrumPopup 적용
- Phase 5: 자가 검증 → 중간관리자에게 보고

### 6. 참고: MDPopup의 BaseSpectrumPopup 적용 시 주의
- MDPopup은 QTimer 기반 애니메이션(궤적 재생)을 포함하여 다른 popup과 구조가 다름
- `_parse_data()`: MDTrajectoryParser 연동
- `_setup_ui()`: 재생 컨트롤(Play/Pause/Slider) 포함
- `get_spectrum_data_for_pdf()`: 에너지 진화 그래프 + 수렴 그래프를 이미지로 반환

> **상태:** 🟢 **작업 시작** — 중간관리자 승인 완료 (2026-02-28 23:08)
> 
> ### 🆕 base_spectrum.py 생성 완료
> - 위치: `agents/08_spectroscopy/base_spectrum.py`
> - `BaseSpectrumPopup(QDialog, ABC)` — 공통 추상 클래스
> - 필수 구현: `_parse_data()`, `_setup_ui()`, `get_spectrum_data_for_pdf()`
> - Phase 7 API: `get_embeddable_widget()`, `get_spectrum_summary()`
> - **conda 환경 사용:** `C:\ProgramData\anaconda3\Scripts\conda.exe run -n chemgrid python <script>`
> - **패키지 설치 완료:** PyQt6, matplotlib, numpy 모두 가용
> 
> ### 작업 순서
> 1. S3 (backend_qtagg) → S8 (plt.colorbar → fig.colorbar) 먼저 수정
> 2. S5 (print→logging) 수정
> 3. BaseSpectrumPopup 상속 적용 (MolecularOrbitalPopup + MDPopup 둘 다)
> 4. 자가 검증 후 중간관리자에게 보고
