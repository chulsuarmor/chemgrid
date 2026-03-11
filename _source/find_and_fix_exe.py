#!/usr/bin/env python3
"""
ChemDraw.exe 위치 확인 및 파일명/로고 수정
"""

import os
import shutil
from pathlib import Path

workspace = Path(r"C:\Users\김남헌\Desktop\organicdraw")

print("=" * 70)
print("ChemDraw.exe 파일 찾기 및 수정")
print("=" * 70)

# 모든 .exe 파일 검색
print("\n🔍 organicdraw 폴더 내 모든 .exe 파일 검색...\n")

exe_files = list(workspace.glob("*.exe"))
dist_exe_files = list((workspace / "dist").glob("*.exe")) if (workspace / "dist").exists() else []

print(f"📁 organicdraw/: {len(exe_files)}개 파일")
for f in exe_files:
    size = f.stat().st_size
    print(f"   - {f.name} ({size:,} bytes)")

if dist_exe_files:
    print(f"\n📁 organicdraw/dist/: {len(dist_exe_files)}개 파일")
    for f in dist_exe_files:
        size = f.stat().st_size
        print(f"   - {f.name} ({size:,} bytes)")
else:
    print(f"\n📁 organicdraw/dist/: 폴더 없거나 exe 파일 없음")

# dist/ChemDraw.exe를 organicdraw/ChemDraw.exe로 복사
if dist_exe_files:
    print("\n" + "=" * 70)
    print("✅ dist 폴더에 exe 파일 발견!")
    print("=" * 70)
    
    source = dist_exe_files[0]  # 첫 번째 exe
    target = workspace / "ChemDraw.exe"
    
    print(f"\n복사 중...")
    print(f"원본: {source}")
    print(f"대상: {target}")
    
    try:
        shutil.copy2(source, target)
        print(f"\n✅ 복사 완료!")
        print(f"\n🎉 ChemDraw.exe가 organicdraw 폴더에 배치되었습니다!")
        print(f"   위치: {target}")
        print(f"   크기: {target.stat().st_size:,} bytes")
        print(f"\n🚀 사용법: ChemDraw.exe를 더블클릭하면 프로그램 실행됩니다.")
    except Exception as e:
        print(f"\n❌ 복사 실패: {e}")
else:
    print("\n" + "=" * 70)
    print("❌ dist 폴더에 exe 파일이 없습니다!")
    print("=" * 70)
    
    print("\n다음 명령어를 Anaconda Prompt에서 실행하세요:\n")
    print("─" * 70)
    print("cd C:\\Users\\김남헌\\Desktop\\organicdraw")
    print("pyinstaller --onefile --windowed --icon=logo.ico --name=ChemDraw draw.py")
    print("─" * 70)
    print("\n또는 더 간단하게:\n")
    print("─" * 70)
    print("python build_exe.py --clean")
    print("─" * 70)

print("\n" + "=" * 70)
