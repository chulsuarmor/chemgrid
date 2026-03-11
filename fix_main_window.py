"""main_window.py의 open_3d_popup 중복 블록 수정"""
import re

with open('c:/chemgrid/src/app/main_window.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 잘못된 중복 패턴 찾기: 두 번째 FEAT-4 Fix 블록 (들여쓰기 안된 채로 if not selected_keys: 뒤에 옴)
# 원본에서 두 번 나타나는 블록 중 두 번째 것을 제거
old_bad = (
    "        if not selected_keys:\n"
    "        # ★ [FEAT-4 Fix] _last_drawn_smiles가 있으면 전체 분자 선택 보장\n"
    "        # 이론적 구조 → 입체 구조 전환 시 선택 도구가 일부만 긁어오는 버그 해결\n"
    "        # _last_drawn_smiles 존재 시 전체 원자를 선택 (부분 선택 무시)\n"
    "        _last_smiles = getattr(self.cv, '_last_drawn_smiles', '') or ''\n"
    "        # ★ [개선] 선택된 원자 키 가져오기 — 없으면 전체 atoms 사용\n"
    "        selected_keys = getattr(self.cv, 'selected_molecule_keys', set())\n"
    "        if not selected_keys:\n"
    "            # Drawing 모드 selected_atoms도 확인\n"
    "            selected_keys = getattr(self.cv, 'selected_atoms', set())\n"
    "        # [FEAT-4] 선택 원자가 전체의 50% 미만이고 _last_drawn_smiles 있으면 전체 선택으로 교체\n"
    "        all_atom_keys = set(self.cv.atoms.keys())\n"
    "        if _last_smiles and all_atom_keys and len(selected_keys) < len(all_atom_keys) * 0.5:\n"
    "            selected_keys = all_atom_keys\n"
    "        if not selected_keys:\n"
    "            # 선택 없음 → 전체 원자 사용 (간단한 분자를 바로 3D 전환 가능)\n"
    "            selected_keys = set(self.cv.atoms.keys())\n"
)

new_good = (
    "        if not selected_keys:\n"
    "            # 선택 없음 → 전체 원자 사용 (간단한 분자를 바로 3D 전환 가능)\n"
    "            selected_keys = set(self.cv.atoms.keys())\n"
)

if old_bad in content:
    content = content.replace(old_bad, new_good, 1)
    print("✅ 중복 블록 제거 성공")
else:
    # 패턴이 조금 다를 수 있으니 수동으로 확인
    idx = content.find("        if not selected_keys:\n        # ★ [FEAT-4 Fix]")
    print(f"Pattern 2 idx={idx}")
    if idx >= 0:
        # 해당 위치부터 내용 찾아서 제거
        end_marker = "            selected_keys = set(self.cv.atoms.keys())\n\n        if not selected_keys:"
        end_idx = content.find(end_marker, idx)
        if end_idx >= 0:
            content = content[:idx] + "        if not selected_keys:\n            # 선택 없음 → 전체 원자 사용\n            selected_keys = set(self.cv.atoms.keys())\n" + content[end_idx + len("            selected_keys = set(self.cv.atoms.keys())\n"):]
            print("✅ 수동 패턴으로 제거 성공")
        else:
            print(f"❌ end_marker 못 찾음")
    else:
        print("❌ 패턴 못 찾음 — 수동 확인 필요")

# 문법 검증
try:
    compile(content, 'main_window.py', 'exec')
    print("✅ 문법 OK")
    with open('c:/chemgrid/src/app/main_window.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ 저장 완료")
except SyntaxError as e:
    print(f"❌ SyntaxError: {e}")
    # 저장하지 않음
