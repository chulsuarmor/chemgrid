"""ChemGrid 사전 비행 검증 스크립트"""
import ast
import os
import sys
import re

INTEGRATED = r"c:\chemgrid\agents\10_testing_build\integrated"

print("=" * 60)
print("STEP 1-A: AST 구문 검증")
print("=" * 60)
ok = 0
fail = 0
for f in sorted(os.listdir(INTEGRATED)):
    if f.endswith('.py'):
        path = os.path.join(INTEGRATED, f)
        try:
            ast.parse(open(path, encoding='utf-8').read())
            ok += 1
        except SyntaxError as e:
            print(f"  ❌ {f}: {e}")
            fail += 1
print(f"  결과: {ok} OK, {fail} FAIL")

print()
print("=" * 60)
print("STEP 1-B: ChemDraw 잔존 검사")
print("=" * 60)
chemdraw_count = 0
for f in sorted(os.listdir(INTEGRATED)):
    if f.endswith('.py'):
        path = os.path.join(INTEGRATED, f)
        content = open(path, encoding='utf-8').read()
        matches = [(i+1, line.strip()) for i, line in enumerate(content.split('\n'))
                   if 'ChemDraw' in line and not line.strip().startswith('#')]
        if matches:
            for lineno, line in matches:
                print(f"  ⚠️ {f}:{lineno} → {line[:80]}")
                chemdraw_count += 1
if chemdraw_count == 0:
    print("  ✅ ChemDraw 잔존 0건")
else:
    print(f"  ❌ ChemDraw 잔존 {chemdraw_count}건")

print()
print("=" * 60)
print("STEP 1-C: Agent 03 고리 함수 존재 확인")
print("=" * 60)
layer_logic_path = os.path.join(INTEGRATED, "layer_logic.py")
if os.path.exists(layer_logic_path):
    content = open(layer_logic_path, encoding='utf-8').read()
    funcs = ['_find_ring_containing_bond', '_get_ring_center_direction']
    for func in funcs:
        if func in content:
            # Find the def line
            for i, line in enumerate(content.split('\n')):
                if f'def {func}' in line:
                    print(f"  ✅ {func}() → L{i+1}")
                    break
            else:
                print(f"  ⚠️ {func} 문자열은 있으나 def 미발견")
        else:
            print(f"  ❌ {func}() 없음!")
    
    # Check if it's used in render methods
    ring_dir_usage = content.count('_get_ring_center_direction')
    print(f"  📊 _get_ring_center_direction 사용 횟수: {ring_dir_usage}")
else:
    print("  ❌ layer_logic.py 파일 없음!")

print()
print("=" * 60)
print("STEP 1-D: Agent 04 Procrustes 함수 존재 확인")
print("=" * 60)
analyzer_path = os.path.join(INTEGRATED, "analyzer.py")
if os.path.exists(analyzer_path):
    content = open(analyzer_path, encoding='utf-8').read()
    if '_align_to_original' in content:
        for i, line in enumerate(content.split('\n')):
            if 'def _align_to_original' in line:
                print(f"  ✅ _align_to_original() → L{i+1}")
                break
    else:
        print("  ❌ _align_to_original() 없음!")
    
    if 'np.linalg.svd' in content or 'numpy' in content:
        print("  ✅ numpy/SVD 사용 확인")
    else:
        print("  ⚠️ numpy/SVD 미사용 — Procrustes 미구현 가능성")
else:
    print("  ❌ analyzer.py 파일 없음!")

print()
print("=" * 60)
print("STEP 1-E: Agent 06 GL import 크래시 확인 (U6)")
print("=" * 60)
popup_3d_path = os.path.join(INTEGRATED, "popup_3d.py")
if os.path.exists(popup_3d_path):
    content = open(popup_3d_path, encoding='utf-8').read()
    bad_import = 'from PyQt6.QtOpenGL import GL'
    if bad_import in content:
        print(f"  ❌ '{bad_import}' 여전히 존재! (크래시 원인)")
    else:
        print(f"  ✅ 문제 import 제거됨")
    
    # Check for correct OpenGL import
    if 'from OpenGL.GL import' in content or 'import OpenGL' in content:
        print(f"  ✅ OpenGL.GL import 존재")
    else:
        print(f"  ⚠️ OpenGL import 확인 필요")
else:
    print("  ❌ popup_3d.py 파일 없음!")

print()
print("=" * 60)
print("STEP 1-F: Agent 05 ELEMENT_COLORS / CPK 색상 확인 (U7)")
print("=" * 60)
renderer_path = os.path.join(INTEGRATED, "renderer.py")
if os.path.exists(renderer_path):
    content = open(renderer_path, encoding='utf-8').read()
    if 'ELEMENT_COLORS' in content:
        print("  ✅ ELEMENT_COLORS 딕셔너리 존재")
    else:
        print("  ❌ ELEMENT_COLORS 없음!")
    
    if 'get_element_color' in content:
        print("  ✅ get_element_color() 함수 존재")
    else:
        print("  ⚠️ get_element_color() 없음")
    
    if 'save()' in content and 'restore()' in content:
        print("  ✅ painter save()/restore() 존재")
    else:
        print("  ⚠️ painter save()/restore() 미확인")
else:
    print("  ❌ renderer.py 파일 없음!")

print()
print("=" * 60)
print("STEP 1-G: Agent 01 툴바/btn_3d 확인")
print("=" * 60)
for fname in ['main_window.py', 'toolbar_setup.py', 'draw.py']:
    fpath = os.path.join(INTEGRATED, fname)
    if os.path.exists(fpath):
        content = open(fpath, encoding='utf-8').read()
        checks = {
            'addToolBarBreak': '툴바 2줄 분리',
            'btn_3d': '3D 버튼',
            'setEnabled': '비활성화 로직',
            'arrow_action': '반응 화살표',
            'text_action': '텍스트 도구',
        }
        found = []
        for key, desc in checks.items():
            if key in content:
                found.append(desc)
        if found:
            print(f"  📄 {fname}: {', '.join(found)}")
        else:
            print(f"  📄 {fname}: 관련 코드 없음")
    else:
        print(f"  ❌ {fname} 없음")

print()
print("=" * 60)
print("STEP 1-H: Agent 02 canvas.py 신규 기능 확인")
print("=" * 60)
canvas_path = os.path.join(INTEGRATED, "canvas.py")
if os.path.exists(canvas_path):
    content = open(canvas_path, encoding='utf-8').read()
    features = {
        'arrows': '반응 화살표 데이터',
        'text_boxes': '텍스트 상자 데이터',
        'charge': '+/- charge 필드',
        'molecule_selected': 'molecule_selected 시그널',
        '_render_subscript': '아래첨자 변환',
        'user_lp': '비공유전자쌍 플래그',
        'selected_molecule': '선택 도구',
    }
    for key, desc in features.items():
        if key in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ {desc} 없음!")
else:
    print("  ❌ canvas.py 없음!")

print()
print("=" * 60)
print("STEP 1-I: Agent 05 공명 균등화 / LP 제외 확인")
print("=" * 60)
if os.path.exists(renderer_path):
    content = open(renderer_path, encoding='utf-8').read()
    if 'avg_charge' in content or 'ring_atoms' in content or '평균' in content or 'equalize' in content.lower():
        print("  ✅ 공명 전자구름 균등화 로직 존재")
    else:
        print("  ❌ 공명 균등화 로직 미발견")
    
    if 'user_lp' in content or 'LP' in content:
        print("  ✅ LP 관련 로직 존재")
    else:
        print("  ❌ user_lp/LP 처리 없음")

print()
print("=" * 60)
print("STEP 1-J: 포터블 경로 위반 검사")
print("=" * 60)
violations = 0
for f in sorted(os.listdir(INTEGRATED)):
    if f.endswith('.py'):
        path = os.path.join(INTEGRATED, f)
        content = open(path, encoding='utf-8').read()
        # Check for hardcoded absolute paths
        patterns = [
            r'[A-Z]:\\Users\\',
            r'[A-Z]:\\chemgrid\\',
            r'[A-Z]:\\ProgramData\\',
            r'r"[A-Z]:\\',
        ]
        for pat in patterns:
            matches = re.findall(pat, content)
            if matches:
                for m in matches:
                    print(f"  ⚠️ {f}: 절대경로 → {m}")
                    violations += 1
if violations == 0:
    print("  ✅ 절대 경로 위반 0건")
else:
    print(f"  ❌ 절대 경로 위반 {violations}건")

print()
print("=" * 60)
print("📋 사전 비행 검증 완료")
print("=" * 60)
