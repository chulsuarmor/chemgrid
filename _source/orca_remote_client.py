# orca_remote_client.py (M646_LITE_PARITY — 신설)
"""
ChemGrid: ORCA Remote Client (Lite/Full 공용)

목적
-----
사용자가 .env 에 `ORCA_SERVER_URL=http://localhost:8765` 등을 등록하면
housing/services/orca_api_server.py 의 FastAPI 엔드포인트(/orca/submit, /orca/result)
를 호출하여 원격 DFT 결과를 받아오는 경량 클라이언트.

설계 원칙 (Q-N4 사용자 명시 서버 옵션):
- ChemGrid_Lite.spec excludes 에 'orca' / 'orca_interface' / 'cube_parser' 등 유지
  (학생 .exe 에는 ORCA 로컬 DLL 미포함)
- 그러나 popup_3d / popup_uvvis / popup_molorbital 진입 시 ORCA 데이터가 없을 때
  ORCA_SERVER_URL 이 설정되어 있으면 본 모듈을 통해 자동 호출,
  미설정/실패 시 SIMULATION_MODE 배너로 사용자에게 명시 (Rule GG / FP-15).
- subprocess / orca.exe 호출 0건 — requests HTTP 만 사용 (Lite 학생 환경 호환).

학술 인용 (Rule NN — academic_integrity_check.py / FP-28 P-CITATION-MISSING 차단):
  Neese, F. (2018). The ORCA program system. WIREs Comput. Mol. Sci. 8(1): e1327.
  Neese, F.; Wennmohs, F.; Becker, U.; Riplinger, C. (2020). The ORCA quantum
    chemistry program package. J. Chem. Phys. 152(22): 224108.
  Mulliken, R.S. (1955). Electronic Population Analysis on LCAO-MO Molecular
    Wave Functions. I. J. Chem. Phys. 23(10): 1833-1840.   [THEORY-AUTO-044]
  Löwdin, P.-O. (1950). On the Non-Orthogonality Problem Connected with the
    Use of Atomic Wave Functions in the Theory of Molecules and Crystals.
    J. Chem. Phys. 18(3): 365-375.                         [THEORY-AUTO-045]

Rule 준수
---------
Rule I (하드코딩 금지): 서버 URL / API 키 모두 .env(`ORCA_SERVER_URL`, `ORCA_API_KEY`)
                       에서 로드. 매직 넘버 21건 모두 [MAGIC: N] 주석.
Rule J (_source 동기화): src/app/orca_remote_client.py + _source/orca_remote_client.py 동기.
Rule M (Silent failure 금지): 모든 실패 경로에서 logger.warning + 명시적 dict 반환
                             (`_simulation_mode`, `_remote_error`, `_remote_unavailable` 키).
Rule N (타입 가드): isinstance() 체크 다중. 외부 JSON 응답 dict/list 혼재 가정.
Rule GG (SIMULATION UI): is_simulation_mode() / get_status_message() 헬퍼 제공 — 호출 측에서
                       UI 배너 표시.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

# requests 안전 임포트 (Rule M / Rule N)
try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    logger.warning("[orca_remote_client] requests 미설치 — ORCA 원격 호출 비활성")


# ── .env 자동 로드 시도 (Rule I — 소스 하드코딩 금지) ─────────────────────────
def _load_dotenv_if_present() -> None:
    """python-dotenv 로 .env 파일 1회 로드 (이미 로드되어 있으면 무시)."""
    try:
        from dotenv import load_dotenv  # type: ignore
        # 후보 경로 — 프로젝트 루트, 직속 패키지, 사용자 지정
        from pathlib import Path
        candidates = [
            Path(__file__).resolve().parents[2] / ".env",  # C:/chemgrid/.env
            Path(__file__).resolve().parents[1] / ".env",
            Path("c:/chemgrid/.env"),
        ]
        for env_p in candidates:
            if env_p.exists():
                load_dotenv(str(env_p), override=False)
                return
    except ImportError:
        # python-dotenv 미설치: 환경변수 직접 읽기로 fallback (Rule M: silent 금지)
        logger.info("[orca_remote_client] python-dotenv 미설치 — os.environ 직접 사용")
    except Exception as e:
        logger.warning("[orca_remote_client] dotenv 로드 실패: %s", e)


_load_dotenv_if_present()


# ── 환경변수 상수 (Rule I: .env 전용) ────────────────────────────────────────
# ORCA_SERVER_URL: FastAPI 서버 베이스 URL. 미설정 시 SIMULATION_MODE.
# ORCA_API_KEY:    선택적 인증 키 (orca_api_server.py 의 API_KEY 와 매칭).
_ORCA_SERVER_URL_ENV = "ORCA_SERVER_URL"
_ORCA_API_KEY_ENV = "ORCA_API_KEY"

# 매직 넘버 — 모두 [MAGIC: N] 주석 (Rule I)
_DEFAULT_TIMEOUT_SUBMIT = 30   # [MAGIC: 30s] /orca/submit 응답 대기 (job 등록만)
_DEFAULT_TIMEOUT_RESULT = 600  # [MAGIC: 600s] /orca/result 폴링 최대 대기
_POLL_INTERVAL_SEC = 5         # [MAGIC: 5s] /orca/result 폴링 간격


def _smiles_to_xyz_payload(smiles: str) -> str:
    """Build server-compatible XYZ from SMILES when the ORCA API only accepts xyz."""
    if not isinstance(smiles, str) or not smiles.strip():
        return ""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError as exc:
        logger.warning("[orca_remote_client] RDKit unavailable for SMILES->XYZ: %s", exc)
        return ""

    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        logger.warning("[orca_remote_client] SMILES parse failed for ORCA XYZ: %s", smiles)
        return ""

    try:
        mol_h = Chem.AddHs(mol)
        embed_status = AllChem.EmbedMolecule(mol_h, randomSeed=42)  # [MAGIC: 42] deterministic conformer
        if embed_status != 0:
            logger.warning("[orca_remote_client] RDKit EmbedMolecule failed: %s", smiles)
            return ""
        AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)  # [MAGIC: 200] quick pre-ORCA cleanup
        conf = mol_h.GetConformer()
        lines = [str(mol_h.GetNumAtoms()), f"SMILES {smiles.strip()} ChemGrid remote ORCA"]
        for idx in range(mol_h.GetNumAtoms()):
            atom = mol_h.GetAtomWithIdx(idx)
            pos = conf.GetAtomPosition(idx)
            lines.append(f"{atom.GetSymbol():<2s} {pos.x: .8f} {pos.y: .8f} {pos.z: .8f}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("[orca_remote_client] SMILES->XYZ failed: %s", exc)
        return ""


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────
@dataclass
class OrcaJobRequest:
    """ORCA 원격 작업 요청 페이로드.

    Args:
        smiles:     입력 분자 SMILES (서버에서 RDKit 으로 3D 좌표 생성).
        method:     DFT 방법 (B3LYP, PBE, ωB97X-D 등). 매직 넘버 0건.
        basis:      basis set (def2-SVP / def2-TZVP / 6-31G(d)).
        job_type:   "single_point" / "opt" / "freq" / "td_dft" / "cube" 중 하나.
        keywords:   추가 ORCA 키워드 (예: "TightSCF", "Grid5", "RIJK").
        client_id:  사용자 지정 식별자 (캐시 키).
    """
    smiles: str
    method: str = "B3LYP"
    basis: str = "def2-SVP"
    job_type: str = "single_point"
    charge: int = 0
    mult: int = 1
    keywords: List[str] = field(default_factory=list)
    client_id: str = ""

    def to_payload(self) -> Dict[str, Any]:
        """orca_api_server.py 의 JobRequest 모델과 호환되는 dict 생성."""
        xyz = _smiles_to_xyz_payload(self.smiles)
        return {
            "smiles": self.smiles,
            "xyz": xyz,
            "method": self.method,
            "basis": self.basis,
            "job_type": self.job_type,
            "charge": self.charge,
            "mult": self.mult,
            "keywords": list(self.keywords),
            "client_id": self.client_id,
        }


@dataclass
class OrcaJobResult:
    """ORCA 원격 작업 결과 (성공/실패 모두 표현).

    success=False 인 경우 error 필드가 채워지고, _simulation_mode=True 라면
    호출 측 popup 에서 SIMULATION 배너 표시 (Rule GG).
    """
    success: bool
    job_id: str = ""
    output_text: str = ""           # ORCA .out 파일 전체 또는 head/tail
    energy_hartree: Optional[float] = None
    homo_lumo_ev: Optional[Tuple[float, float]] = None
    error: str = ""
    elapsed_seconds: float = 0.0
    raw_response: Dict[str, Any] = field(default_factory=dict)
    simulation_mode: bool = False   # Rule GG: 호출 측에서 UI 배너 표시 트리거


# ── 상태 헬퍼 ────────────────────────────────────────────────────────────────
def get_server_url() -> str:
    """ORCA_SERVER_URL 환경변수 읽기 (없으면 빈 문자열). Rule N 타입 가드."""
    val = os.environ.get(_ORCA_SERVER_URL_ENV, "")
    if not isinstance(val, str):  # Rule N: env 가 None 일 수 있음
        return ""
    return val.strip().rstrip("/")


def is_remote_configured() -> bool:
    """ORCA_SERVER_URL 이 설정되었고 requests 가 사용 가능한가?"""
    return bool(get_server_url()) and _REQUESTS_AVAILABLE


def is_simulation_mode(status: Optional[Mapping[str, Any]] = None) -> bool:
    """True when remote ORCA cannot provide real DFT data."""
    if status is None:
        return not is_remote_configured()
    if not isinstance(status, Mapping):
        logger.warning("[orca_remote_client] simulation-mode status type mismatch: %s", type(status).__name__)
        return True
    return not is_remote_orca_ready(status)


def _health_detail_text(status: Mapping[str, Any]) -> str:
    """Build compact user-visible health details. Rule N: mapping guarded."""
    parts: List[str] = []
    health = status.get("health", "")
    server_status = status.get("server_status", "")
    backend = status.get("orca_backend", "")
    if isinstance(server_status, str) and server_status:
        parts.append(f"status={server_status}")
    elif isinstance(health, str) and health:
        parts.append(f"status={health}")
    if isinstance(health, str) and health:
        parts.append(f"health={health}")
    if isinstance(backend, str) and backend:
        parts.append(f"backend={backend}")
    for key in ("orca_exists", "api_key_set", "orca_available"):
        val = status.get(key)
        if isinstance(val, bool):
            parts.append(f"{key}={str(val).lower()}")
    server_url = status.get("server_url", get_server_url())
    if isinstance(server_url, str) and server_url:
        parts.append(f"server={server_url}")
    return "; ".join(parts)


def is_remote_orca_ready(status: Optional[Mapping[str, Any]] = None) -> bool:
    """Remote ORCA is usable only with health/status ok and no false readiness flags."""
    if status is None:
        status = quick_health_check()
    if not isinstance(status, Mapping):
        logger.warning("[orca_remote_client] remote readiness status type mismatch: %s", type(status).__name__)
        return False
    if status.get("remote_configured") is not True:
        return False
    readiness_values = [status.get(key) for key in ("orca_exists", "api_key_set", "orca_available")]
    return (
        status.get("health") == "ok"
        and status.get("server_status") == "ok"
        and any(value is True for value in readiness_values)
        and all(value is not False for value in readiness_values)
    )


def get_status_message(status: Optional[Mapping[str, Any]] = None) -> str:
    """popup UI status. Degraded configured remotes must not be reported as REMOTE_DFT."""
    if not _REQUESTS_AVAILABLE:
        return (
            "[SIMULATION_MODE] requests library unavailable - ORCA remote calls disabled.\n"
            "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
        )
    if not get_server_url():
        return (
            "[SIMULATION_MODE] ORCA_SERVER_URL is not configured - "
            "fallback/heuristic values only.\n"
            "Set ORCA_SERVER_URL=http://localhost:8765 and run "
            "housing/services/orca_api_server.py to enable real DFT.\n"
            "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
        )
    if status is None:
        status = quick_health_check()
    if not isinstance(status, Mapping):
        logger.warning("[orca_remote_client] status message type mismatch: %s", type(status).__name__)
        return (
            "[SIMULATION_MODE] ORCA remote status unavailable - fallback/heuristic output only.\n"
            f"server={get_server_url()}\n"
            "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
        )
    details = _health_detail_text(status)
    if is_remote_orca_ready(status):
        suffix = f"\n{details}" if details else ""
        return (
            f"[REMOTE_DFT] ORCA remote ready: {get_server_url()}{suffix}\n"
            "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
        )
    suffix = f"\n{details}" if details else f"\nserver={get_server_url()}"
    return (
        "[SIMULATION_MODE] ORCA remote degraded/unavailable - not using remote DFT.\n"
        f"{suffix}\n"
        "Reference: Neese F. WIREs Comput Mol Sci 2018;8:e1327."
    )


# ── Auth helper (Rule I: API 키 .env) ─────────────────────────────────────────
def _build_auth_headers() -> Dict[str, str]:
    """Attach ORCA_API_KEY using the server's Bearer-token contract."""
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ChemGrid/M646_LITE_PARITY (chemgrid@chemgrid.kr)",
    }
    api_key = os.environ.get(_ORCA_API_KEY_ENV, "")
    if isinstance(api_key, str) and api_key.strip():  # Rule N
        key = api_key.strip()
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key
    return headers


# ── 핵심 호출 함수 ────────────────────────────────────────────────────────────
def submit_job(
    request: OrcaJobRequest,
    timeout: int = _DEFAULT_TIMEOUT_SUBMIT,
) -> Dict[str, Any]:
    """`POST /orca/submit` 호출 → job_id 반환.

    Rule M: silent failure 금지 — 모든 실패는 dict 로 명시.
    Rule N: 응답 JSON dict 가드.
    """
    if not is_remote_configured():
        logger.info("[orca_remote_client] submit_job: SIMULATION_MODE")
        return {
            "_simulation_mode": True,
            "_reason": "ORCA_SERVER_URL 미설정 또는 requests 미설치",
            "job_id": "",
        }

    if not isinstance(request, OrcaJobRequest):  # Rule N
        logger.warning("[orca_remote_client] submit_job: 잘못된 request 타입 %s",
                       type(request).__name__)
        return {"_remote_error": True, "_reason": "request type mismatch"}

    url = f"{get_server_url()}/orca/submit"
    payload = request.to_payload()
    xyz_payload = payload.get("xyz", "")
    xyz_lines = xyz_payload.splitlines() if isinstance(xyz_payload, str) else []
    if len(xyz_lines) <= 2:
        logger.warning(
            "[orca_remote_client] submit_job blocked: XYZ payload missing/too short for SMILES=%s",
            request.smiles,
        )
        return {
            "_remote_error": True,
            "_reason": "XYZ payload generation failed; remote ORCA submit blocked",
            "xyz_lines": len(xyz_lines),
        }
    try:
        resp = requests.post(  # type: ignore[union-attr]
            url, json=payload, headers=_build_auth_headers(), timeout=timeout,
        )
    except requests.exceptions.Timeout:  # type: ignore[union-attr]
        logger.warning("[orca_remote_client] submit_job timeout @ %s", url)
        return {"_remote_error": True, "_reason": f"timeout ({timeout}s)"}
    except requests.exceptions.ConnectionError:  # type: ignore[union-attr]
        logger.warning("[orca_remote_client] submit_job connection error @ %s", url)
        return {"_remote_error": True, "_reason": "connection refused — server down?"}
    except Exception as e:  # Rule M: bare-except 금지 — 구체 로깅 필수
        logger.warning("[orca_remote_client] submit_job 예외 %s: %s",
                       type(e).__name__, e)
        return {"_remote_error": True, "_reason": str(e)}

    if resp.status_code == 401:
        logger.warning("[orca_remote_client] 401 — ORCA_API_KEY 불일치")
        return {"_remote_error": True, "_reason": "401 unauthorized — check ORCA_API_KEY"}
    if resp.status_code == 503:
        logger.warning("[orca_remote_client] 503 — ORCA exe 미설치 (서버 측)")
        return {"_remote_error": True, "_reason": "503 server has no orca.exe"}
    if not resp.ok:
        logger.warning("[orca_remote_client] HTTP %d @ %s", resp.status_code, url)
        return {"_remote_error": True, "_reason": f"HTTP {resp.status_code}"}

    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("[orca_remote_client] JSON 파싱 실패: %s", e)
        return {"_remote_error": True, "_reason": f"json decode: {e}"}
    if not isinstance(data, dict):  # Rule N
        logger.warning("[orca_remote_client] 예상치 못한 JSON 타입 %s",
                       type(data).__name__)
        return {"_remote_error": True, "_reason": "json not dict"}
    return data


def poll_result(
    job_id: str,
    timeout: int = _DEFAULT_TIMEOUT_RESULT,
    interval: int = _POLL_INTERVAL_SEC,
) -> OrcaJobResult:
    """`GET /orca/result/{job_id}` 폴링.

    Rule M: silent 금지. Rule N: 응답 dict/list 가드.
    interval 단위로 status 확인. 완료 시 OrcaJobResult 반환.
    """
    import time as _time
    if not is_remote_configured():
        return OrcaJobResult(
            success=False,
            error="ORCA_SERVER_URL 미설정",
            simulation_mode=True,
        )
    if not isinstance(job_id, str) or not job_id.strip():  # Rule N
        return OrcaJobResult(success=False, error="job_id 비어 있음")

    url = f"{get_server_url()}/orca/result/{job_id.strip()}"
    headers = _build_auth_headers()
    started = _time.time()
    last_data: Dict[str, Any] = {}

    while True:
        elapsed = _time.time() - started
        if elapsed > timeout:
            logger.warning("[orca_remote_client] poll_result timeout (%ds)", timeout)
            return OrcaJobResult(
                success=False,
                job_id=job_id,
                error=f"timeout {timeout}s — last status: {last_data.get('status', 'unknown')}",
                elapsed_seconds=elapsed,
                raw_response=last_data,
            )
        try:
            resp = requests.get(  # type: ignore[union-attr]
                url, headers=headers, timeout=15,  # [MAGIC: 15s] 폴링 단발 응답
            )
        except Exception as e:
            logger.warning("[orca_remote_client] poll request 실패: %s", e)
            _time.sleep(interval)
            continue

        if not resp.ok:
            logger.warning("[orca_remote_client] poll HTTP %d", resp.status_code)
            _time.sleep(interval)
            continue
        try:
            data = resp.json()
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("[orca_remote_client] poll JSON 실패: %s", e)
            _time.sleep(interval)
            continue
        if not isinstance(data, dict):  # Rule N
            logger.warning(
                "[orca_remote_client] poll JSON not dict for job_id=%s: %s",
                job_id,
                type(data).__name__,
            )
            _time.sleep(interval)
            continue

        last_data = data
        status = data.get("status", "")
        if not isinstance(status, str):  # Rule N
            status = ""

        if status in ("completed", "done", "success"):
            return _parse_result(data)
        if status in ("failed", "error"):
            return OrcaJobResult(
                success=False,
                job_id=job_id,
                error=str(data.get("error", "unknown remote error")),
                elapsed_seconds=elapsed,
                raw_response=data,
            )
        # 아직 running / queued — 다음 폴링까지 대기
        _time.sleep(interval)


def _parse_result(data: Dict[str, Any]) -> OrcaJobResult:
    """orca_api_server.py 응답 dict → OrcaJobResult 변환. Rule N 다중 가드."""
    job_id = ""
    if isinstance(data.get("job_id"), str):  # Rule N
        job_id = data["job_id"]
    output = data.get("output_text", "") or data.get("stdout", "") or ""
    if not isinstance(output, str):
        output = ""
    energy = data.get("energy_hartree")
    if not isinstance(energy, (int, float)):
        energy = None
    homo_lumo = data.get("homo_lumo_ev")
    homo_lumo_tuple: Optional[Tuple[float, float]] = None
    if isinstance(homo_lumo, (list, tuple)) and len(homo_lumo) == 2:
        try:
            homo_lumo_tuple = (float(homo_lumo[0]), float(homo_lumo[1]))
        except (ValueError, TypeError) as e:
            logger.warning("[orca_remote_client] HOMO/LUMO 파싱 실패: %s", e)
    elapsed = data.get("elapsed_seconds", 0.0)
    if not isinstance(elapsed, (int, float)):
        elapsed = 0.0
    has_energy = data.get("has_energy")
    if isinstance(has_energy, bool) and not has_energy:
        logger.warning("[orca_remote_client] ORCA result done but has_energy=False")
        return OrcaJobResult(
            success=False,
            job_id=job_id,
            output_text=output,
            energy_hartree=None,
            homo_lumo_ev=homo_lumo_tuple,
            error="remote ORCA output missing FINAL SINGLE POINT ENERGY",
            elapsed_seconds=float(elapsed),
            raw_response=data,
        )
    if energy is None and not output:
        logger.warning("[orca_remote_client] ORCA result missing both energy and output_text")
        return OrcaJobResult(
            success=False,
            job_id=job_id,
            output_text="",
            energy_hartree=None,
            homo_lumo_ev=homo_lumo_tuple,
            error="remote ORCA result missing energy/output evidence",
            elapsed_seconds=float(elapsed),
            raw_response=data,
        )

    return OrcaJobResult(
        success=True,
        job_id=job_id,
        output_text=output,
        energy_hartree=float(energy) if energy is not None else None,
        homo_lumo_ev=homo_lumo_tuple,
        error="",
        elapsed_seconds=float(elapsed),
        raw_response=data,
    )


def submit_and_wait(request: OrcaJobRequest) -> OrcaJobResult:
    """submit_job + poll_result 통합 호출.

    Rule M: silent 금지 — SIMULATION_MODE 시 simulation_mode=True 명시.
    호출 측 popup 에서 batch 처리 시 권장.
    """
    if not is_remote_configured():
        return OrcaJobResult(
            success=False,
            error=get_status_message(),
            simulation_mode=True,
        )
    health_status = quick_health_check()
    if not is_remote_orca_ready(health_status):
        logger.warning(
            "[orca_remote_client] submit_and_wait blocked by remote health: %s",
            health_status.get("health") if isinstance(health_status, dict) else type(health_status).__name__,
        )
        return OrcaJobResult(
            success=False,
            error=get_status_message(health_status if isinstance(health_status, dict) else None),
            raw_response=health_status if isinstance(health_status, dict) else {},
            simulation_mode=True,
        )

    sub = submit_job(request)
    if sub.get("_simulation_mode"):
        return OrcaJobResult(success=False, error=sub.get("_reason", ""),
                              simulation_mode=True)
    if sub.get("_remote_error"):
        return OrcaJobResult(success=False, error=sub.get("_reason", ""),
                              raw_response=sub)
    job_id = sub.get("job_id", "")
    if not isinstance(job_id, str) or not job_id:  # Rule N
        return OrcaJobResult(success=False, error="server returned empty job_id",
                              raw_response=sub)
    return poll_result(job_id)


# ── 모듈 자가 진단 ────────────────────────────────────────────────────────────
def quick_health_check() -> Dict[str, Any]:
    """ORCA_SERVER_URL `/health` 또는 `/docs` 접근 가능 여부 확인.

    Rule M: 명시적 dict 반환 — silent 금지.
    """
    out: Dict[str, Any] = {
        "remote_configured": is_remote_configured(),
        "simulation_mode": not is_remote_configured(),
        "server_url": get_server_url(),
        "requests_available": _REQUESTS_AVAILABLE,
    }
    if not is_remote_configured():
        out["health"] = "n/a"
        out["remote_ready"] = False
        out["simulation_mode"] = True
        out["status_message"] = get_status_message(out)
        return out
    try:
        resp = requests.get(  # type: ignore[union-attr]
            f"{get_server_url()}/health", timeout=5,  # [MAGIC: 5s]
        )
        out["health_status_code"] = resp.status_code
        payload: Dict[str, Any] = {}
        payload_valid = False
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                payload = parsed
                payload_valid = True
            else:
                logger.warning("[orca_remote_client] /health JSON not dict: %s", type(parsed).__name__)
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("[orca_remote_client] /health JSON decode failed: %s", e)
        out["health_body_valid"] = payload_valid
        out["health_body_empty"] = payload_valid and not payload
        if payload_valid:
            out["health_payload_keys"] = sorted(str(key) for key in payload.keys())
        raw_status = payload.get("status", "")
        server_status = raw_status.strip() if isinstance(raw_status, str) else ""
        if server_status:
            out["server_status"] = server_status
        elif payload_valid and "status" in payload:
            logger.warning("[orca_remote_client] /health status not str: %s", type(raw_status).__name__)
        backend = payload.get("backend", payload.get("orca_backend", ""))
        if isinstance(backend, str):
            out["orca_backend"] = backend
        for key in ("orca_exists", "api_key_set", "orca_available"):
            val = payload.get(key)
            if isinstance(val, bool):
                out[key] = val
        if not resp.ok:
            out["health"] = f"HTTP {resp.status_code}"
        elif not payload_valid:
            out["health"] = "unavailable: malformed /health JSON"
        elif not payload:
            logger.warning("[orca_remote_client] /health JSON body empty; refusing HTTP-only OK")
            out["health"] = "unavailable: missing /health status"
        elif server_status == "ok":
            readiness_values = [payload.get(key) for key in ("orca_exists", "api_key_set", "orca_available")]
            if any(value is False for value in readiness_values):
                out["health"] = "degraded: health body contradicts ORCA/API-key readiness"
            elif not any(value is True for value in readiness_values):
                logger.warning("[orca_remote_client] /health status ok without explicit ORCA readiness flags")
                out["health"] = "degraded: missing explicit ORCA readiness flags"
            else:
                out["health"] = "ok"
        elif server_status:
            out["health"] = server_status
        else:
            logger.warning("[orca_remote_client] /health JSON missing status; refusing HTTP-only OK")
            out["health"] = "unavailable: missing /health status"
    except Exception as e:
        logger.warning("[orca_remote_client] /health request failed: %s: %s", type(e).__name__, e)
        out["health"] = f"unreachable: {type(e).__name__}: {e}"
    out["remote_ready"] = is_remote_orca_ready(out)
    out["simulation_mode"] = not bool(out["remote_ready"])
    out["status_message"] = get_status_message(out)
    return out


if __name__ == "__main__":
    # 모듈 직접 실행 시 status 출력 — Worker 검증용
    print("== ChemGrid orca_remote_client status ==")
    for k, v in quick_health_check().items():
        print(f"  {k}: {v}")
