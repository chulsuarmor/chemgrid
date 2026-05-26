# ChemGrid

화학 그리기 + 스펙트럼 분석 + AI 약물 설계 + DryLab 보고서 — 학생용 화학 분석 통합 플랫폼

---

## 한 줄 설치 (Windows PowerShell)

학생 PC에서 PowerShell을 열고 아래 명령어 1줄만 붙여넣기:

```powershell
irm https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.ps1 | iex
```

- Canonical public install boundary: pinned `v1.0.0-lite-rc1` `ChemGrid.exe`.
- Expected `ChemGrid.exe` SHA256: `981898c1b88e3d512aae820eb7be812c27b4dd7dc217a3bd59522ba37d8f5a22`.
- The installer supports `-NoLaunch` and `--dry-run` when run from a saved script; the one-line command above is the public student install command.
- 경고: 이 안내는 rc1 고정 `ChemGrid.exe` 설치 명령만 대상으로 합니다.
- `releases/latest/download/install.ps1`, `v1.0.0-lite-rc8` 경로, ZIP/latest 설치 흐름은 학생용 고정 EXE 설치 명령이 아닙니다.
- latest/rc8 경로는 별도 검증 전까지 위 rc1 고정 명령을 대체하지 마세요.

### WSL / Linux / macOS

현재 학생 배포 경로는 Windows onefile EXE입니다. WSL/Linux/macOS 설치 스크립트는 rc1 학생용 고정 경로로 검증되지 않았습니다.

---

## 수동 다운로드

| 파일 | 크기 | 설명 |
|------|------|------|
| [ChemGrid.exe](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid.exe) | 422 MB / 422,218,217 bytes | Canonical pinned Windows onefile EXE; SHA256 above |
| [ChemGrid_Lite.zip](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/ChemGrid_Lite.zip) | 305 MB | Archive only; not the canonical fixed EXE install command |
| [install.ps1](https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.ps1) | 2,931 bytes | PowerShell installer for the pinned rc1 EXE |

---

## 주요 기능

- **2D/3D 분자 구조 그리기** — 직관적 캔버스 + SMILES 입력
- **IR / UV-Vis / Mass 스펙트럼** — RDKit 기반 실시간 예측
- **ADMET 예측** — 약물 흡수/분포/대사/배설/독성
- **역합성 분석** — ASKCOS (MIT) 연동
- **단백질 구조 예측** — ColabFold / AlphaFold (인터넷 연결 시)
- **PDBe Mol* 3D 뷰어** — 로그인 없이 단백질 3D 가시화
- **DryLab 보고서** — 전국과학전람회 수준 실험 보고서 자동 생성
- **SIMULATION_MODE** — 서버 미연결 시 모의/휴리스틱 결과를 명시하는 경계 표시 모드

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

ORCA 서버는 선택 구성입니다. 이 README의 rc1 설치 안내는 고정 EXE 경로와 SHA를 문서화하며, SIMULATION_MODE의 전체 기능 준비 상태를 검증하지 않습니다.
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
