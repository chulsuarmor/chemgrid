"""
4대 핵심 과제 수정 검증 스크립트
실제 코드를 읽어서 수정이 적용되었는지 확인
"""

import re

def verify_fix(file_path, line_num, expected_text, fix_name):
    """특정 라인에 예상 텍스트가 있는지 확인"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if line_num <= len(lines):
                actual = lines[line_num - 1].strip()
                if expected_text in actual:
                    print(f"✓ {fix_name}: PASS")
                    print(f"  Line {line_num}: {actual}")
                    return True
                else:
                    print(f"✗ {fix_name}: FAIL")
                    print(f"  Expected: {expected_text}")
                    print(f"  Actual:   {actual}")
                    return False
            else:
                print(f"✗ {fix_name}: FAIL (file too short)")
                return False
    except Exception as e:
        print(f"✗ {fix_name}: ERROR - {e}")
        return False

def verify_toolbar_separation(file_path):
    """tb2에 버튼들이 추가되었는지 확인"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # tb2에 추가되어야 할 버튼들
        required_patterns = [
            r'self\.tb2\.addAction\(file_btn\)',      # 파일 버튼
            r'self\.tb2\.addAction\(export_btn\)',    # 내보내기 버튼
            r'self\.tb2\.addAction.*전체 지우기',     # 전체 지우기
            r'self\.tb2\.addAction.*원소 선택',       # 원소 선택
            r'self\.tb2\.addAction\(self\.btn_comparator\)',  # 분자 비교
            r'self\.tb2\.addAction\(self\.btn_history\)',     # 계산 히스토리
            r'self\.tb2\.addAction\(self\.btn_batch\)',       # 배치 처리
        ]

        found = []
        missing = []

        for pattern in required_patterns:
            if re.search(pattern, content):
                found.append(pattern)
            else:
                missing.append(pattern)

        print(f"\n✓ 2단 툴바 검증: {len(found)}/{len(required_patterns)} 버튼 확인됨")

        if missing:
            print("  ✗ 누락된 패턴:")
            for p in missing:
                print(f"    - {p}")
            return False
        else:
            print("  ✓ 모든 텍스트 버튼이 tb2로 이동됨")
            return True

    except Exception as e:
        print(f"✗ 2단 툴바 검증 ERROR: {e}")
        return False

def main():
    print("=" * 60)
    print("4대 핵심 과제 수정 검증 시작")
    print("=" * 60)

    draw_py = "_source/draw.py"
    renderer_py = "_source/renderer.py"

    results = []

    # Fix 1: 뷰포트 동기화 (draw.py:1770-1771)
    print("\n[Fix 1] 뷰포트 동기화 검증:")
    results.append(verify_fix(
        draw_py, 1770,
        "prev_scale = self.cv.scale_factor",
        "Viewport scale preservation"
    ))
    results.append(verify_fix(
        draw_py, 1771,
        "prev_offset = QPointF(self.cv.pan_offset)",
        "Viewport offset preservation"
    ))
    results.append(verify_fix(
        draw_py, 1776,
        "self.cv.scale_factor = prev_scale",
        "Viewport scale restoration"
    ))
    results.append(verify_fix(
        draw_py, 1777,
        "self.cv.pan_offset = prev_offset",
        "Viewport offset restoration"
    ))

    # Fix 2: 이중 결합 간격 증가 (draw.py:1491)
    print("\n[Fix 2] 이중 결합 간격 증가 검증:")
    results.append(verify_fix(
        draw_py, 1491,
        "off = 7",
        "Double bond spacing (4→7 pixels)"
    ))

    # Fix 3: 전자구름 반경 확대 (renderer.py:380)
    print("\n[Fix 3] 전자구름 반경 확대 검증:")
    results.append(verify_fix(
        renderer_py, 380,
        "max_cloud_radius = avg_bond_length * 0.45",
        "Electron cloud radius (0.25→0.45x)"
    ))

    # Fix 4: 2단 툴바 구조 (draw.py:1589-1591 + button moves)
    print("\n[Fix 4] 2단 툴바 구조 검증:")
    results.append(verify_fix(
        draw_py, 1589,
        "self.tb2 = QToolBar()",
        "Second toolbar creation"
    ))
    results.append(verify_fix(
        draw_py, 1590,
        "self.tb2.setMinimumHeight(40)",
        "Second toolbar height"
    ))

    # 2단 툴바 버튼 분리 검증
    results.append(verify_toolbar_separation(draw_py))

    # 최종 결과
    print("\n" + "=" * 60)
    print("최종 검증 결과")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"통과: {passed}/{total} 검사")

    if passed == total:
        print("\n✓✓✓ 모든 수정사항이 정상적으로 적용되었습니다! ✓✓✓")
        print("\n다음 명령어로 프로그램을 실행하세요:")
        print("  python _source/draw.py")
        print("\n또는 ChemGrid.exe를 빌드하세요:")
        print("  build_chemgrid.bat")
        return 0
    else:
        print(f"\n✗ {total - passed}개 검사 실패")
        print("4_CORE_FIXES_COMPLETE.md 파일을 참조하여 수정하세요.")
        return 1

if __name__ == "__main__":
    exit(main())
