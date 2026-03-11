"""PubChem 응답 키 실제 확인"""
import sys
sys.path.insert(0, 'src/app')
import pubchem_client as pc
import requests, urllib.parse

name = "dopamine"
url = (
    f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
    f"{urllib.parse.quote(name)}/property/IsomericSMILES/JSON"
)

# 1) 직접 호출
r = requests.get(url, timeout=5)
j = r.json()
print("=== 직접 응답 JSON ===")
print(j)
props = j.get("PropertyTable", {}).get("Properties", [])
print("Properties[0] 키들:", list(props[0].keys()) if props else "없음")
print("IsomericSMILES:", props[0].get("IsomericSMILES") if props else "없음")
print("SMILES:", props[0].get("SMILES") if props else "없음")
print()

# 2) _get 헬퍼로 호출 (rate limiter 적용)
print("=== pubchem_client._get() 호출 ===")
r2 = pc._get(url, timeout=5)
if r2:
    j2 = r2.json()
    props2 = j2.get("PropertyTable", {}).get("Properties", [])
    print("Properties[0] 키들:", list(props2[0].keys()) if props2 else "없음")
    print("Status:", r2.status_code)
else:
    print("r2 is None!")
