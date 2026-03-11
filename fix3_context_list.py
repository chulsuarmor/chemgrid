"""context_list.md의 FEAT-3, FEAT-4 완료 항목 체크"""
with open('c:/chemgrid/context_list.md', 'r', encoding='utf-8') as f:
    content = f.read()

# FEAT-3 단기 임시 해결 완료 표시
content = content.replace(
    "- [ ] **단기 임시 해결**: SMILES에서 방향족 원자(소문자 c,n,o) + 전하 패턴 감지 → 고리 전체 원자에 charge 균등 강제 적용 (`renderer.py` ionic_bias_uniform)",
    "- [x] **단기 임시 해결 완료(2026-03-10)**: `renderer.py` raw_strength 조건 확장 → ring_atoms_all 포함 원자도 strength=2.2 적용 → 고리 원자 간 구름 크기 균등화"
)

# FEAT-4 선택 버그 완료 표시
content = content.replace(
    "- [ ] 선택 로직 대안: `_last_drawn_smiles` 기반으로 전체 분자 선택 → layer_logic에 `select_all_from_smiles()` 추가",
    "- [x] **선택 버그 수정 완료(2026-03-10)**: `open_3d_popup()` 내 50% 임계값 체크 추가 — 선택 원자 < 전체의 50% & _last_drawn_smiles 존재 시 전체 원자 선택으로 자동 교체"
)

# 세션 완료 사항 추가
new_section = """
---

## [PHASE 6] 2026-03-10 세션 2 완료 사항

- [x] **BUG-3/FEAT-3 (전자구름 편재화)**: `renderer.py` `raw_strength` 조건 수정
  - 원인: `[cH-]`/`[cH+]` 원자가 `aromatic` set에 누락 → strength=0.85 (타 원자 2.2) → 고리 내 불균등 구름
  - 수정: `raw_strength = 2.2 if (pt_key in aromatic or pt_key in ring_atoms_all) else ...`
  - 효과: 모든 ring_atoms_all 원자가 동일 strength → 균등한 전자구름 크기

- [x] **FEAT-4 (선택 버그)**: `main_window.py` `open_3d_popup()` 수정
  - 원인: `selected_molecule_keys`가 불완전 → `_build_smiles_from_graph`가 일부 원자만 인식
  - 수정: `_last_drawn_smiles` 존재 + 선택 원자 < 전체의 50% → 전체 원자(`all_atom_keys`)로 자동 교체
  - 효과: AI 입력 후 생성된 분자의 3D 전환 시 전체 분자 올바르게 전달

- [x] **FEAT-5 (AI 입력)**: `main_window.py` 확인 — PubChem REST API + BUILTIN 사전 이미 구현 완료
  - BUILTIN: benzene, tropylium, aspirin 등 포함
  - PubChem fallback: `requests.get()` + `CanonicalSMILES` 조회 구현됨
  - Gemini AI fallback: `gemini-2.0-flash` 최종 폴백

- [x] `mistakes.md` 신규 2건 기록: BUG-3 raw_strength 원인, FEAT-4 부분선택 원인

---
"""

with open('c:/chemgrid/context_list.md', 'a', encoding='utf-8') as f:
    f.write(new_section)

with open('c:/chemgrid/context_list.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("context_list.md 업데이트 완료")
