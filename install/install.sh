#!/usr/bin/env bash
# ChemGrid Installer — WSL/Linux/macOS 1줄 설치
# Worker D-M1091-W145, 2026-05-17 / M1255
#
# 사용법:
#   curl -sL https://github.com/chulsuarmor/chemgrid/releases/download/v1.0.0-lite-rc1/install.sh | bash
#
# 또는 로컬 실행:
#   bash install.sh
#
# Rule I : API 키 소스코드 포함 금지
# Rule M : silent failure 금지 — 모든 단계 echo + 에러 메시지
# Rule JJ: Windows cmd /c 노출 금지 (본 파일은 Bash 전용)

set -euo pipefail

# ----------------------------------------------------------------------------
# 설정 (매직넘버 주석 — Rule I)
# ----------------------------------------------------------------------------
REPO="chulsuarmor/chemgrid"
TAG="v1.0.0-lite-rc1"               # M1255: 배포 태그 고정
BASE_URL="https://github.com/${REPO}/releases/download/${TAG}"
MIN_EXE_MB=100                       # EXE 최소 크기 MB (rc1 onefile 검증용)
MIN_ZIP_MB=50                        # ZIP 최소 크기 MB (검증용)

# ----------------------------------------------------------------------------
# 색상 헬퍼
# ----------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; GRAY='\033[0;37m'; RESET='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${RESET} $*"; }
err()  { echo -e "  ${RED}[ERR]${RESET}  $*" >&2; }
step() { echo -e "\n${CYAN}==[${1}]==${RESET}"; }

echo ""
echo -e "${CYAN}==========================================${RESET}"
echo -e "${CYAN} ChemGrid 설치 프로그램 (WSL/Linux) v2${RESET}"
echo -e "${GRAY} ${TAG}${RESET}"
echo -e "${CYAN}==========================================${RESET}"
echo ""

# ----------------------------------------------------------------------------
# 1) 실행 환경 감지
# ----------------------------------------------------------------------------
step "환경 감지"

IS_WSL=0
IS_LINUX=0
IS_MACOS=0

if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=1
    ok "WSL (Windows Subsystem for Linux) 감지"
elif [[ "$(uname -s)" == "Darwin" ]]; then
    IS_MACOS=1
    ok "macOS 감지"
else
    IS_LINUX=1
    ok "Linux 감지"
fi

# curl 또는 wget 확인 (Rule M — 다운로드 도구 미존재 시 명확 오류)
if command -v curl &>/dev/null; then
    DOWNLOADER="curl"
    ok "다운로드 도구: curl"
elif command -v wget &>/dev/null; then
    DOWNLOADER="wget"
    ok "다운로드 도구: wget"
else
    err "curl 또는 wget 필요. 설치 후 재시도:"
    err "  Ubuntu/Debian: sudo apt install curl"
    err "  macOS: brew install curl"
    exit 1
fi

# ----------------------------------------------------------------------------
# 2) 설치 방식 선택
# ----------------------------------------------------------------------------
step "설치 방식"

# WSL + Windows: ChemGrid.exe를 Windows 경로에 직접 다운로드 (추천)
# Linux/macOS: ChemGrid_Lite.zip (Python 소스 기반 — conda 필요)
MODE="${CHEMGRID_INSTALL_MODE:-}"

if [[ -z "$MODE" ]]; then
    if [[ $IS_WSL -eq 1 ]]; then
        MODE="exe"
        ok "WSL 환경: EXE 직접 설치 (Windows 경로)"
    else
        MODE="source"
        warn "Linux/macOS: Python 소스 설치 (conda 필요)"
    fi
fi

# Windows EXE 설치 경로 (WSL)
WIN_INSTALL_DIR=""
if [[ "$MODE" == "exe" && $IS_WSL -eq 1 ]]; then
    WIN_APPDATA=$(powershell.exe -WindowStyle Hidden -NonInteractive -Command "[System.Environment]::GetFolderPath('LocalApplicationData')" 2>/dev/null | tr -d '\r')
    if [[ -n "$WIN_APPDATA" ]]; then
        WIN_INSTALL_DIR=$(wslpath "$WIN_APPDATA/ChemGrid" 2>/dev/null || true)
    fi
    if [[ -z "$WIN_INSTALL_DIR" ]]; then
        # 폴백: 기본 경로 추정
        WIN_INSTALL_DIR="/mnt/c/Users/${USER}/AppData/Local/ChemGrid"
    fi
    mkdir -p "$WIN_INSTALL_DIR"
    ok "설치 폴더: $WIN_INSTALL_DIR"
fi

# ----------------------------------------------------------------------------
# 3) 다운로드 함수
# ----------------------------------------------------------------------------
download_file() {
    local url="$1"
    local dest="$2"
    if [[ "$DOWNLOADER" == "curl" ]]; then
        curl -L --progress-bar --fail -o "$dest" "$url" || {
            err "다운로드 실패: $url"
            return 1
        }
    else
        wget --show-progress -q -O "$dest" "$url" || {
            err "다운로드 실패: $url"
            return 1
        }
    fi
}

# Rule N: 파일 크기 검증 함수 (MB)
check_size_mb() {
    local file="$1"
    local min_mb="$2"
    local label="$3"
    local size_bytes
    size_bytes=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo 0)
    local size_mb=$(( size_bytes / 1048576 ))  # 1MB = 1048576 bytes
    if [[ $size_mb -lt $min_mb ]]; then
        err "${label} 크기 비정상 (${size_mb}MB < ${min_mb}MB). 파일 손상 의심."
        rm -f "$file"
        return 1
    fi
    ok "${label} 다운로드 완료 (${size_mb} MB)"
}

# ----------------------------------------------------------------------------
# 4-A) EXE 설치 (WSL 전용)
# ----------------------------------------------------------------------------
if [[ "$MODE" == "exe" ]]; then
    step "ChemGrid.exe 다운로드"
    EXE_URL="${BASE_URL}/ChemGrid.exe"
    EXE_DEST="${WIN_INSTALL_DIR}/ChemGrid.exe"

    warn "ChemGrid.exe는 약 128.6 MB입니다. 네트워크에 따라 시간이 걸릴 수 있습니다."
    download_file "$EXE_URL" "$EXE_DEST"
    check_size_mb "$EXE_DEST" "$MIN_EXE_MB" "ChemGrid.exe"

    # Rule N: MZ 헤더 검증 (Windows PE)
    if command -v xxd &>/dev/null; then
        magic=$(xxd -l 2 "$EXE_DEST" 2>/dev/null | awk '{print $2}')
        if [[ "$magic" != "4d5a" ]]; then
            err "EXE 시그니처 불일치 (MZ). 파일 손상 의심."
            rm -f "$EXE_DEST"
            exit 1
        fi
        ok "EXE 시그니처 확인 (MZ)"
    fi

    # .env 처리 (Rule I — API 키 절대 미포함)
    step ".env 설정"
    ENV_EXAMPLE="${WIN_INSTALL_DIR}/.env.example"
    ENV_FILE="${WIN_INSTALL_DIR}/.env"
    if [[ -f "$ENV_EXAMPLE" ]] && [[ ! -f "$ENV_FILE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok ".env 생성 (SIMULATION_MODE로 시작)"
        warn "AI 기능 활성화: $ENV_FILE 편집 → GEMINI_API_KEY 입력"
    else
        warn ".env.example 미발견 — ChemGrid은 SIMULATION_MODE로 시작"
    fi

    echo ""
    echo -e "${GREEN}==========================================${RESET}"
    echo -e "${GREEN} ChemGrid 설치 완료! (WSL EXE 모드)${RESET}"
    echo -e "${GREEN}==========================================${RESET}"
    echo ""
    echo "  실행 파일: $(wslpath -w "$EXE_DEST" 2>/dev/null || echo "$EXE_DEST")"
    echo ""
    echo "실행 방법:"
    echo "  WSL에서: explorer.exe \"$(wslpath -w "$EXE_DEST" 2>/dev/null)\""
    echo "  또는 Windows 파일 탐색기에서 더블클릭"
    echo ""

# ----------------------------------------------------------------------------
# 4-B) Python 소스 설치 (Linux/macOS)
# ----------------------------------------------------------------------------
elif [[ "$MODE" == "source" ]]; then
    step "Python 환경 확인"

    # conda 확인
    if ! command -v conda &>/dev/null; then
        warn "conda 미발견. Miniconda 설치 후 재시도:"
        warn "  https://docs.conda.io/en/latest/miniconda.html"
        warn ""
        warn "또는 자동 설치:"
        if [[ $IS_MACOS -eq 1 ]]; then
            warn "  curl -sL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh | bash"
        else
            warn "  curl -sL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh | bash"
        fi
        exit 1
    fi
    ok "conda 발견: $(conda --version)"

    step "ChemGrid ZIP 다운로드"
    ZIP_URL="${BASE_URL}/ChemGrid_Lite.zip"
    ZIP_TMP="/tmp/chemgrid_${TAG}.zip"
    download_file "$ZIP_URL" "$ZIP_TMP"
    check_size_mb "$ZIP_TMP" "$MIN_ZIP_MB" "ChemGrid_Lite.zip"

    # Rule N: PK 헤더 검증
    if command -v xxd &>/dev/null; then
        magic=$(xxd -l 2 "$ZIP_TMP" 2>/dev/null | awk '{print $2}')
        if [[ "$magic" != "504b" ]]; then
            err "ZIP 시그니처 불일치 (PK). 파일 손상 의심."
            rm -f "$ZIP_TMP"
            exit 1
        fi
        ok "ZIP 시그니처 확인 (PK)"
    fi

    step "압축 해제"
    INSTALL_DIR="${HOME}/ChemGrid"
    mkdir -p "$INSTALL_DIR"
    unzip -q "$ZIP_TMP" -d "$INSTALL_DIR"
    rm -f "$ZIP_TMP"
    ok "압축 해제: $INSTALL_DIR"

    step "conda 환경 생성 (chemgrid)"
    if conda env list | grep -q "^chemgrid "; then
        warn "chemgrid 환경 이미 존재 — 건너뜀"
    else
        conda create -n chemgrid python=3.12 -y
        ok "conda env chemgrid 생성"
    fi

    step "의존성 설치"
    # conda-forge RDKit
    conda run -n chemgrid conda install -c conda-forge rdkit=2025.09.5 -y 2>&1 | tail -5
    ok "RDKit 설치"

    conda run -n chemgrid pip install PyQt6==6.10.2 requests python-dotenv matplotlib reportlab 2>&1 | tail -5
    ok "PyQt6 + 필수 패키지 설치"

    # .env 처리 (Rule I)
    step ".env 설정"
    ENV_EXAMPLE="$INSTALL_DIR/.env.example"
    ENV_FILE="$INSTALL_DIR/.env"
    if [[ -f "$ENV_EXAMPLE" ]] && [[ ! -f "$ENV_FILE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok ".env 생성 (API 키 없음 — SIMULATION_MODE)"
        warn "AI 기능: $ENV_FILE 편집 → GEMINI_API_KEY 또는 GROQ_API_KEY 입력"
    fi

    echo ""
    echo -e "${GREEN}==========================================${RESET}"
    echo -e "${GREEN} ChemGrid 설치 완료! (Python 소스 모드)${RESET}"
    echo -e "${GREEN}==========================================${RESET}"
    echo ""
    echo "실행 방법:"
    echo "  conda activate chemgrid"
    echo "  python $INSTALL_DIR/src/app/draw.py"
    echo ""
    echo "AI 기능 활성화:"
    echo "  $ENV_FILE 편집 → GEMINI_API_KEY 또는 GROQ_API_KEY 입력"
    echo "  Gemini 무료: https://aistudio.google.com/app/apikey"
    echo "  Groq   무료: https://console.groq.com/keys"
    echo ""

else
    err "알 수 없는 MODE: $MODE (exe 또는 source 지원)"
    exit 1
fi

echo -e "${GRAY}문제 발생 시: https://github.com/${REPO}/issues${RESET}"
echo ""
