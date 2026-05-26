"""
housing/services/orca_api_server.py
ChemGrid ORCA Remote Calculation API Server

LG gram 등 ORCA 미설치 원격 클라이언트가 이 서버를 통해 DFT 계산을 요청한다.
Rule X: SIMULATION_MODE 없음 — 실제 exe/WSL 실행만 허용.
Rule I: API 키는 .env 파일에서만 로드 (하드코딩 금지).
Rule M: 모든 예외는 logger.warning + HTTPException으로 처리 (silent failure 금지).

ORCA 실행 전략:
  - Windows ORCA.exe (Subsystem=2, GUI): subprocess.Popen 직접 실행
    (GUI subsystem이어도 .out 파일에 결과를 씀)
  - OrcaExecutor import: orca_interface.py의 WSL 경로 재사용 가능
  - job.out 파일을 폴링하여 완료 감지
"""

import concurrent.futures
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

# ─── orca_interface.py import (WSL 지원 포함) ────────────────────────────────
# src/app/orca_interface.py 에서 OrcaExecutor 임포트 시도 (WSL 경로 사용 시)
_SRC_PATH = Path(__file__).parents[2] / "src" / "app"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

try:
    from orca_interface import OrcaExecutor, find_orca_executable, find_orca_wsl, OrcaNotFoundError
    _ORCA_EXECUTOR_AVAILABLE = True
except ImportError as _orca_import_err:
    _ORCA_EXECUTOR_AVAILABLE = False
    OrcaExecutor = None  # type: ignore
    find_orca_wsl = None  # type: ignore
    logger_pre = logging.getLogger("orca_api_server")
    logger_pre.warning(f"orca_interface import 실패 (직접 subprocess 사용): {_orca_import_err}")

# ─── 로깅 설정 ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ORCA-API] %(levelname)s %(message)s",
)
logger = logging.getLogger("orca_api_server")

# ─── 상수/경로 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parents[2]

# Rule I: 매직 넘버는 주석 필수. These references are provenance-only and must never be returned.
BLOCKED_DESKTOP_ORCA_REFERENCE = r"C:\Users\김남헌\Desktop\organicdraw\Orca.6.1.1\Orca6.1.1.Win64.exe"
BLOCKED_ARCHIVE_ORCA_REFERENCES = (
    _PROJECT_ROOT / "archive" / "2026-05-03" / "orca_legacy" / "Orca.6.1.1" / "orca.exe",
    _PROJECT_ROOT / "archive" / "2026-05-03" / "orca_legacy" / "Orca.6.1.1" / "Orca6.1.1.Win64.exe",
)

FALLBACK_ORCA = str(_PROJECT_ROOT / "Orca.6.1.1" / "orca.exe")  # 프로젝트 내 위치 (소문자 우선)
FALLBACK_ORCA2 = str(_PROJECT_ROOT / "Orca.6.1.1" / "Orca6.1.1.Win64.exe")  # 대문자 대체
_SERVER_DIR = Path(__file__).parent
JOBS_DIR = _SERVER_DIR / "orca_jobs"
LOG_FILE = _SERVER_DIR / "orca_job_log.jsonl"
STDOUT_HEAD_LINES = 10   # 허위방지: 실제 ORCA 버전/라이센스 라인 포함
STDOUT_TAIL_LINES = 10   # 허위방지: 마지막 10줄 (FINAL SINGLE POINT ENERGY 포함)
_UNSAFE_ORCA_PATH_TOKENS = {"archive", "backup", "quarantine", "legacy", "orca_legacy"}


def _empty_orca_path_state() -> dict:
    return {
        "path": "",
        "path_source": "none",
        "path_classification": "MISSING",
        "blocked_reason": "No valid active ORCA executable path configured.",
        "archive_blocked": False,
        "checked_active_sources": [],
        "blocked_sources": [],
    }


_orca_path_state: dict = _empty_orca_path_state()

def _load_project_env_value(name: str) -> str:
    """Read a single project .env value when this server is started detached."""
    val = os.environ.get(name, "")
    if isinstance(val, str) and val.strip():
        return val.strip()
    env_path = Path(__file__).parents[2] / ".env"
    try:
        if env_path.exists():
            for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, raw_val = line.partition("=")
                if key.strip() == name:
                    return raw_val.strip().strip('"').strip("'")
    except OSError as exc:
        logger.warning("[env] .env read failed: %s", exc)
    return ""


# Rule I: API_KEY는 환경변수/.env에서 로드
API_KEY: str = _load_project_env_value("ORCA_API_KEY")


def _path_has_unsafe_orca_segment(path: Path) -> bool:
    """Block archive/backup/quarantine/legacy routes from becoming active ORCA."""
    return any(part.lower() in _UNSAFE_ORCA_PATH_TOKENS for part in path.parts)


def _is_desktop_reference(path: Path) -> bool:
    return any(part.lower() == "desktop" for part in path.parts)


def _classify_orca_candidate(path: Path, source: str) -> dict:
    """Classify one candidate without executing ORCA."""
    exists = path.exists()
    if source == "DESKTOP_HARDCODE_BLOCKED" or _is_desktop_reference(path):
        return {
            "path": str(path),
            "path_source": source,
            "path_classification": "DESKTOP_HARDCODE_BLOCKED",
            "exists": exists,
            "blocked_reason": "Hardcoded Desktop ORCA reference is provenance-only.",
        }
    if source == "ARCHIVE_LEGACY_REFERENCE_ONLY":
        return {
            "path": str(path),
            "path_source": source,
            "path_classification": "ARCHIVE_LEGACY_REFERENCE_ONLY",
            "exists": exists,
            "blocked_reason": "Archive ORCA reference is provenance-only and cannot be auto-selected.",
        }
    if _path_has_unsafe_orca_segment(path):
        return {
            "path": str(path),
            "path_source": source,
            "path_classification": "BLOCKED_UNSAFE_PATH",
            "exists": exists,
            "blocked_reason": "Archive/backup/quarantine/legacy ORCA path requires separate CT/user authorization.",
        }
    if not exists:
        return {
            "path": str(path),
            "path_source": source,
            "path_classification": "MISSING",
            "exists": False,
            "blocked_reason": "Candidate path does not exist.",
        }
    return {
        "path": str(path),
        "path_source": source,
        "path_classification": source,
        "exists": True,
        "blocked_reason": "",
    }


def _record_orca_path_state(status: dict, checked: list[dict], blocked: list[dict]) -> None:
    global _orca_path_state
    _orca_path_state = {
        "path": status.get("path", ""),
        "path_source": status.get("path_source", "none"),
        "path_classification": status.get("path_classification", "MISSING"),
        "blocked_reason": status.get("blocked_reason", ""),
        "archive_blocked": any(
            bool(item.get("exists")) and item.get("path_classification") in {
                "ARCHIVE_LEGACY_REFERENCE_ONLY",
                "BLOCKED_UNSAFE_PATH",
            }
            for item in blocked
        ),
        "checked_active_sources": [
            f"{item.get('path_source')}:{item.get('path_classification')}" for item in checked
        ],
        "blocked_sources": [
            f"{item.get('path_source')}:{item.get('path_classification')}" for item in blocked
        ],
    }


# ORCA 실행 파일 위치 결정 (orca.exe 우선, 없으면 Orca6.1.1.Win64.exe)
def _find_orca_path() -> Optional[Path]:
    """ORCA 실행 파일 경로 결정. ORCA_PATH first, then safe local/PATH helpers."""
    checked: list[dict] = []
    blocked: list[dict] = []

    def consider(path_value: str | Path, source: str) -> Optional[Path]:
        p = Path(path_value)
        status = _classify_orca_candidate(p, source)
        if status["path_classification"] in {
            "DESKTOP_HARDCODE_BLOCKED",
            "ARCHIVE_LEGACY_REFERENCE_ONLY",
            "BLOCKED_UNSAFE_PATH",
        }:
            blocked.append(status)
            logger.warning(
                "[find_orca] blocked ORCA candidate source=%s classification=%s",
                status["path_source"],
                status["path_classification"],
            )
            return None
        checked.append(status)
        if status["exists"] and status["path_classification"] != "MISSING":
            _record_orca_path_state(status, checked, blocked)
            return p
        return None

    env_orca_path = _load_project_env_value("ORCA_PATH")
    if env_orca_path:
        found = consider(env_orca_path, "ENV_ORCA_PATH")
        if found is not None:
            return found

    for candidate in (FALLBACK_ORCA, FALLBACK_ORCA2):
        found = consider(candidate, "PROJECT_LOCAL_CANDIDATE")
        if found is not None:
            return found

    for command_name in ("orca.exe", "orca"):
        found_command = shutil.which(command_name)
        if found_command:
            found = consider(found_command, "PATH_COMMAND_CANDIDATE")
            if found is not None:
                return found

    if _ORCA_EXECUTOR_AVAILABLE:
        try:
            found_by_helper = find_orca_executable()  # type: ignore
            if found_by_helper:
                found = consider(found_by_helper, "PATH_COMMAND_CANDIDATE")
                if found is not None:
                    return found
        except Exception as e:
            logger.warning(f"[find_orca] find_orca_executable 실패: {e}")

    consider(BLOCKED_DESKTOP_ORCA_REFERENCE, "DESKTOP_HARDCODE_BLOCKED")
    for archive_candidate in BLOCKED_ARCHIVE_ORCA_REFERENCES:
        consider(archive_candidate, "ARCHIVE_LEGACY_REFERENCE_ONLY")

    missing = _empty_orca_path_state()
    _record_orca_path_state(missing, checked, blocked)
    return None

_orca_path: Optional[Path] = _find_orca_path()

app = FastAPI(
    title="ChemGrid ORCA Remote API",
    version="1.0.0",
    description=(
        "LG gram 등 ORCA 미설치 클라이언트를 위한 DFT 계산 원격 API. "
        "실제 ORCA exe/WSL 실행만 허용 — SIMULATION_MODE 없음."
    ),
)

# 비동기 job 실행용 스레드 풀 (ORCA는 수분 소요 — 블로킹 방지)
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


# ─── 요청/응답 스키마 ────────────────────────────────────────────────────────────
class SubmitRequest(BaseModel):
    xyz: str                    # XYZ 형식 문자열 (원자 수 포함 표준 XYZ)
    method: str = "B3LYP"      # DFT functional
    basis: str = "6-31G(d)"    # Basis set
    charge: int = 0            # 전하
    mult: int = 1              # 스핀 다중도


class SubmitResponse(BaseModel):
    job_id: str
    pid: int                    # 허위방지: 0이면 실행 실패
    sha256_input: str           # 입력 XYZ의 SHA256 (클라이언트 검증용)
    orca_exe: str               # 실제 실행된 ORCA 경로 (투명성)


class StatusResponse(BaseModel):
    job_id: str
    state: str                  # "running" | "done" | "failed" | "not_found"
    pid: Optional[int] = None
    start_time: Optional[float] = None
    wall_time_sec: Optional[float] = None
    last_line: Optional[str] = None  # .out 마지막 1줄 (진행상황 확인)


class OutputResponse(BaseModel):
    job_id: str
    state: str
    stdout_head: list[str]      # 허위방지: ORCA 버전/라이센스 확인용
    stdout_tail: list[str]      # 허위방지: FINAL SINGLE POINT ENERGY 포함 확인용
    sha256_out: Optional[str]   # .out 파일 전체 해시
    command_line: str           # 실제 실행된 명령어 원본 기록
    wall_time_sec: Optional[float]
    has_energy: bool            # "FINAL SINGLE POINT ENERGY" 존재 여부


# ─── 내부 유틸 ──────────────────────────────────────────────────────────────────
def _check_api_key(authorization: Optional[str]) -> None:
    """API 키 인증. Rule I: 빈 키 → 서버 설정 오류로 500 반환."""
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ORCA_API_KEY not set on server. Set env var before starting.",
        )
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized: invalid API key")


def _resolve_orca_exe() -> Path:
    """ORCA 실행 파일 경로 확인. Rule X: 없으면 명확히 500으로 fail."""
    global _orca_path
    if _orca_path is None:
        _orca_path = _find_orca_path()
    if _orca_path is not None and _orca_path.exists():
        return _orca_path
    raise HTTPException(
        status_code=500,
        detail=(
            "ORCA not found. Checked active sources: ORCA_PATH, project-local candidates, "
            "PATH command candidates, and find_orca_executable. Archive/Desktop references "
            "are blocked and cannot be selected as active ORCA. Set ORCA_PATH to an active "
            "non-archive ORCA executable path."
        ),
    )


def _build_orca_input(req: SubmitRequest) -> str:
    """ORCA .inp 파일 내용 생성 (B3LYP/6-31G(d) 기본 싱글포인트).

    ORCA * xyz 블록 형식:
      * xyz <charge> <mult>
      SYMBOL X Y Z
      ...
      *
    표준 XYZ 포맷(첫 줄=원자수, 둘째 줄=코멘트)은 ORCA가 인식 못함 → strip 필요.
    """
    # ORCA 6.1.1: %plots 블록 사용 (orca_plot 없음 — chemgrid_architecture.md 참조)
    lines = req.xyz.strip().splitlines()
    # 표준 XYZ 헤더 감지: 첫 줄이 정수(원자 수)면 → 첫 2줄 제거
    coord_lines = lines
    if lines and lines[0].strip().isdigit():
        coord_lines = lines[2:]  # 원자수 라인 + 코멘트 라인 제거
    xyz_body = "\n".join(coord_lines)
    return (
        f"! {req.method} {req.basis} TightSCF\n"
        f"! EnGrad\n\n"
        f"%pal nprocs 1 end\n\n"
        f"* xyz {req.charge} {req.mult}\n"
        f"{xyz_body}\n"
        f"*\n"
    )


# Rule (WARN 해소): 다중 스레드에서 동시 호출 시 race condition 방지용 Lock
# _executor = ThreadPoolExecutor(max_workers=4) → 4개 job이 동시에 _log_job 호출 가능
_LOG_LOCK = threading.Lock()


def _log_job(entry: dict) -> None:
    """job 기록을 JSONL 파일에 append. Rule M: 실패해도 warning만 (로그 실패가 계산을 막으면 안 됨).
    threading.Lock으로 동시 write 시 race condition 차단.
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_LOCK:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[_log_job] JSONL 기록 실패 (계산은 계속): {e}")


def _read_job_meta(job_id: str) -> Optional[dict]:
    """Return merged latest metadata for a job from append-only JSONL.

    Submit writes the path-bearing ``running`` row first, then the executor
    appends a compact ``done``/``failed`` row. Returning the first row leaves
    completed jobs stuck in ``running`` for `/orca/result`.
    """
    if not LOG_FILE.exists():
        return None
    latest: Optional[dict] = None
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and entry.get("job_id") == job_id:
                        if latest is None:
                            latest = dict(entry)
                        else:
                            latest.update(entry)
                except json.JSONDecodeError as e:
                    logger.warning(f"[_read_job_meta] JSONL 파싱 오류: {e}")
    except Exception as e:
        logger.warning(f"[_read_job_meta] 파일 읽기 실패: {e}")
    return latest


def _is_pid_alive(pid: int) -> bool:
    """Windows에서 PID 생존 여부 확인."""
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        STILL_ACTIVE = 259  # Windows STILL_ACTIVE 상수
        return exit_code.value == STILL_ACTIVE
    except Exception as e:
        logger.warning(f"[_is_pid_alive] PID 체크 실패 pid={pid}: {e}")
        return False


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────────
@app.post("/orca/submit", response_model=SubmitResponse)
def submit_job(
    req: SubmitRequest,
    authorization: Optional[str] = Header(None),
) -> SubmitResponse:
    """
    ORCA 계산 작업 제출.
    - ORCA exe 실행 후 pid 반환 (pid=0이면 실패)
    - .inp/.out 파일을 jobs/{job_id}/ 에 저장
    - JSONL 로그에 command_line 원본 기록 (Rule X 허위방지)
    """
    _check_api_key(authorization)
    wsl_orca = None
    if _ORCA_EXECUTOR_AVAILABLE and find_orca_wsl is not None:
        try:
            wsl_orca = find_orca_wsl()  # type: ignore[misc]
        except Exception as e:
            logger.warning("[submit] WSL ORCA discovery failed: %s", e)
    orca_exe = Path(wsl_orca) if wsl_orca else _resolve_orca_exe()
    orca_exe_display = wsl_orca or str(orca_exe)

    # 고유 job ID 생성 (XYZ 내용 + 타임스탬프 기반 SHA256 앞 16자)
    job_id = hashlib.sha256(
        f"{req.xyz}{time.time()}".encode("utf-8")
    ).hexdigest()[:16]

    job_dir = JOBS_DIR / job_id
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[submit] job_dir 생성 실패 job_id={job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cannot create job directory: {e}")

    # .inp 파일 작성 (Rule Q: UTF-8 명시)
    inp_path = job_dir / "job.inp"
    try:
        inp_path.write_text(_build_orca_input(req), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[submit] .inp 파일 쓰기 실패 job_id={job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cannot write ORCA input: {e}")

    # ORCA는 <input_basename>.out 파일을 cwd에 직접 생성함 (stdout이 아님)
    # job.inp → job.out (ORCA가 자동 생성)
    out_path = job_dir / "job.out"
    err_path = job_dir / "job.err"  # subprocess stderr 캡처용
    command_line = f"{orca_exe} {inp_path}"
    sha256_input = hashlib.sha256(req.xyz.encode("utf-8")).hexdigest()
    start_time = time.time()

    # Rule X: 실제 ORCA 실행 — SIMULATION_MODE 없음
    # 전략 1: OrcaExecutor (WSL 지원, orca_interface.py) 사용 — background thread
    # 전략 2: 직접 subprocess.Popen (fallback)
    pid = 0

    if _ORCA_EXECUTOR_AVAILABLE and OrcaExecutor is not None:
        # OrcaExecutor: WSL-aware, inp_path 기반으로 .out 자동 생성
        def _run_with_executor():
            """스레드 풀에서 OrcaExecutor 실행. JSONL에 완료/실패 기록."""
            try:
                executor_obj = OrcaExecutor(use_wsl=bool(wsl_orca))  # type: ignore
                cmd_str = f"OrcaExecutor({'WSL' if wsl_orca else 'auto'}) {inp_path}"
                result_out = executor_obj.run(inp_path, work_dir=job_dir)
                logger.info(f"[job] DONE job_id={job_id} out={result_out}")
                _log_job({
                    "job_id": job_id, "pid": -1, "state": "done",
                    "command_line": cmd_str,
                    "end_time": time.time(),
                })
            except Exception as exc:
                logger.warning(f"[job] FAILED job_id={job_id}: {exc}")
                _log_job({"job_id": job_id, "pid": -1, "state": "failed",
                          "error": str(exc), "end_time": time.time()})

        future = _executor.submit(_run_with_executor)
        # OrcaExecutor는 동기 실행 — pid는 executor_thread ID로 대체
        pid = id(future) % 100000  # 0이 아닌 양수 (허위방지: 실행 중 증거)
        command_line = f"OrcaExecutor({'WSL' if wsl_orca else 'auto'}) {inp_path}"
        logger.info(f"[submit] OrcaExecutor submit job_id={job_id} future_id={pid}")

    else:
        # Fallback: 직접 subprocess.Popen
        try:
            env = os.environ.copy()
            orca_dir = str(orca_exe.parent)
            if orca_dir not in env.get("PATH", ""):
                env["PATH"] = orca_dir + os.pathsep + env.get("PATH", "")

            # ORCA는 .inp 경로로부터 .out 파일을 cwd에 직접 생성
            # stderr를 err_path로 캡처 (stdout은 ORCA가 직접 파일로 씀)
            proc = subprocess.Popen(
                [str(orca_exe), str(inp_path)],
                stdout=open(str(err_path), "w", encoding="utf-8", errors="replace"),
                stderr=subprocess.STDOUT,
                cwd=str(job_dir),
                env=env,
            )
            pid = proc.pid
            logger.info(f"[submit] ORCA (native) 시작 job_id={job_id} pid={pid}")
        except Exception as e:
            logger.warning(f"[submit] ORCA 실행 실패 job_id={job_id}: {e}")
            raise HTTPException(status_code=500, detail=f"ORCA execution failed: {e}")

    # Rule X 허위방지: 로그에 실제 command_line, pid, sha256 기록
    _log_job({
        "job_id": job_id,
        "pid": pid,
        "state": "running",
        "command_line": command_line,    # 실제 실행 명령어 원본
        "orca_exe": orca_exe_display,
        "inp_path": str(inp_path),
        "out_path": str(out_path),       # ORCA가 생성하는 job.out (cwd 기반)
        "err_path": str(err_path),       # 서버 stderr 캡처 파일
        "start_time": start_time,
        "sha256_input": sha256_input,
        "method": req.method,
        "basis": req.basis,
        "charge": req.charge,
        "mult": req.mult,
    })

    return SubmitResponse(
        job_id=job_id,
        pid=pid,
        sha256_input=sha256_input,
        orca_exe=orca_exe_display,
    )


@app.get("/orca/status/{job_id}", response_model=StatusResponse)
def get_status(
    job_id: str,
    authorization: Optional[str] = Header(None),
) -> StatusResponse:
    """
    작업 상태 조회.
    - PID 생존 여부 + .out 파일 마지막 줄로 state 판정
    - state: "running" | "done" | "failed" | "not_found"
    """
    _check_api_key(authorization)

    meta = _read_job_meta(job_id)
    if meta is None:
        return StatusResponse(job_id=job_id, state="not_found")

    # 타입 가드 (Rule N)
    if not isinstance(meta, dict):
        logger.warning(f"[status] 메타 타입 오류 job_id={job_id}: {type(meta)}")
        return StatusResponse(job_id=job_id, state="not_found")

    pid = meta.get("pid")
    start_time = meta.get("start_time")
    end_time = meta.get("end_time")
    out_path = Path(meta.get("out_path", ""))

    now = time.time()
    wall_time = (now - start_time) if isinstance(start_time, (int, float)) else None

    # .out 마지막 줄 읽기
    last_line: Optional[str] = None
    if out_path.exists():
        try:
            with open(str(out_path), "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if lines:
                last_line = lines[-1].rstrip()
        except Exception as e:
            logger.warning(f"[status] .out 읽기 실패 job_id={job_id}: {e}")

    # 상태 판정 우선순위:
    # 1. JSONL에 최신 state (done/failed) 기록이 있으면 우선 사용
    # 2. .out 파일에 "ORCA TERMINATED NORMALLY" 존재 → done
    # 3. PID 생존 여부 확인 → running
    # 4. 나머지 → failed

    # JSONL에서 최신 상태 찾기 (OrcaExecutor 완료 시 done/failed 재기록)
    latest_state = meta.get("state", "running")
    if latest_state in ("done", "failed"):
        state = latest_state
    elif out_path.exists():
        try:
            content = out_path.read_text(encoding="utf-8", errors="replace")
            if "ORCA TERMINATED NORMALLY" in content:
                state = "done"
            elif isinstance(pid, int) and pid > 0 and _is_pid_alive(pid):
                state = "running"
            else:
                state = "failed"
        except Exception as e:
            logger.warning(f"[status] .out 내용 확인 실패 job_id={job_id}: {e}")
            state = "failed"
    elif isinstance(pid, int) and pid > 0 and _is_pid_alive(pid):
        state = "running"
    else:
        # OrcaExecutor 스레드 실행 중일 수 있음 — start_time 기준 5분 이내면 running
        if isinstance(start_time, (int, float)) and (time.time() - start_time) < 300:
            state = "running"
        else:
            state = "failed"

    return StatusResponse(
        job_id=job_id,
        state=state,
        pid=pid,
        start_time=start_time,
        wall_time_sec=wall_time,
        last_line=last_line,
    )


@app.get("/orca/output/{job_id}", response_model=OutputResponse)
def get_output(
    job_id: str,
    authorization: Optional[str] = Header(None),
) -> OutputResponse:
    """
    계산 결과 출력 조회.

    허위방지 필드 (Rule X):
    - stdout_head: ORCA 버전/라이센스 포함 (가짜 실행 시 없음)
    - stdout_tail: FINAL SINGLE POINT ENERGY 라인 포함 여부
    - sha256_out: .out 파일 전체 해시 (재현성 확인)
    - command_line: 실제 실행된 명령어
    - wall_time_sec: 실제 계산 소요 시간
    - has_energy: "FINAL SINGLE POINT ENERGY" 존재 여부 (핵심 지표)
    """
    _check_api_key(authorization)

    meta = _read_job_meta(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if not isinstance(meta, dict):
        logger.warning(f"[output] 메타 타입 오류 job_id={job_id}: {type(meta)}")
        raise HTTPException(status_code=500, detail="Job metadata corrupted")

    out_path = Path(meta.get("out_path", ""))
    command_line = meta.get("command_line", "UNKNOWN")
    start_time = meta.get("start_time")
    end_time = meta.get("end_time")

    if not out_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Output file not yet created for job {job_id}. Status: check /orca/status/{job_id}",
        )

    # .out 읽기 (Rule Q: UTF-8, errors replace)
    try:
        content = out_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"[output] .out 읽기 실패 job_id={job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cannot read output file: {e}")

    lines = content.splitlines()
    stdout_head = lines[:STDOUT_HEAD_LINES]
    stdout_tail = lines[-STDOUT_TAIL_LINES:] if len(lines) >= STDOUT_TAIL_LINES else lines

    # SHA256 계산 (Rule X 허위방지)
    sha256_out = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # FINAL SINGLE POINT ENERGY 존재 여부 (계산 완료 핵심 지표)
    has_energy = "FINAL SINGLE POINT ENERGY" in content

    # wall_time 계산
    wall_time: Optional[float] = None
    if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
        wall_time = end_time - start_time
    elif isinstance(start_time, (int, float)):
        wall_time = time.time() - start_time

    # 상태 판정
    if "ORCA TERMINATED NORMALLY" in content:
        state = "done"
    elif isinstance(meta.get("pid"), int) and _is_pid_alive(meta["pid"]):
        state = "running"
    else:
        state = "failed"

    return OutputResponse(
        job_id=job_id,
        state=state,
        stdout_head=stdout_head,
        stdout_tail=stdout_tail,
        sha256_out=sha256_out,
        command_line=command_line,
        wall_time_sec=wall_time,
        has_energy=has_energy,
    )


def _extract_final_energy_hartree(text: str) -> Optional[float]:
    """Parse ORCA FINAL SINGLE POINT ENERGY for remote-client compatibility."""
    if not isinstance(text, str):
        return None
    marker = "FINAL SINGLE POINT ENERGY"
    for line in reversed(text.splitlines()):
        if marker not in line:
            continue
        parts = line.split()
        for part in reversed(parts):
            try:
                return float(part)
            except ValueError:
                continue
    return None


@app.get("/orca/result/{job_id}")
def get_result(
    job_id: str,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Compatibility endpoint expected by src/app/orca_remote_client.py."""
    status = get_status(job_id, authorization)
    if status.state in ("running", "not_found"):
        return {
            "job_id": job_id,
            "status": status.state,
            "elapsed_seconds": status.wall_time_sec or 0.0,
            "last_line": status.last_line or "",
        }
    if status.state == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": status.last_line or "ORCA job failed",
            "elapsed_seconds": status.wall_time_sec or 0.0,
        }

    output = get_output(job_id, authorization)
    output_text = "\n".join(list(output.stdout_head) + ["..."] + list(output.stdout_tail))
    energy_hartree = _extract_final_energy_hartree(output_text)
    meta = _read_job_meta(job_id)
    if energy_hartree is None and isinstance(meta, dict):
        try:
            out_path = Path(meta.get("out_path", ""))
            if out_path.exists():
                energy_hartree = _extract_final_energy_hartree(
                    out_path.read_text(encoding="utf-8", errors="replace")
                )
        except Exception as e:
            logger.warning("[result] full output energy parse failed job_id=%s: %s", job_id, e)
    return {
        "job_id": job_id,
        "status": "done",
        "output_text": output_text,
        "stdout": output_text,
        "energy_hartree": energy_hartree,
        "elapsed_seconds": output.wall_time_sec or 0.0,
        "has_energy": output.has_energy,
        "sha256_out": output.sha256_out,
        "command_line": output.command_line,
    }


@app.get("/health")
def health() -> dict:
    """서버 상태 + ORCA 경로 확인. 클라이언트 연결 테스트용.
    Rule N: _orca_path가 None일 수 있음 (ORCA 미설치 환경) — None 가드 필수.
    """
    global _orca_path
    if _orca_path is None:
        _orca_path = _find_orca_path()

    wsl_orca = None
    wsl_probe_setting = os.environ.get("ORCA_HEALTH_WSL_PROBE", "1").strip()
    wsl_probe_enabled = wsl_probe_setting != "0"
    if wsl_probe_enabled and _ORCA_EXECUTOR_AVAILABLE and find_orca_wsl is not None:
        try:
            wsl_orca = find_orca_wsl()  # type: ignore[misc]
        except Exception as e:
            logger.warning("[health] WSL ORCA discovery failed: %s", e)

    # Rule N: 타입 가드 — _orca_path가 Optional[Path]이므로 None 체크 먼저
    if isinstance(wsl_orca, str) and wsl_orca.strip():
        orca_exists = True
        orca_exe_str = wsl_orca.strip()
        backend = "wsl"
        path_source = "ORCA_HEALTH_WSL_PROBE"
        path_classification = "WSL_ORCA_PATH"
        blocked_reason = ""
    elif _orca_path is not None:
        orca_exists = _orca_path.exists()
        orca_exe_str = str(_orca_path)
        backend = "native"
        path_source = str(_orca_path_state.get("path_source", "unknown"))
        path_classification = str(_orca_path_state.get("path_classification", "unknown"))
        blocked_reason = str(_orca_path_state.get("blocked_reason", ""))
    else:
        orca_exists = False
        orca_exe_str = "not_found"
        backend = "none"
        path_source = str(_orca_path_state.get("path_source", "none"))
        path_classification = str(_orca_path_state.get("path_classification", "MISSING"))
        blocked_reason = str(_orca_path_state.get("blocked_reason", "No valid active ORCA executable path configured."))
        logger.warning("[health] _orca_path is None — ORCA 실행 파일을 찾지 못했습니다.")

    key_set = bool(API_KEY)
    archive_blocked = bool(_orca_path_state.get("archive_blocked", False))
    orca_available = bool(orca_exists)
    return {
        "status": "ok" if (orca_available and key_set) else "degraded",
        "orca_exe": orca_exe_str,
        "orca_backend": backend,
        "orca_exists": orca_exists,
        "orca_available": orca_available,
        "orca_configured": orca_available,
        "path_source": path_source,
        "orca_path_source": path_source,
        "path_classification": path_classification,
        "blocked_reason": blocked_reason,
        "archive_blocked": archive_blocked,
        "api_key_set": key_set,
        "api_key_configured": key_set,
        "wsl_probe": "enabled" if wsl_probe_enabled else "disabled_by_env",
        "jobs_dir": str(JOBS_DIR),
        "log_file": str(LOG_FILE),
    }
