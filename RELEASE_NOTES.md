# ChemGrid v1.0.0 릴리즈 노트

배포일: 2026-05-18  
빌드 식별자: v1.0.0-deploy-final  
이전 릴리즈: v1.0.0-lite-rc1 (2026-04-28)

---

## 포함 기능 (v1.0 완성)

### 분자 그리기 및 렌더링
- 원자/결합 캔버스 그리기 (Lewis 구조, 이론적 구조 레이어)
- ESP 전자구름 시각화 (Theory 모드에서만 활성)
- 방향족 오쏘/파라/메타 지향성 구별 렌더링

### 분광 분석 (자체 엔진 기반)
- IR 스펙트럼 예측
- ¹H / ¹³C NMR 예측
- UV-Vis 흡수 스펙트럼
- 라만 스펙트럼

### 3D 분자 뷰어 + 도킹
- Ball-and-stick 3D 뷰어
- 35종 수용체 경험적 도킹 스코어링 (Vina 근사)
- 진동 모드 시각화 (자체 엔진)

### 반응 분석 및 합성
- 반응 메커니즘 팝업 (교과서 스타일)
- 유기 합성 경로 (역합성 분석)
- 반응 애니메이션

### 약물 설계
- ADMET 예측
- Lead Optimizer
- Drug Screening
- AlphaFold 기반 단백질 뷰어

### 고분자 분석 (popup_polymer.py)
- 중합 유형별 PDI/Mn/Mw 분포 그래프 (Schulz-Flory)
- AI 기반 구조 분석

### DryLab 보고서
- PDF 출력 (IR/NMR/UV-Vis/Raman/EI-MS 포함 — 보고서 내부 생성)
- 합성 실험 설계서 양식

---

## v1.0 제한 기능 (비활성화)

> 아래 기능은 학술 검증 미완 또는 구현 미완성으로 v1.0에서 비활성화됩니다.  
> 환경변수 `CHEMGRID_ENABLE_<NAME>=1`로 개발자 오버라이드 가능.

| 기능 | 플래그 | 비활성화 사유 | 예정 버전 |
|------|--------|-------------|---------|
| EI-MS 독립 팝업 | `SPECTRUM_EI_MS_STANDALONE` | Cascade #10 Block4 미완 (α-cleavage 헤테로원자 우선순위 미구현). DryLab PDF 내 EI-MS는 정상 작동. | v1.1 |
| 분자 안정성 분석 | `STABILITY_ANALYSIS` | Cascade #10 Block7 미완 (popup_stability.py 미구현, BDE+Woodward-Fieser 미검증) | v1.1 |
| 분자동역학 전체 | `MOLECULAR_DYNAMICS_FULL` | popup_md.py 기본 구현만 완성, 전체 궤적 시뮬레이션 학술 검증 필요 | v1.2 |

**참고**: ORCA DFT 계산은 ORCA 6.1.1 별도 설치가 필요합니다.  
학술용 무료 다운로드: https://orcaforum.kofo.mpg.de/

---

## API 키 설정 (.env)

`.env.example`을 참조하여 `.env` 파일을 생성하세요.  
AI 기능(분자 이름 검색, Lead Optimizer 등)에 GROQ_API_KEY 또는 GEMINI_API_KEY 중 하나가 필요합니다.

```
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
```

API 키 없이도 기본 그리기 + 분광 분석 + 도킹은 동작합니다.

---

## 설치 방법

### 1-click 설치 (PowerShell)
```powershell
irm https://github.com/chulsuarmor/chemgrid/releases/latest/download/install.ps1 | iex
```

### 수동 설치
1. `ChemGrid.exe` 다운로드
2. 같은 폴더에 `.env.example` → `.env`로 복사 후 API 키 입력
3. `ChemGrid.exe` 실행

---

## 버그 리포트

https://github.com/chulsuarmor/chemgrid/issues

---

## 변경 이력 (v1.0.0-lite-rc1 → v1.0.0-deploy-final)

- `src/app/feature_flags.py` 신설 — v1.0 disable matrix 명시화 (M685 기반)
- `.env.example` API 키 목록 검증 완료 (소스코드 하드코딩 0건 확인)
- RELEASE_NOTES.md 신설 — 제한 기능 리스트 공개
