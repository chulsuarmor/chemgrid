# ChemGrid

화학 그리기 + 스펙트럼 분석 + AI 약물 설계 + DryLab 보고서 — 학생용 화학 분석 통합 플랫폼

---

## 한 줄 설치 (Windows PowerShell)

학생 PC에서 PowerShell을 열고 아래 명령어 1줄만 붙여넣기:

```powershell
iwr -useb https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.ps1 | iex
```

- 관리자 권한 불필요
- ChemGrid.exe 자동 다운로드 + 바탕화면 바로가기 생성
- 설치 완료 후 ChemGrid 자동 실행

### WSL / Linux / macOS

```bash
curl -sL https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.sh | bash
```

---

## 수동 다운로드

| 파일 | 크기 | 설명 |
|------|------|------|
| [ChemGrid.exe](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid.exe) | 1.1 GB | Windows 단일 실행 파일 (설치 불필요) |
| [ChemGrid_Lite.zip](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid_Lite.zip) | 305 MB | ZIP 패키지 |
| [install.ps1](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.ps1) | 15 KB | PowerShell 설치 스크립트 |
| [install.sh](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.sh) | - | Bash 설치 스크립트 (WSL/Linux) |

---

## 주요 기능

- **2D/3D 분자 구조 그리기** — 직관적 캔버스 + SMILES 입력
- **IR / UV-Vis / Mass 스펙트럼** — RDKit 기반 실시간 예측
- **ADMET 예측** — 약물 흡수/분포/대사/배설/독성
- **역합성 분석** — ASKCOS (MIT) 연동
- **단백질 구조 예측** — ColabFold / AlphaFold (인터넷 연결 시)
- **PDBe Mol* 3D 뷰어** — 로그인 없이 단백질 3D 가시화
- **DryLab 보고서** — 전국과학전람회 수준 실험 보고서 자동 생성
- **SIMULATION_MODE** — 서버 없이도 핵심 기능 모두 작동

---

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Windows 10 22H2 | Windows 11 |
| RAM | 8 GB | 16 GB |
| 디스크 | 3 GB 여유 | 5 GB |
| GPU | 불필요 | 불필요 |

---

## 교사용: 인수인계 안내

> 자세한 내용: [housing/docs/STUDENT_DEPLOY.md](housing/docs/STUDENT_DEPLOY.md)

### 학생 PC 설치 (LG Gram 등)

1. PowerShell에서 위 한 줄 명령어 실행
2. 설치 완료 후 바탕화면 ChemGrid 아이콘 더블클릭

### 교사 PC: ORCA 서버 (DFT 계산 — 선택)

ORCA 서버 없이도 ChemGrid은 SIMULATION_MODE로 완전 작동합니다.
DFT 정밀 계산이 필요한 경우에만 교사 PC에 서버를 설치하세요.

```bash
pip install fastapi uvicorn
python housing/services/orca_api_server.py
# -> http://교사PC_IP:8765 에서 시작
```

학생 `.env` 파일에 한 줄 추가:
```
ORCA_SERVER_URL=http://192.168.1.100:8765
```

---

## 개발자용 실행

```bash
conda activate chemgrid
python src/app/draw.py
```

빌드:
```
tools/build_chemdraw.bat
```

---

## 학술 인용

ORCA DFT 결과 사용 시:
```
Neese, F. et al. (2020). J. Chem. Phys. 152(22): 224108. DOI: 10.1063/5.0004608
```

PDBe Mol* 3D 뷰어:
```
Sehnal, D. et al. (2021). Nucleic Acids Res. 49(W1): W431-W437. DOI: 10.1093/nar/gkab314
```

---

*ChemGrid v1.0.0-lite-rc1 — 2026-05-17*
*Worker D-M1091-W145 / CT Order D-M1091 / M1255*
