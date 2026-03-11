#!/usr/bin/env python3
"""
ChemDraw.exe 검증 및 생성 스크립트
logo.png가 포함된 ChemDraw.exe 파일 생성
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

workspace = Path(r"C:\Users\김남헌\Desktop\organicdraw")

print("=" * 70)
print("ChemDraw.exe 검증 및 생성")
print("=" * 70)

# 1. logo.png 확인
logo_path = workspace / "logo.png"
print(f"\n1️⃣ logo.png 확인: {logo_path}")
if logo_path.exists():
    size = logo_path.stat().st_size
    print(f"   ✅ 존재 (크기: {size:,} bytes)")
else:
    print(f"   ❌ 없음 - 기본 로고 생성 필요")

# 2. ChemDraw.exe (organicdraw 폴더) 확인
exe_path = workspace / "ChemDraw.exe"
print(f"\n2️⃣ ChemDraw.exe 확인: {exe_path}")
if exe_path.exists():
    size = exe_path.stat().st_size
    print(f"   ✅ 존재 (크기: {size:,} bytes)")
    print("   → 이미 배포 가능한 상태입니다!")
else:
    print(f"   ❌ 없음 - 지금부터 생성합니다...")

# 3. dist 폴더 확인
dist_path = workspace / "dist"
dist_exe = dist_path / "ChemDraw.exe" if dist_path.exists() else None

print(f"\n3️⃣ dist 폴더 확인: {dist_path}")
if dist_path.exists():
    if dist_exe and dist_exe.exists():
        size = dist_exe.stat().st_size
        print(f"   ✅ dist/ChemDraw.exe 존재 (크기: {size:,} bytes)")
    else:
        print(f"   ⚠️ dist 폴더는 있지만 ChemDraw.exe 없음")
else:
    print(f"   ❌ dist 폴더 없음")

# 4. build_exe.py 확인
build_script = workspace / "build_exe.py"
print(f"\n4️⃣ build_exe.py 확인: {build_script}")
if build_script.exists():
    print(f"   ✅ 존재")
else:
    print(f"   ❌ 없음")

# 5. draw.py 확인
draw_py = workspace / "draw.py"
print(f"\n5️⃣ draw.py 확인: {draw_py}")
if draw_py.exists():
    size = draw_py.stat().st_size
    print(f"   ✅ 존재 (크기: {size:,} bytes)")
else:
    print(f"   ❌ 없음 - 컴파일 불가")

print("\n" + "=" * 70)

# 결론 및 실행
if exe_path.exists():
    print("\n✅ 최종 결론: ChemDraw.exe가 organicdraw 폴더에 존재합니다!")
    print("   이미 배포 가능한 상태입니다.")
    print("\n🚀 사용 방법: ChemDraw.exe를 더블클릭하면 프로그램 실행됩니다.")
    sys.exit(0)
else:
    print("\n❌ 최종 결론: ChemDraw.exe가 organicdraw 폴더에 없습니다.")
    print("   지금부터 PyInstaller로 생성합니다...\n")
    
    # dist/ChemDraw.exe가 있으면 copy
    if dist_exe and dist_exe.exists():
        print(f"📋 dist/ChemDraw.exe를 organicdraw 폴더로 복사 중...")
        try:
            shutil.copy(dist_exe, exe_path)
            print(f"✅ 복사 완료: {exe_path}")
            sys.exit(0)
        except Exception as e:
            print(f"❌ 복사 실패: {e}")
            print("   PyInstaller로 새로 생성하겠습니다...")
    
    # PyInstaller로 새로 생성
    print("\n🔨 PyInstaller로 ChemDraw.exe 생성 중...")
    print("   (시간이 약 1-2분 소요될 수 있습니다)\n")
    
    try:
        # PyInstaller 명령어 구성
        cmd = [
            "pyinstaller",
            "--onefile",
            "--windowed",
            f"--icon={workspace / 'logo.ico'}",
            f"--name=ChemDraw",
            f"--distpath={workspace}",
            f"--buildpath={workspace / 'build'}",
            f"--specpath={workspace}",
            str(draw_py)
        ]
        
        # PyInstaller 실행
        result = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ PyInstaller 성공!")
            
            # dist/ChemDraw.exe → organicdraw/ChemDraw.exe 복사
            if (workspace / "ChemDraw.exe").exists():
                print(f"✅ ChemDraw.exe 생성 완료: {exe_path}")
                size = exe_path.stat().st_size
                print(f"   파일 크기: {size:,} bytes")
                print("\n🚀 사용 방법: ChemDraw.exe를 더블클릭하면 프로그램 실행됩니다!")
            else:
                print("❌ ChemDraw.exe가 예상 위치에 없습니다.")
                print(f"stdout: {result.stdout}")
                print(f"stderr: {result.stderr}")
        else:
            print(f"❌ PyInstaller 실패 (코드: {result.returncode})")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ PyInstaller가 설치되지 않았습니다.")
        print("   설치: pip install pyinstaller")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

print("\n" + "=" * 70)
