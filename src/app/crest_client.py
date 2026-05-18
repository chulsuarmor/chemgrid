# crest_client.py — CREST conformer search client (Worker M646_W_CREST)
"""
ChemGrid CREST conformer search 클라이언트.

CREST (Conformer-Rotamer Ensemble Sampling Tool) 통합 — 학술 연구실급 정합성.

학술 인용 (Rule NN):
- Pracht P, Bohle F, Grimme S (2020). "Automated exploration of the low-energy
  chemical space with fast quantum chemical methods". Phys. Chem. Chem. Phys.
  22:7169-7192. DOI: 10.1039/C9CP06869D.
- Grimme S (2019). "Exploration of Chemical Compound, Conformer, and Reaction
  Space with Meta-Dynamics Simulations Based on Tight-Binding Quantum
  Chemical Calculations". J. Chem. Theory Comput. 15(5):2847-2862.

CREST는 GFN-xTB 메타다이내믹스 기반의 conformer-rotamer 탐색 도구로,
xtb 의존성을 가집니다. xtb는 별도 binary로 설치되어야 합니다 (M646_BINS).

운영 모드:
- Windows: WSL Ubuntu에서 Linux CREST + xtb 실행 (binary 다운로드 완료)
- Linux/Mac: native binary 직접 실행
- SIMULATION_MODE: CREST 미설치 시 RDKit ETKDG fallback 안내

Rule 매핑:
- I: 매직넘버 [MAGIC] 주석, API 키 .env 전용 (해당 없음)
- L: SMILES MolFromSmiles + None 가드
- M: silent failure 차단 — logger.warning 의무
- N: subprocess 출력 isinstance(str) 가드, 응답 dict 타입 체크
- NN: 학술 인용 코드 + UI 툴팁
- GG: SIMULATION_MODE 노랑 배너 워터마크 안내
- JJ: subprocess STARTUPINFO + CREATE_NO_WINDOW (cmd 노출 차단)
"""

from __future__ import annotations

import os
import sys
import shutil
import logging
import subprocess
import tempfile
import platform
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Logger
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# CREST + xtb path detection (M646_BINS 패턴 4단계)
# ─────────────────────────────────────────────────────────────────

# [MAGIC] ChemGrid 표준 binary 경로
_CHEMGRID_CREST_LINUX_FALLBACK = r"C:/chemgrid/bin/crest/crest/crest"
_CHEMGRID_XTB_LINUX_FALLBACK = r"C:/chemgrid/bin/xtb/xtb-dist/bin/xtb"
_CHEMGRID_XTB_WINDOWS_FALLBACK = r"C:/chemgrid/bin/xtb/xtb-6.7.1/bin/xtb.exe"

# [MAGIC: 600] CREST 기본 timeout (초). 작은 분자 ~30s, 큰 분자 ~10min.
_CREST_TIMEOUT_DEFAULT = 600

# [MAGIC: 50] 최대 conformer 수 표시 한도 (UI rendering 부담 방지)
_MAX_CONFORMERS_DISPLAY = 50


def _is_windows() -> bool:
    """현재 OS가 Windows인지 확인."""
    return platform.system().lower() == "windows"


def _detect_wsl_distro() -> Optional[str]:
    """Windows 환경에서 WSL distro 감지 (Ubuntu 우선).

    Returns:
        distro 이름 (예: "Ubuntu-24.04") 또는 None.
    """
    if not _is_windows():
        return None
    try:
        # JJ: STARTUPINFO + CREATE_NO_WINDOW (cmd 노출 차단)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        # wsl --list --verbose 출력은 UTF-16 LE (BOM 없음). bytes로 받아 직접 디코드.
        result = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True,
            startupinfo=si,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        if result.returncode != 0:
            logger.debug("[CREST] WSL --list 실패 returncode=%d", result.returncode)
            return None
        # UTF-16 LE BOM 없음 → utf-16-le 직접 디코드
        raw_bytes = result.stdout or b""
        try:
            text = raw_bytes.decode("utf-16-le", errors="replace")
        except Exception:
            text = raw_bytes.decode("utf-8", errors="replace")
        # NUL 문자 제거
        text = text.replace("\x00", "")
        lines = text.splitlines()
        # 우선순위: Ubuntu-24.04 > Ubuntu-22.04 > Ubuntu > 첫 번째
        candidates: List[str] = []
        for line in lines:
            line = line.strip().lstrip("*").strip()
            if not line or line.startswith("NAME"):
                continue
            # Format: "Ubuntu-24.04    Stopped    2"
            parts = line.split()
            if parts:
                name = parts[0]
                if name and name != "NAME":
                    candidates.append(name)
        # Ubuntu 우선
        for pref in ("Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu-20.04", "Ubuntu"):
            if pref in candidates:
                return pref
        if candidates:
            return candidates[0]
        return None
    except Exception as e:  # Rule M: silent fail 금지
        logger.warning("[CREST] WSL distro 감지 실패: %s", e)
        return None


def _windows_to_wsl_path(win_path: str) -> str:
    """Windows path → WSL mount path 변환.

    예: "C:/chemgrid/bin/crest/crest/crest" → "/mnt/c/chemgrid/bin/crest/crest/crest"
    """
    if not isinstance(win_path, str) or not win_path:
        return win_path
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def detect_crest() -> Tuple[Optional[str], str]:
    """CREST executable 자동 탐지.

    Returns:
        (crest_path or None, mode):
        - mode "native": Linux/Mac native binary (.env CREST_PATH 또는 shutil.which)
        - mode "wsl": Windows + WSL Linux binary (절대경로 또는 .env)
        - mode "fallback": ChemGrid 절대경로 폴백 (Windows + WSL distro 발견)
        - mode "none": 미설치
    """
    # 1) .env CREST_PATH (환경변수 우선)
    env_crest = os.environ.get("CREST_PATH", "").strip()
    if env_crest and Path(env_crest).is_file():
        logger.debug("[CREST] env CREST_PATH 사용: %s", env_crest)
        if _is_windows():
            return (env_crest, "wsl")
        return (env_crest, "native")

    # 2) shutil.which (PATH 탐색)
    which_crest = shutil.which("crest")
    if which_crest:
        logger.debug("[CREST] shutil.which: %s", which_crest)
        return (which_crest, "native")

    # 3) ChemGrid 절대경로 폴백
    if Path(_CHEMGRID_CREST_LINUX_FALLBACK).is_file():
        logger.debug("[CREST] ChemGrid 절대경로 폴백: %s", _CHEMGRID_CREST_LINUX_FALLBACK)
        if _is_windows():
            # WSL distro 확인
            distro = _detect_wsl_distro()
            if distro:
                return (_CHEMGRID_CREST_LINUX_FALLBACK, "wsl")
            else:
                logger.warning(
                    "[CREST] CREST binary 발견되었으나 WSL distro 미설치. "
                    "Windows에서 CREST 실행을 위해서는 WSL Ubuntu 설치 필요. "
                    "https://learn.microsoft.com/ko-kr/windows/wsl/install"
                )
                return (None, "none")
        else:
            return (_CHEMGRID_CREST_LINUX_FALLBACK, "native")

    return (None, "none")


def detect_xtb_for_crest(mode: str) -> Optional[str]:
    """CREST에 필요한 xtb 탐지 (mode 일치 의무).

    Args:
        mode: "native" (Linux/Mac) 또는 "wsl" (Windows + WSL)

    Returns:
        xtb path or None.
    """
    # .env XTB_PATH 우선
    env_xtb = os.environ.get("XTB_PATH", "").strip()

    if mode == "wsl":
        # WSL에서 실행되므로 Linux xtb 필요
        if env_xtb and Path(env_xtb).is_file() and (
            "linux" in env_xtb.lower() or "xtb-dist" in env_xtb.lower()
        ):
            return env_xtb
        # ChemGrid Linux xtb 폴백
        if Path(_CHEMGRID_XTB_LINUX_FALLBACK).is_file():
            return _CHEMGRID_XTB_LINUX_FALLBACK
        logger.warning(
            "[CREST] WSL 모드에서 Linux xtb 미발견. CREST 실행 불가. "
            "필요: %s", _CHEMGRID_XTB_LINUX_FALLBACK
        )
        return None

    # native 모드 (Linux/Mac)
    if env_xtb and Path(env_xtb).is_file():
        return env_xtb
    which_xtb = shutil.which("xtb")
    if which_xtb:
        return which_xtb
    if not _is_windows() and Path(_CHEMGRID_XTB_LINUX_FALLBACK).is_file():
        return _CHEMGRID_XTB_LINUX_FALLBACK
    return None


# Module-level detection (한번 실행)
CREST_PATH, CREST_MODE = detect_crest()
CREST_AVAILABLE = CREST_PATH is not None
XTB_FOR_CREST = detect_xtb_for_crest(CREST_MODE) if CREST_AVAILABLE else None
SIMULATION_MODE = not (CREST_AVAILABLE and XTB_FOR_CREST is not None)


def get_status_message() -> str:
    """현재 CREST 상태 메시지 (UI 배너 표시용).

    Returns:
        한글 사용자 메시지. SIMULATION_MODE 시 노랑 배너 텍스트 포함 (Rule GG).
    """
    if SIMULATION_MODE:
        if not CREST_AVAILABLE:
            return ("[SIMULATION_MODE] CREST 미설치 — RDKit ETKDG 폴백 사용. "
                    "정밀 conformer 탐색을 위해 CREST 설치 필요. "
                    "출처: Pracht/Bohle/Grimme PCCP 2020;22:7169.")
        if not XTB_FOR_CREST:
            return ("[SIMULATION_MODE] xtb 미설치 — CREST 실행 불가 (xtb 의존). "
                    "C:/chemgrid/bin/xtb/xtb-dist/bin/xtb (Linux WSL용) 설치 필요.")
        return "[SIMULATION_MODE] CREST 또는 xtb 미설치"
    if CREST_MODE == "wsl":
        return f"[REAL_CREST_WSL] CREST {CREST_PATH} via WSL — 정밀 conformer 탐색 활성"
    return f"[REAL_CREST] CREST {CREST_PATH} — 정밀 conformer 탐색 활성"


# ─────────────────────────────────────────────────────────────────
# Core function: run_crest_conformer
# ─────────────────────────────────────────────────────────────────

def run_crest_conformer(
    smiles: str,
    timeout: int = _CREST_TIMEOUT_DEFAULT,
    quick: bool = True,
    workdir: Optional[str] = None,
) -> Dict[str, Any]:
    """SMILES → CREST conformer search → 결과 dict 반환.

    학술 인용 (Rule NN):
        Pracht P, Bohle F, Grimme S. PCCP 2020;22:7169.
        Grimme S. JCTC 2019;15:2847.

    Args:
        smiles: SMILES 문자열 (Rule L 가드 의무).
        timeout: subprocess timeout (sec). 기본 600s.
        quick: True면 --quick 모드 (빠른 탐색, 정확도 약간 낮음).
        workdir: 작업 디렉토리 (None이면 임시).

    Returns:
        dict {
            "status": "success" | "simulation" | "error",
            "smiles": 입력 SMILES,
            "n_conformers": int,
            "energies_kcal": List[float] (상대 에너지, kcal/mol),
            "lowest_energy_hartree": float (절대 에너지, Hartree),
            "conformers_xyz": List[str] (각 conformer XYZ 텍스트),
            "wall_time_sec": float,
            "raw_log_tail": str (로그 마지막 50줄),
            "method": "GFN2-xTB CREST (quick)" 또는 "ETKDG fallback",
            "citation": 학술 인용 문자열,
            "error": str (실패 시),
            "alternative": str (SIMULATION_MODE 시 사용자 안내),
        }
    """
    # Rule L: SMILES 파싱 방어
    if not isinstance(smiles, str) or not smiles.strip():
        return {
            "status": "error",
            "error": "[Rule L] SMILES가 빈 문자열 또는 비-string 타입",
            "smiles": str(smiles),
            "method": "none",
        }

    smiles = smiles.strip()

    # RDKit 파싱 검증
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError as e:
        return {
            "status": "error",
            "error": f"RDKit 미설치: {e}",
            "smiles": smiles,
            "method": "none",
        }

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {
            "status": "error",
            "error": f"[Rule L] MolFromSmiles 실패: {smiles}",
            "smiles": smiles,
            "method": "none",
        }

    mol_h = Chem.AddHs(mol)
    # 초기 좌표 (CREST 입력용)
    embed_result = AllChem.EmbedMolecule(mol_h, randomSeed=42)
    if embed_result == -1:
        return {
            "status": "error",
            "error": "[Rule L] AllChem.EmbedMolecule 실패 — 입체구조 생성 불가",
            "smiles": smiles,
            "method": "none",
        }
    AllChem.MMFFOptimizeMolecule(mol_h)

    # SIMULATION_MODE 분기 — RDKit ETKDG 폴백
    if SIMULATION_MODE:
        return _etkdg_fallback(mol_h, smiles)

    # CREST 실행 분기
    if CREST_PATH is None or XTB_FOR_CREST is None:
        return {
            "status": "simulation",
            "smiles": smiles,
            "n_conformers": 0,
            "energies_kcal": [],
            "lowest_energy_hartree": 0.0,
            "conformers_xyz": [],
            "wall_time_sec": 0.0,
            "raw_log_tail": "",
            "method": "ETKDG fallback (CREST 미가용)",
            "citation": "Pracht/Bohle/Grimme PCCP 2020;22:7169 (CREST 미실행)",
            "alternative": "CREST 설치 필요 또는 RDKit ETKDG 폴백 사용",
        }

    # 작업 디렉토리 — Windows + WSL 모드에서는 한글 사용자명 path 회피 (UTF-16 변환 실패 방지)
    cleanup_workdir = False
    if workdir is None:
        if _is_windows() and CREST_MODE == "wsl":
            # ChemGrid 표준 임시 dir (한글 path 회피)
            # [MAGIC] C:/chemgrid/tmp 경로 — 한글 사용자명 회피용 (M646_W_CREST)
            base_tmp = Path(r"C:/chemgrid/tmp/crest")
            base_tmp.mkdir(parents=True, exist_ok=True)
            import time as _t
            workdir = str(base_tmp / f"run_{int(_t.time()*1000)}")
        else:
            workdir = tempfile.mkdtemp(prefix="crest_")
        cleanup_workdir = True
    workdir_path = Path(workdir)
    workdir_path.mkdir(parents=True, exist_ok=True)

    # 입력 XYZ 작성
    xyz_path = workdir_path / "input.xyz"
    xyz_text = Chem.MolToXYZBlock(mol_h)
    if not isinstance(xyz_text, str) or not xyz_text:  # Rule N
        return {
            "status": "error",
            "error": "Chem.MolToXYZBlock 빈 출력",
            "smiles": smiles,
            "method": "none",
        }
    xyz_path.write_text(xyz_text, encoding="utf-8")

    # CREST 명령 구성
    args = _build_crest_command(xyz_path, workdir_path, quick=quick)
    if args is None:
        return {
            "status": "error",
            "error": "CREST 명령 구성 실패",
            "smiles": smiles,
            "method": "none",
        }

    # 실행
    import time
    start = time.time()
    try:
        # JJ: STARTUPINFO + CREATE_NO_WINDOW
        kwargs: Dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "cwd": str(workdir_path),
            "encoding": "utf-8",
            "errors": "replace",
        }
        if _is_windows():
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(args, **kwargs)
        wall_time = time.time() - start
        raw_log = (result.stdout or "") + "\n" + (result.stderr or "")
        raw_log_tail = "\n".join(raw_log.splitlines()[-50:])

        if result.returncode != 0:
            logger.warning("[CREST] returncode=%d log_tail=%s",
                           result.returncode, raw_log_tail[-500:])
            return {
                "status": "error",
                "error": f"CREST returncode={result.returncode}",
                "smiles": smiles,
                "raw_log_tail": raw_log_tail,
                "wall_time_sec": wall_time,
                "method": "CREST (failed)",
            }
    except subprocess.TimeoutExpired:
        wall_time = time.time() - start
        logger.warning("[CREST] timeout after %ds", timeout)
        return {
            "status": "error",
            "error": f"CREST timeout {timeout}s",
            "smiles": smiles,
            "wall_time_sec": wall_time,
            "method": "CREST (timeout)",
        }
    except Exception as e:  # Rule M
        wall_time = time.time() - start
        logger.warning("[CREST] subprocess 예외: %s: %s", type(e).__name__, e)
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "smiles": smiles,
            "wall_time_sec": wall_time,
            "method": "CREST (exception)",
        }

    # 결과 파싱
    parsed = _parse_crest_output(workdir_path, raw_log_tail, wall_time, smiles, quick)

    # 작업 디렉토리 cleanup (사용자 지정 시 보존)
    if cleanup_workdir:
        try:
            import shutil as _sh
            _sh.rmtree(workdir_path, ignore_errors=True)
        except Exception as e:
            logger.debug("[CREST] tmpdir cleanup 실패: %s", e)

    return parsed


def _build_crest_command(
    xyz_path: Path,
    workdir: Path,
    quick: bool = True,
) -> Optional[List[str]]:
    """CREST subprocess 명령 구성 (WSL 또는 native).

    Returns:
        argv list 또는 None.
    """
    if not CREST_AVAILABLE or XTB_FOR_CREST is None:
        return None

    if CREST_MODE == "wsl":
        # WSL 경유 — Windows path를 /mnt/c/... 변환
        # 한글 사용자명 PATH 오염 회피: bash -c 인라인 대신 .sh 스크립트 파일 작성 후 실행
        distro = _detect_wsl_distro() or "Ubuntu-24.04"
        crest_wsl = _windows_to_wsl_path(CREST_PATH or "")
        xtb_wsl = _windows_to_wsl_path(XTB_FOR_CREST or "")
        xtb_dir = str(Path(xtb_wsl).parent)
        xyz_wsl = _windows_to_wsl_path(str(xyz_path))
        workdir_wsl = _windows_to_wsl_path(str(workdir))
        # bash 스크립트 작성 (workdir 내부)
        script_text = (
            "#!/bin/bash\n"
            "# CREST runner (Worker M646_W_CREST) — bash 스크립트 분리로 한글 PATH 오염 회피\n"
            "set -e\n"
            f"export PATH={xtb_dir}:$PATH\n"
            f"cd {workdir_wsl}\n"
            f"{crest_wsl} {xyz_wsl} -gfn2"
            + (" --quick" if quick else "")
            + " --niceprint\n"
        )
        script_path = workdir / "run_crest.sh"
        try:
            script_path.write_text(script_text, encoding="utf-8", newline="\n")
        except Exception as e:  # Rule M
            logger.warning("[CREST] 스크립트 작성 실패: %s", e)
            return None
        script_wsl = _windows_to_wsl_path(str(script_path))
        return ["wsl", "-d", distro, "--", "bash", script_wsl]

    # native 모드
    args = [CREST_PATH, str(xyz_path), "-gfn2"]
    if quick:
        args.append("--quick")
    args.append("--niceprint")
    return args


def _parse_crest_output(
    workdir: Path,
    raw_log_tail: str,
    wall_time: float,
    smiles: str,
    quick: bool,
) -> Dict[str, Any]:
    """CREST 출력 파싱 — crest_conformers.xyz + crest.energies.

    Returns:
        결과 dict (run_crest_conformer 시그니처와 동일).
    """
    # crest_conformers.xyz: 각 conformer가 XYZ 블록으로 연결
    conformers_path = workdir / "crest_conformers.xyz"
    energies_path = workdir / "crest.energies"

    conformers_xyz: List[str] = []
    energies_kcal: List[float] = []
    lowest_hartree = 0.0

    # crest.energies 파싱 — 각 라인: "  index  rel_energy_kcal_per_mol"
    if energies_path.is_file():
        try:
            for line in energies_path.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        e = float(parts[1])
                        energies_kcal.append(e)
                    except ValueError:
                        continue
        except Exception as e:
            logger.warning("[CREST] crest.energies 파싱 실패: %s", e)

    # crest_conformers.xyz 파싱 — multi-frame XYZ
    if conformers_path.is_file():
        try:
            content = conformers_path.read_text(encoding="utf-8", errors="replace")
            # 각 conformer는: N\n header_with_energy\n atoms... 형식
            lines = content.splitlines()
            i = 0
            cnt = 0
            while i < len(lines) and cnt < _MAX_CONFORMERS_DISPLAY:
                if not lines[i].strip():
                    i += 1
                    continue
                try:
                    n = int(lines[i].strip())
                except (ValueError, IndexError):
                    break
                # n_atoms + 1 (header) + n_atoms (coordinates) = n+2 lines per frame
                end = i + n + 2
                if end > len(lines):
                    break
                frame = "\n".join(lines[i:end])
                conformers_xyz.append(frame)
                # header 라인에서 에너지 추출 (CREST 포맷: "       -15.87964068")
                if i + 1 < len(lines):
                    try:
                        header = lines[i + 1].strip().split()
                        if header:
                            lowest_candidate = float(header[0])
                            if cnt == 0 or lowest_candidate < lowest_hartree:
                                lowest_hartree = lowest_candidate
                    except (ValueError, IndexError) as e:
                        logger.warning("[CREST] conformer energy parse error: %s", e)
                i = end
                cnt += 1
        except Exception as e:
            logger.warning("[CREST] crest_conformers.xyz 파싱 실패: %s", e)

    n_conformers = len(conformers_xyz)
    if n_conformers == 0 and not energies_kcal:
        return {
            "status": "error",
            "error": "CREST 결과 파일 부재 (crest_conformers.xyz / crest.energies)",
            "smiles": smiles,
            "raw_log_tail": raw_log_tail,
            "wall_time_sec": wall_time,
            "method": "CREST (no output)",
        }

    method = "GFN2-xTB CREST"
    if quick:
        method += " (quick)"

    return {
        "status": "success",
        "smiles": smiles,
        "n_conformers": n_conformers,
        "energies_kcal": energies_kcal[:_MAX_CONFORMERS_DISPLAY],
        "lowest_energy_hartree": lowest_hartree,
        "conformers_xyz": conformers_xyz,
        "wall_time_sec": wall_time,
        "raw_log_tail": raw_log_tail,
        "method": method,
        "citation": "Pracht/Bohle/Grimme PCCP 2020;22:7169",
    }


def _etkdg_fallback(mol_h, smiles: str) -> Dict[str, Any]:
    """RDKit ETKDG 폴백 (CREST 미설치 시).

    학술 인용:
        Riniker S, Landrum GA (2015). "Better Informed Distance Geometry: Using
        What We Know To Improve Conformation Generation". J. Chem. Inf. Model.
        55(12):2562-2574.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        return {
            "status": "error",
            "error": "RDKit 미설치",
            "smiles": smiles,
            "method": "none",
        }

    # ETKDG로 conformer 생성 (10개)
    n_target = 10  # [MAGIC: 10] ETKDG fallback conformer 수
    confs = AllChem.EmbedMultipleConfs(mol_h, numConfs=n_target, randomSeed=42)
    if not confs:
        return {
            "status": "error",
            "error": "ETKDG conformer 생성 실패",
            "smiles": smiles,
            "method": "ETKDG fallback (failed)",
        }

    # MMFF 최적화 + 에너지
    energies_hartree: List[float] = []
    energies_kcal: List[float] = []
    conformers_xyz: List[str] = []

    for cid in confs:
        try:
            ff = AllChem.MMFFGetMoleculeForceField(
                mol_h,
                AllChem.MMFFGetMoleculeProperties(mol_h),
                confId=cid,
            )
            if ff is None:
                continue
            ff.Minimize()
            energy_kcal = ff.CalcEnergy()
            energies_kcal.append(energy_kcal)
            # XYZ block per conformer
            xyz_text = Chem.MolToXYZBlock(mol_h, confId=cid)
            if isinstance(xyz_text, str):
                conformers_xyz.append(xyz_text)
        except Exception as e:
            logger.debug("[CREST/ETKDG] conformer %d 처리 실패: %s", cid, e)
            continue

    # 상대 에너지 변환
    if energies_kcal:
        e_min = min(energies_kcal)
        rel_energies = [e - e_min for e in energies_kcal]
    else:
        rel_energies = []

    return {
        "status": "simulation",
        "smiles": smiles,
        "n_conformers": len(conformers_xyz),
        "energies_kcal": rel_energies,
        "lowest_energy_hartree": 0.0,  # MMFF는 Hartree 단위 아님
        "conformers_xyz": conformers_xyz,
        "wall_time_sec": 0.0,
        "raw_log_tail": "",
        "method": "ETKDG (RDKit fallback, MMFF94)",
        "citation": "Riniker/Landrum JCIM 2015;55:2562 (CREST 미설치 폴백)",
        "alternative": ("CREST 설치 시 GFN2-xTB 메타다이내믹스 정밀 탐색 가능. "
                        "현재 RDKit ETKDG + MMFF94로 폴백 (Pracht/Bohle/Grimme "
                        "PCCP 2020;22:7169 미실행)."),
    }


# ─────────────────────────────────────────────────────────────────
# Self-test (CLI)
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # cp949 OS 콘솔에서도 안전하게 출력 (Q rule, M601)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception as _enc_e:  # Rule M: silent fail 차단
        logger.warning("[CREST/CLI] stdout reconfigure 실패 (호환성 무시): %s", _enc_e)
    logging.basicConfig(level=logging.INFO)
    print("=== CREST self-test ===")
    print(f"Status: {get_status_message()}")
    print(f"CREST_PATH: {CREST_PATH}")
    print(f"CREST_MODE: {CREST_MODE}")
    print(f"CREST_AVAILABLE: {CREST_AVAILABLE}")
    print(f"XTB_FOR_CREST: {XTB_FOR_CREST}")
    print(f"SIMULATION_MODE: {SIMULATION_MODE}")
    print()
    test_smiles = "c1ccccc1"  # benzene
    print(f"=== Test conformer search: {test_smiles} ===")
    result = run_crest_conformer(test_smiles, quick=True, timeout=180)
    print(f"Status: {result.get('status')}")
    print(f"Method: {result.get('method')}")
    print(f"N conformers: {result.get('n_conformers')}")
    print(f"Wall time: {result.get('wall_time_sec', 0):.2f}s")
    if result.get("error"):
        print(f"Error: {result.get('error')}")
    print(f"Citation: {result.get('citation')}")
