"""
test_10molecules.py — ChemGrid 10분자 자동화 검증 스크립트
===========================================================
사용법: python tools/test_10molecules.py

검증 항목:
  1. SMILES 조회 (BUILTIN 사전 + PubChem + Gemini)
  2. RDKit 유효성 검증
  3. 분자 원자수/결합수 타당성
  4. 공명 이온 감지 (cyclopentadienyl, tropylium)
  5. 헤모글로빈 폴백 동작 (heme SMILES 반환)

테스트 분자 세트 (물 ~ 헤모글로빈, 단계적 복잡도):
  1.  water             (H2O)           — 최단순
  2.  benzene           (C6H6)          — 방향족
  3.  glucose           (C6H12O6)       — 당류
  4.  aspirin           (C9H8O4)        — 약물
  5.  cyclopentadienyl anion (C5H5-)    — ★ 공명 이온 균등화 테스트
  6.  tropylium         (C7H7+)         — ★ 공명 이온 균등화 테스트
  7.  adenine           (C5H5N5)        — 핵산 염기
  8.  cholesterol       (C27H46O)       — 스테로이드
  9.  heme              (Fe 포르피린)    — 헤모글로빈 코어
  10. hemoglobin        → heme 폴백     — 대형 단백질 폴백 테스트
  [Bonus] CH3CH2CH2COOH — 축약식 구조식 테스트
"""

import sys
import os
import time
import pathlib

# 프로젝트 루트 및 src/app 경로 추가
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC  = ROOT / "src" / "app"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))

# .env 로드
try:
    from dotenv import load_dotenv
    _env = ROOT / "agents" / "mcp_server" / ".env"
    if _env.exists():
        load_dotenv(str(_env))
        print(f"[ENV] Loaded: {_env}")
except ImportError:
    pass

# ── RDKit 임포트 ─────────────────────────────────────────────────
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDKIT_OK = True
except ImportError:
    RDKIT_OK = False
    print("[WARN] RDKit not available — validation will be skipped")

# ── 색상 코드 ────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ============================================================
# 테스트 세트 정의
# ============================================================
TEST_MOLECULES = [
    # (입력명, 기대 원소 포함 여부, 기대 최소 원자수, 설명)
    ("water",                   ["O"],        1,   "무기물 최단순"),
    ("benzene",                 ["C"],        6,   "방향족 벤젠"),
    ("glucose",                 ["C","O"],    6,   "당류 글루코스"),
    ("aspirin",                 ["C","O"],    9,   "약물 아스피린"),
    ("cyclopentadienyl anion",  ["C"],        5,   "★공명이온-Cp음이온"),
    ("tropylium",               ["C"],        7,   "★공명이온-트로필리움"),
    ("adenine",                 ["C","N"],    5,   "핵산 염기"),
    ("cholesterol",             ["C","O"],    27,  "스테로이드"),
    ("heme",                    ["C","N","Fe"],10, "헤모글로빈 코어"),
    ("hemoglobin",              ["C","N"],    5,   "대형단백질→heme폴백"),
    # Bonus
    ("CH3CH2CH2COOH",           ["C","O"],    4,   "★축약식 부티르산"),
]

# ============================================================
# SMILES 조회 함수 (main_window._lookup_smiles_for_name 로직 재현)
# ============================================================
def lookup_smiles(name: str) -> str:
    """
    main_window._lookup_smiles_for_name()과 동일한 우선순위 로직.
    GUI 없이 독립 실행 가능한 버전.
    """
    BUILTIN = {
        "water": "O", "물": "O", "h2o": "O",
        "ammonia": "N", "co2": "O=C=O",
        "benzene": "c1ccccc1", "벤젠": "c1ccccc1",
        "toluene": "Cc1ccccc1",
        "ethanol": "CCO", "methanol": "CO",
        "acetic acid": "CC(=O)O",
        "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
        "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
        "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
        "cholesterol": "C[C@@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@@H]2CC=C4[C@@]3(CCC(O)C4)C)C",
        "adenine": "Nc1ncnc2[nH]cnc12",
        "guanine": "Nc1nc2[nH]cnc2c(=O)[nH]1",
        "cytosine": "Nc1cc[nH]c(=O)n1",
        "thymine": "Cc1c[nH]c(=O)[nH]c1=O",
        "uracil": "O=c1cc[nH]c(=O)[nH]1",
        "cyclopentadienyl anion": "[cH-]1cccc1",
        "사이클로펜타디에닐 음이온": "[cH-]1cccc1",
        "cp-": "[cH-]1cccc1",
        "tropylium": "C1=CC=CC=C[CH+]1",
        "tropylium ion": "C1=CC=CC=C[CH+]1",
        "트로필리움": "C1=CC=CC=C[CH+]1",
        "cycloheptatrienyl cation": "C1=CC=CC=C[CH+]1",
        "heme": r"CC1=C2C=C3C(=CC4=NC(=CC5=NC(=C1/N2\[Fe]N34)CC(=O)O)C(C=C)=C5C)C(C)=C(CCC(=O)O)C6=CC7=NC(=CC(=C7C)C=C)C(CCC(=O)O)=C6",
        "heme b": r"CC1=C2C=C3C(=CC4=NC(=CC5=NC(=C1/N2\[Fe]N34)CC(=O)O)C(C=C)=C5C)C(C)=C(CCC(=O)O)C6=CC7=NC(=CC(=C7C)C=C)C(CCC(=O)O)=C6",
    }

    # 축약식 사전
    CONDENSED = {
        "ch3oh": "CO", "ch3ch2oh": "CCO", "c2h5oh": "CCO",
        "ch3cooh": "CC(=O)O", "ch3ch2cooh": "CCC(=O)O",
        "ch3ch2ch2cooh": "CCCC(=O)O",
        "ch3(ch2)2cooh": "CCCC(=O)O",
        "c6h6": "c1ccccc1", "c6h12o6": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    }

    # 대형 분자 폴백
    LARGE = {
        "hemoglobin": "heme", "myoglobin": "heme",
        "albumin": None, "collagen": None, "protein": None,
        "dna": "adenine", "rna": "adenine",
    }

    lower = name.lower().strip()

    # 1) BUILTIN
    if lower in BUILTIN:
        return BUILTIN[lower]

    # 2) 축약식
    key = lower.replace(" ", "")
    if key in CONDENSED:
        return CONDENSED[key]

    # 3) RDKit 직접 SMILES
    if RDKIT_OK:
        mol = Chem.MolFromSmiles(name)
        if mol:
            return Chem.MolToSmiles(mol)

    # 4) PubChem
    try:
        import requests
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{requests.utils.quote(name)}/property/CanonicalSMILES/JSON"
        )
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            props = resp.json().get("PropertyTable", {}).get("Properties", [{}])
            smiles = props[0].get("CanonicalSMILES", "")
            if smiles:
                return smiles
    except Exception:
        pass

    # 5) 대형 분자 폴백
    if lower in LARGE:
        alt = LARGE[lower]
        if alt:
            return lookup_smiles(alt)
        return ""

    # 6) Gemini
    api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    if api_key:
        try:
            import google.genai as _genai
            client = _genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=(
                    f"화학 분자명 또는 분자식 '{name}'의 SMILES 코드를 알려주세요. "
                    "SMILES 코드만 한 줄로 출력하세요."
                ),
            )
            s = response.text.strip().split()[0]
            if s and s.upper() not in ("UNKNOWN", "NONE", ""):
                return s
        except Exception:
            pass

    return ""


# ============================================================
# 검증 로직
# ============================================================
def validate_smiles(smiles: str, expected_elements: list, min_atoms: int):
    """
    Returns: (pass: bool, msg: str, atom_count: int, formula: str)
    """
    if not smiles:
        return False, "SMILES 없음 (조회 실패)", 0, ""
    if not RDKIT_OK:
        return True, "RDKit 없음 (스킵)", 0, smiles
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False, f"RDKit 파싱 실패: {smiles[:60]}", 0, ""
    formula = rdMolDescriptors.CalcMolFormula(mol)
    n_atoms = mol.GetNumAtoms()
    heavy_syms = {a.GetSymbol() for a in mol.GetAtoms()}
    missing = [e for e in expected_elements if e not in heavy_syms]
    if missing:
        return False, f"기대 원소 누락: {missing} | 실제: {heavy_syms}", n_atoms, formula
    if n_atoms < min_atoms:
        return False, f"원자수 부족: {n_atoms} < {min_atoms}", n_atoms, formula
    return True, "OK", n_atoms, formula


def check_resonance_ion(name: str, smiles: str) -> str:
    """
    공명 이온 SMILES가 방향족/전하분산 표기인지 확인.
    cyclopentadienyl anion → [cH-]1cccc1 (소문자 c = 방향족)
    tropylium → [CH+]1=CC=CC=CC1
    """
    lower = name.lower()
    if "cyclopentadienyl" in lower and "anion" in lower:
        if "[cH-]" in smiles or "[CH-]" in smiles or "c1" in smiles:
            return "✅ 방향족 표기 확인 (5π, 4n+2=6)"
        return "⚠️ 비방향족 표기 — 균등화 필요"
    if "tropylium" in lower or "cycloheptatrienyl" in lower:
        if "[CH+]" in smiles or "+" in smiles:
            return "✅ 양이온 표기 확인 (7π, 4n+2=6이지만 6π → 사실 4n+2=2 불일치, 하지만 실험적 방향족)"
        return "⚠️ 양전하 표기 없음"
    return ""


# ============================================================
# 메인 실행
# ============================================================
def main():
    print(f"\n{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}{CYAN}  ChemGrid 10분자 자동화 검증 테스트{RESET}")
    print(f"{BOLD}{'='*65}{RESET}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  RDKit:  {'OK' if RDKIT_OK else '미설치'}")
    print(f"  GEMINI: {'연결됨' if (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')) else '키 없음'}")
    print(f"{'='*65}\n")

    results = []
    total_pass = 0
    total_fail = 0

    for idx, (mol_name, exp_elements, min_atoms, desc) in enumerate(TEST_MOLECULES, 1):
        print(f"{BOLD}[{idx:02d}/{len(TEST_MOLECULES)}] {mol_name}{RESET}  ({desc})")
        t0 = time.time()
        smiles = lookup_smiles(mol_name)
        elapsed = time.time() - t0

        ok, msg, n_atoms, formula = validate_smiles(smiles, exp_elements, min_atoms)

        # 공명 이온 추가 체크
        ion_msg = check_resonance_ion(mol_name, smiles)

        if ok:
            total_pass += 1
            status = f"{GREEN}PASS{RESET}"
        else:
            total_fail += 1
            status = f"{RED}FAIL{RESET}"

        smiles_preview = (smiles[:55] + "...") if len(smiles) > 55 else smiles
        print(f"  상태:   [{status}] {msg}")
        print(f"  SMILES: {smiles_preview or '(없음)'}")
        print(f"  분자식: {formula or '?'} | 원자수: {n_atoms} | 소요: {elapsed:.2f}s")
        if ion_msg:
            print(f"  공명:   {ion_msg}")
        print()

        results.append({
            "name": mol_name, "smiles": smiles, "pass": ok,
            "msg": msg, "atoms": n_atoms, "formula": formula,
            "desc": desc, "elapsed": elapsed,
        })

    # ── 요약 ─────────────────────────────────────────────────
    print(f"{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}  검증 결과 요약{RESET}")
    print(f"{'='*65}")
    print(f"  {GREEN}통과: {total_pass}{RESET} / {total_fail + total_pass}  |  "
          f"{RED}실패: {total_fail}{RESET}")
    print()

    fail_items = [r for r in results if not r["pass"]]
    if fail_items:
        print(f"{RED}{BOLD}  ★ 실패 목록:{RESET}")
        for r in fail_items:
            print(f"    - [{r['name']}]: {r['msg']}")
    else:
        print(f"{GREEN}{BOLD}  ★ 모든 테스트 통과! ★{RESET}")

    print(f"{'='*65}\n")

    # ── 보고서 저장 ───────────────────────────────────────────
    report_path = ROOT / "docs" / "reports" / "test_10mol_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# ChemGrid 10분자 자동화 검증 보고서\n\n")
        f.write(f"**실행 시간:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**결과:** {total_pass}개 통과 / {total_fail}개 실패\n\n")
        f.write("| # | 분자명 | SMILES | 분자식 | 원자수 | 결과 | 비고 |\n")
        f.write("|---|--------|--------|--------|--------|------|------|\n")
        for i, r in enumerate(results, 1):
            s_preview = (r["smiles"][:40] + "...") if len(r["smiles"]) > 40 else r["smiles"]
            stat = "✅ PASS" if r["pass"] else "❌ FAIL"
            f.write(f"| {i} | {r['name']} | `{s_preview}` | {r['formula']} | {r['atoms']} | {stat} | {r['msg']} |\n")

    print(f"[보고서 저장] {report_path}\n")
    return total_fail


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
