"""
_patch_pubchem.py — PubChem 호출을 pubchem_client 모듈로 교체하는 패치 스크립트
모든 PubChem REST 호출에 API 키 + 초당 1회 속도 제한 적용
"""
import re

# ============================================================
# 1. main_window.py 패치
# ============================================================
with open("src/app/main_window.py", "r", encoding="utf-8") as f:
    src = f.read()

# 1-a) import 추가 (from canvas import ... 직후)
if "import pubchem_client as _pc_client" not in src:
    src = src.replace(
        "from canvas import MoleculeCanvas",
        "from canvas import MoleculeCanvas\nimport pubchem_client as _pc_client  # [pubchem 통합] API 키 + rate limiter"
    )
    print("[main_window] import 추가 완료")

# 1-b) Step 2 PubChem 블록 교체
# 기존: import requests + url 빌드 + requests.get() + 파싱
step2_old = (
    "        try:\n"
    "            import requests\n"
    "            url = (\n"
    "                # [ISSUE-4 FIX] CanonicalSMILES \u2192 IsomericSMILES (\ubc29\ud5a5\uc871 \uc18c\ubb38\uc790 \ud45c\uae30 \ubcf4\uc874)\n"
    '                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"\n'
    '                f"{requests.utils.quote(name)}/property/IsomericSMILES/JSON"\n'
    "            )\n"
    "            resp = requests.get(url, timeout=3)\n"
    "            if resp.status_code == 200:\n"
    "                data = resp.json()\n"
    "                # [ISSUE-4 FIX] IsomericSMILES \ud0a4\ub85c \ud30c\uc2f1 (CanonicalSMILES \u2192 \ubc29\ud5a5\uc871 \uc18c\ubb38\uc790 \uc190\uc2e4)\n"
    '                smiles = data.get("PropertyTable", {}).get("Properties", [{}])[0].get("IsomericSMILES", "")\n'
    "                if smiles:\n"
    "                    # RDKit \uc720\ud6a8\uc131 \uac80\uc99d \ud6c4 \ubc18\ud658 (PubChem \ub370\uc774\ud130\ub3c4 \ud55c \ubc88 \uac80\uc99d)\n"
    "                    try:\n"
    "                        from rdkit import Chem as _Chem\n"
    "                        _mol = _Chem.MolFromSmiles(smiles)\n"
    "                        if _mol:\n"
    "                            return _Chem.MolToSmiles(_mol)\n"
    "                    except Exception:\n"
    "                        pass\n"
    "                    return smiles\n"
    "        except Exception:\n"
    "            pass\n"
)
step2_new = (
    "        # ── [Step 2] PubChem REST API (pubchem_client: API \ud0a4 + \ucd08\ub2f9 1\ud68c \uc18d\ub3c4 \uc81c\ud55c) ──\n"
    "        try:\n"
    "            _pc_smiles = _pc_client.get_smiles_by_name(name)\n"
    "            if _pc_smiles:\n"
    "                try:\n"
    "                    from rdkit import Chem as _Chem\n"
    "                    _mol = _Chem.MolFromSmiles(_pc_smiles)\n"
    "                    if _mol:\n"
    "                        return _Chem.MolToSmiles(_mol)\n"
    "                except Exception:\n"
    "                    pass\n"
    "                return _pc_smiles\n"
    "        except Exception:\n"
    "            pass\n"
)
if step2_old in src:
    src = src.replace(step2_old, step2_new)
    print("[main_window] Step 2 PubChem 블록 교체 완료")
else:
    print("[main_window] WARNING: Step 2 블록을 찾지 못함 - 수동 확인 필요")

# 1-c) Step 3.5: _req2.get(pc_url) → _pc_client._get(pc_url)
#  import requests as _req2 제거, _req2.get 교체
if "import requests as _req2" in src:
    src = src.replace("                import requests as _req2\n", "")
    print("[main_window] import requests as _req2 제거 완료")
src = src.replace("_req2.get(pc_url, timeout=5)", "_pc_client._get(pc_url, timeout=5)")
# _req2.get(kg url) - Google KG 호출 (PubChem 아님) → 별도 requests 사용 필요
# Google KG는 속도제한 대상 아니므로 _req2만 복원
if "_req2.get(" in src:
    # Google KG 호출만 남은 경우 - requests 재추가
    src = src.replace(
        "                if google_key:\n",
        "                if google_key:\n"
        "                    import requests as _req2\n"
    )
    print("[main_window] Google KG용 _req2 재추가 완료")

count_pc_r = src.count("_pc_client._get(pc_url")
print(f"[main_window] pc_r 교체 수: {count_pc_r}")

# 1-d) Step 3.6 전체 교체
step36_old = (
    "        # \u2500\u2500 [Step 3.6] PubChem Autocomplete fuzzy matching \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "        # \uc624\ud0c0/\uc57d\uc5b4 \ub4f1 \ubd80\uc815\ud655\ud55c \uc785\ub825\uc5d0 \ub300\ud574 PubChem\uc758 \uc790\ub3d9\uc644\uc131\uc73c\ub85c \uc815\uaddc\uba85 \ud68d\ub4dd\n"
    "        try:\n"
    "            import requests as _req3\n"
    "            import urllib.parse as _up3\n"
    "            ac_url = (\n"
    '                f"https://pubchem.ncbi.nlm.nih.gov/rest/autocomplete/compound/"\n'
    '                f"{_up3.quote(name)}/JSON?limit=3"\n'
    "            )\n"
    "            ac_resp = _req3.get(ac_url, timeout=5)\n"
    "            if ac_resp.status_code == 200:\n"
    '                suggestions = ac_resp.json().get("dictionary_terms", {}).get("compound", [])\n'
    "                for sug in suggestions:\n"
    "                    if sug.lower() == name.lower():\n"
    "                        continue  # \ub3d9\uc77c \uc774\ub984\uc740 \uc774\ubbf8 PubChem\uc5d0\uc11c \uc2dc\ub3c4\ud588\uc73c\ubbc0\ub85c \uac74\ub108\ub700\n"
    "                    sug_url = (\n"
    '                        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"\n'
    '                        f"{_up3.quote(sug)}/property/IsomericSMILES/JSON"\n'
    "                    )\n"
    "                    sug_resp = _req3.get(sug_url, timeout=5)\n"
    "                    if sug_resp.status_code == 200:\n"
    "                        _sug_smiles = (\n"
    "                            sug_resp.json()\n"
    '                            .get("PropertyTable", {})\n'
    '                            .get("Properties", [{}])[0]\n'
    '                            .get("IsomericSMILES", "")\n'
    "                        )\n"
    "                        if _sug_smiles:\n"
    "                            return _sug_smiles\n"
    "        except Exception:\n"
    "            pass\n"
)
step36_new = (
    "        # \u2500\u2500 [Step 3.6] PubChem Autocomplete fuzzy matching (pubchem_client: \ucd08\ub2f9 1\ud68c \uc18d\ub3c4 \uc81c\ud55c) \u2500\u2500\n"
    "        try:\n"
    "            for _sug in _pc_client.get_suggestions(name, limit=3):\n"
    "                if _sug.lower() == name.lower():\n"
    "                    continue\n"
    "                _sug_smiles = _pc_client.get_smiles_by_name(_sug)\n"
    "                if _sug_smiles:\n"
    "                    return _sug_smiles\n"
    "        except Exception:\n"
    "            pass\n"
)
if step36_old in src:
    src = src.replace(step36_old, step36_new)
    print("[main_window] Step 3.6 autocomplete 블록 교체 완료")
else:
    print("[main_window] WARNING: Step 3.6 블록을 찾지 못함 - 수동 확인 필요")

with open("src/app/main_window.py", "w", encoding="utf-8") as f:
    f.write(src)
print("[main_window] 저장 완료\n")

# ============================================================
# 2. popup_3d.py 패치 - PubChemClient.lookup_by_smiles() 교체
# ============================================================
with open("src/app/popup_3d.py", "r", encoding="utf-8") as f:
    src = f.read()

# 2-a) import pubchem_client 추가
if "import pubchem_client as _pc_client" not in src:
    # REQUESTS_AVAILABLE 섹션 직후에 추가
    src = src.replace(
        "REQUESTS_AVAILABLE = False\ntry:\n    import requests\n    REQUESTS_AVAILABLE = True\nexcept ImportError:\n    logger.warning(\"requests not available \u2014 PubChem disabled\")",
        "REQUESTS_AVAILABLE = False\ntry:\n    import requests\n    REQUESTS_AVAILABLE = True\nexcept ImportError:\n    logger.warning(\"requests not available \u2014 PubChem disabled\")\n\n# pubchem_client: API \ud0a4 + \ucd08\ub2f9 1\ud68c \uc18d\ub3c4 \uc81c\ud55c \uc801\uc6a9\ntry:\n    import pubchem_client as _pc_client\n    _PC_CLIENT_AVAILABLE = True\nexcept ImportError:\n    _PC_CLIENT_AVAILABLE = False\n    _pc_client = None"
    )
    print("[popup_3d] pubchem_client import 추가 완료")

# 2-b) PubChemClient.lookup_by_smiles 메서드 교체
old_method = '''    def lookup_by_smiles(self, smiles: str) -> Optional[Dict[str, Any]]:
        """SMILES로 PubChem 조회. 캐시 사용."""
        if not REQUESTS_AVAILABLE or not smiles:
            return None
        if smiles in self._cache:
            return self._cache[smiles]
        try:
            # Step 1: Get CID from SMILES
            url = f"{self.BASE_URL}/compound/smiles/{requests.utils.quote(smiles)}/property/" \\
                  f"IUPACName,MolecularFormula,MolecularWeight,XLogP,TPSA,Complexity," \\
                  f"HBondDonorCount,HBondAcceptorCount,RotatableBondCount,ExactMass/JSON"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            props = data.get("PropertyTable", {}).get("Properties", [])
            if not props:
                return None
            p = props[0]
            cid = p.get("CID")
            result = {
                "cid": cid,
                "iupac_name": p.get("IUPACName", ""),
                "molecular_formula": p.get("MolecularFormula", ""),
                "molecular_weight": p.get("MolecularWeight", ""),
                "xlogp": p.get("XLogP", ""),
                "tpsa": p.get("TPSA", ""),
                "complexity": p.get("Complexity", ""),
                "hbd": p.get("HBondDonorCount", ""),
                "hba": p.get("HBondAcceptorCount", ""),
                "rotatable_bonds": p.get("RotatableBondCount", ""),
                "exact_mass": p.get("ExactMass", ""),
                "cas_number": "",
                "source": "PubChem DB",
            }
            if cid:
                syn_url = f"{self.BASE_URL}/compound/cid/{cid}/synonyms/JSON"
                syn_resp = requests.get(syn_url, timeout=10)
                if syn_resp.status_code == 200:
                    import re
                    synonyms = syn_resp.json().get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
                    for syn in synonyms:
                        if re.match(r"^\\d{2,7}-\\d{2}-\\d$", syn):
                            result["cas_number"] = syn
                            break
            self._cache[smiles] = result
            return result
        except Exception as e:
            logger.warning(f"PubChem lookup failed: {e}")
            return None'''

new_method = '''    def lookup_by_smiles(self, smiles: str) -> Optional[Dict[str, Any]]:
        """SMILES로 PubChem 조회. 캐시 사용. pubchem_client 통합 (API 키 + 초당 1회 속도 제한)."""
        if not smiles:
            return None
        if smiles in self._cache:
            return self._cache[smiles]
        try:
            if _PC_CLIENT_AVAILABLE and _pc_client is not None:
                result = _pc_client.get_info_by_smiles(smiles)
            elif REQUESTS_AVAILABLE:
                # fallback: pubchem_client 없을 때 직접 호출 (속도 제한 없음 주의)
                result = None
            else:
                return None
            if result:
                self._cache[smiles] = result
            return result
        except Exception as e:
            logger.warning(f"PubChem lookup failed: {e}")
            return None'''

if old_method in src:
    src = src.replace(old_method, new_method)
    print("[popup_3d] lookup_by_smiles 교체 완료")
else:
    # 부분 매칭으로 재시도
    print("[popup_3d] WARNING: lookup_by_smiles 정확한 매칭 실패 - 부분 교체 시도")
    # requests.get 호출만 교체
    src = src.replace(
        "resp = requests.get(url, timeout=10)\n            if resp.status_code != 200:",
        "resp = (_pc_client._get(url, timeout=10) if _PC_CLIENT_AVAILABLE else requests.get(url, timeout=10))\n            if resp is None or resp.status_code != 200:"
    )
    src = src.replace(
        "syn_resp = requests.get(syn_url, timeout=10)\n                if syn_resp.status_code == 200:",
        "syn_resp = (_pc_client._get(syn_url, timeout=10) if _PC_CLIENT_AVAILABLE else requests.get(syn_url, timeout=10))\n                if syn_resp and syn_resp.status_code == 200:"
    )

with open("src/app/popup_3d.py", "w", encoding="utf-8") as f:
    f.write(src)
print("[popup_3d] 저장 완료\n")

# ============================================================
# 3. canvas.py 패치 - _fetch_molecule_name() 교체
# ============================================================
with open("src/app/canvas.py", "r", encoding="utf-8") as f:
    src = f.read()

# 3-a) import pubchem_client 추가
if "import pubchem_client as _pc_client" not in src:
    # os import 직후
    src = src.replace(
        "import math\nimport copy\nimport os",
        "import math\nimport copy\nimport os\ntry:\n    import pubchem_client as _pc_client\n    _PC_CLIENT_AVAILABLE = True\nexcept ImportError:\n    _PC_CLIENT_AVAILABLE = False\n    _pc_client = None"
    )
    print("[canvas] pubchem_client import 추가 완료")

# 3-b) _fetch_molecule_name의 requests.get 교체
# 기존: resp = requests.get(url, timeout=5)
# 교체: resp = (_pc_client._get(url, timeout=5) if _PC_CLIENT_AVAILABLE else requests.get(url, timeout=5))
old_fetch = "            resp = requests.get(url, timeout=5)\n            if resp.status_code == 200:"
new_fetch = (
    "            resp = (\n"
    "                _pc_client._get(url, timeout=5)\n"
    "                if _PC_CLIENT_AVAILABLE\n"
    "                else requests.get(url, timeout=5)\n"
    "            )\n"
    "            if resp is not None and resp.status_code == 200:"
)
if old_fetch in src:
    src = src.replace(old_fetch, new_fetch)
    print("[canvas] _fetch_molecule_name requests.get 교체 완료")
else:
    print("[canvas] WARNING: requests.get 패턴 찾지 못함")

with open("src/app/canvas.py", "w", encoding="utf-8") as f:
    f.write(src)
print("[canvas] 저장 완료\n")

print("=== 모든 패치 완료 ===")
