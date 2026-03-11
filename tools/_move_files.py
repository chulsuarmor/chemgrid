#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일 재구성 스크립트"""

import os
import shutil
from pathlib import Path

def move_files_to_source():
    """모든 소스 파일을 _source/ 폴더로 이동"""
    
    root_dir = Path(os.getcwd())
    source_dir = root_dir / "_source"
    
    # 이동할 파일 패턴
    patterns_to_move = [
        '*.py',      # Python 파일
        '*.png',     # 이미지 파일
        '*.ico',     # 아이콘 파일
        '*.json',    # JSON 설정 파일
        '*.chem',    # 분자 파일
    ]
    
    # 문서 파일은 따로 처리
    doc_patterns = ['*.md', '*.txt']
    
    # 제외할 파일들
    exclude_files = {
        'ChemDraw.spec',
        '_move_files.py',  # 이 스크립트 자체는 제외
    }
    
    # 제외할 폴더들
    exclude_dirs = {
        '_backup_before_reorganize',
        '_source',
        'dist',
        'build',
        '__pycache__',
        'Orca.6.1.1',
        'orca_extracted',
        'AvogadroOrca4.1'
    }
    
    files_moved = 0
    
    # 1. Python, 이미지, 설정 파일 이동
    for pattern in patterns_to_move:
        for file_path in root_dir.glob(pattern):
            if file_path.is_file() and file_path.name not in exclude_files:
                try:
                    dest = source_dir / file_path.name
                    shutil.move(str(file_path), str(dest))
                    print(f"✓ Moved: {file_path.name}")
                    files_moved += 1
                except Exception as e:
                    print(f"✗ Failed to move {file_path.name}: {e}")
    
    # 2. 문서 파일도 이동 (선택적)
    for pattern in doc_patterns:
        for file_path in root_dir.glob(pattern):
            if file_path.is_file() and file_path.name not in exclude_files:
                # 일부 주요 문서만 이동 (예: 프로젝트 설정 관련)
                if any(x in file_path.name for x in ['PHASE', 'STEP', 'IMPLEMENTATION', 'VALIDATION']):
                    try:
                        dest = source_dir / file_path.name
                        shutil.move(str(file_path), str(dest))
                        print(f"✓ Moved: {file_path.name}")
                        files_moved += 1
                    except Exception as e:
                        print(f"✗ Failed to move {file_path.name}: {e}")
    
    print(f"\n[완료] {files_moved}개 파일을 _source/로 이동했습니다.")
    
    # 3. ChemDraw.exe 복사 (dist/에서 루트로)
    exe_src = root_dir / "dist" / "ChemDraw.exe"
    exe_dst = root_dir / "ChemDraw.exe"
    
    if exe_src.exists() and not exe_dst.exists():
        try:
            shutil.copy2(str(exe_src), str(exe_dst))
            print(f"✓ Copied: ChemDraw.exe to root directory")
        except Exception as e:
            print(f"✗ Failed to copy ChemDraw.exe: {e}")
    elif exe_dst.exists():
        print(f"⊘ ChemDraw.exe already exists in root")
    else:
        print(f"✗ ChemDraw.exe not found in dist/")
    
    print("\n[폴더 구조 변경 완료]")
    print("루트 디렉토리: ChemDraw.exe")
    print("_source/ 디렉토리: 모든 소스 파일")


if __name__ == "__main__":
    os.chdir("C:\\Users\\김남헌\\Desktop\\organicdraw")
    move_files_to_source()
    print("\n스크립트 실행 완료.")
