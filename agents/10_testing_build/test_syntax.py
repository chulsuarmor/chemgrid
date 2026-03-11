#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""코드 문법 검증 스크립트"""

import py_compile
import sys
from pathlib import Path

def test_syntax(file_path):
    """파일의 Python 문법 검증"""
    try:
        py_compile.compile(str(file_path), doraise=True)
        return True, "✓ 문법 정상"
    except py_compile.PyCompileError as e:
        return False, f"✗ 문법 오류: {e}"

def main():
    files_to_check = [
        "draw.py",
        "layer_logic.py",
        "export_manager_enhanced.py",
    ]
    
    print("[ChemDraw Pro 코드 검증]\n")
    
    all_ok = True
    for filename in files_to_check:
        filepath = Path(filename)
        if filepath.exists():
            ok, msg = test_syntax(filepath)
            print(f"{msg}: {filename}")
            if not ok:
                all_ok = False
        else:
            print(f"⊘ 파일 없음: {filename}")
            all_ok = False
    
    print("\n" + "="*50)
    if all_ok:
        print("✅ 모든 파일 문법 검증 완료!")
        return 0
    else:
        print("⚠️ 일부 파일에 문법 오류가 있습니다.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
