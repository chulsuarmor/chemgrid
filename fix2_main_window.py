"""open_3d_popup에 FEAT-4 50% 임계값 체크 추가"""
with open('c:/chemgrid/src/app/main_window.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 기존 패턴: 단순 fallback
old = (
    "        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''\n"
    "        # ★ [개선] 선택된 원자 키 가져오기 — 없으면 전체 atoms 사용\n"
    "        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())\n"
    "        if not selected_keys:\n"
    "            # Drawing 모드 selected_atoms도 확인\n"
    "            selected_keys = getattr(self.cv, 'selected_atoms', set())\n"
    "        if not selected_keys:\n"
    "            # 선택 없음 → 전체 원자 사용 (간단한 분자를 바로 3D 전환 가능)\n"
    "            selected_keys = set(self.cv.atoms.keys())\n"
)

new = (
    "        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''\n"
    "        # ★ [개선] 선택된 원자 키 가져오기 — 없으면 전체 atoms 사용\n"
    "        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())\n"
    "        if not selected_keys:\n"
    "            # Drawing 모드 selected_atoms도 확인\n"
    "            selected_keys = getattr(self.cv, 'selected_atoms', set())\n"
    "        # [FEAT-4] 선택 원자가 전체의 50% 미만이고 _last_drawn_smiles 있으면 전체 선택으로 교체\n"
    "        # 이론적 구조에서 드래그 선택 시 일부 원자만 인식되는 버그 해결\n"
    "        _all_atom_keys = set(self.cv.atoms.keys())\n"
    "        if _last_smiles and _all_atom_keys and len(selected_keys) < len(_all_atom_keys) * 0.5:\n"
    "            selected_keys = _all_atom_keys\n"
    "        if not selected_keys:\n"
    "            # 선택 없음 → 전체 원자 사용 (간단한 분자를 바로 3D 전환 가능)\n"
    "            selected_keys = set(self.cv.atoms.keys())\n"
)

if old in content:
    content = content.replace(old, new, 1)
    print("✅ FEAT-4 임계값 로직 추가 성공")
else:
    print("❌ 패턴 미발견")
    # 대안: _last_smiles가 있는 줄 이후 삽입
    idx = content.find("        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''\n")
    if idx >= 0:
        print(f"  _last_smiles found at {idx}")
        # 해당 위치 주변 100자 출력
        print(repr(content[idx:idx+400]))

try:
    compile(content, 'main_window.py', 'exec')
    print("✅ 문법 OK")
    with open('c:/chemgrid/src/app/main_window.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ 저장 완료")
except SyntaxError as e:
    print(f"❌ SyntaxError line {e.lineno}: {e.msg}")
