"""Step 3.6 autocomplete 블록을 pubchem_client 호출로 교체"""

with open("src/app/main_window.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Step 3.6 블록 찾기
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "[Step 3.6]" in line:
        start_idx = i
    if start_idx is not None and i > start_idx and line.strip() == 'return ""':
        end_idx = i
        break

print(f"Step 3.6 시작: 라인 {start_idx+1}")
print(f"return 직전 라인: {end_idx+1}")

# start_idx ~ end_idx-1 (except/pass 포함) 을 새 블록으로 교체
# end_idx 는 `        return ""\n` 라인 (유지)
# start_idx 부터 end_idx-1 까지 찾기 (except Exception:\n + pass\n 포함)
# end_idx-1: pass\n, end_idx-2: except Exception:\n

# 새 블록
new_block = [
    '        # \u2500\u2500 [Step 3.6] PubChem Autocomplete fuzzy matching (pubchem_client: \ucd08\ub2f9 1\ud68c \uc18d\ub3c4 \uc81c\ud55c) \u2500\u2500\n',
    '        try:\n',
    '            for _sug in _pc_client.get_suggestions(name, limit=3):\n',
    '                if _sug.lower() == name.lower():\n',
    '                    continue\n',
    '                _sug_smiles = _pc_client.get_smiles_by_name(_sug)\n',
    '                if _sug_smiles:\n',
    '                    return _sug_smiles\n',
    '        except Exception:\n',
    '            pass\n',
    '\n',
]

# 기존 블록 범위: start_idx ~ end_idx-1 (except/pass 뒤 빈줄까지)
# 실제로 end_idx 는 'return ""' 라인이므로
# start_idx ~ end_idx 직전 빈줄 까지가 Step 3.6 블록
# 즉 lines[start_idx:end_idx] 를 new_block으로 교체

# end_idx 바로 앞 빈줄 확인
print(f"lines[end_idx-1]: {repr(lines[end_idx-1])}")
print(f"lines[end_idx-2]: {repr(lines[end_idx-2])}")

# 교체 실행
new_lines = lines[:start_idx] + new_block + lines[end_idx:]

with open("src/app/main_window.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"[main_window] Step 3.6 블록 교체 완료 ({end_idx - start_idx}줄 → {len(new_block)}줄)")

# 검증
with open("src/app/main_window.py", "r", encoding="utf-8") as f:
    content = f.read()

if "_req3" in content:
    print("WARNING: _req3 호출이 아직 남아 있습니다!")
else:
    print("[main_window] _req3 완전히 제거 확인 OK")

if "_pc_client.get_suggestions" in content:
    print("[main_window] get_suggestions 호출 확인 OK")
