# build_chemgrid.py (v2.0 — ChemGrid PyInstaller Builder)
"""
ChemGrid.exe 빌드 스크립트
- integrated/ 폴더에서 실행
- 모든 리소스(.png, .ico, .chem) 번들링
- 포터블 경로 시스템 호환
"""
import subprocess
import sys
import os
from pathlib import Path

def build_chemgrid_exe():
    """Build ChemGrid.exe using PyInstaller"""
    
    project_root = Path(__file__).parent
    draw_script = project_root / "draw.py"
    icon_path = project_root / "logo.ico"
    
    print("=" * 60)
    print("ChemGrid Executable Builder (Phase 6-3)")
    print("=" * 60)
    
    # 1. 필수 파일 확인
    print("\n[1/4] 필수 파일 확인...")
    
    if not draw_script.exists():
        print(f"  ❌ draw.py 없음: {draw_script}")
        return False
    print(f"  ✅ draw.py")
    
    if icon_path.exists():
        print(f"  ✅ logo.ico")
    else:
        print(f"  ⚠️  logo.ico 없음 — 아이콘 없이 빌드")
        icon_path = None
    
    # Python 파일 목록
    py_files = sorted([f for f in os.listdir(project_root) if f.endswith('.py') and f != 'build_chemgrid.py'])
    print(f"  📦 Python 모듈: {len(py_files)}개")
    
    # 리소스 파일 목록
    resource_exts = {'.png', '.ico', '.chem'}
    resources = [f for f in os.listdir(project_root) if Path(f).suffix in resource_exts]
    print(f"  🎨 리소스: {len(resources)}개")
    
    # 2. PyInstaller 확인
    print("\n[2/4] PyInstaller 확인...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  ✅ PyInstaller {result.stdout.strip()}")
        else:
            print("  ❌ PyInstaller 미설치")
            print("  → pip install pyinstaller")
            return False
    except Exception as e:
        print(f"  ❌ PyInstaller 확인 실패: {e}")
        return False
    
    # 3. PyInstaller 명령 구성
    print("\n[3/4] 빌드 중...")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "ChemGrid",
        "--distpath", str(project_root / "dist"),
        "--workpath", str(project_root / "build"),
        "--specpath", str(project_root),
    ]
    
    # 아이콘
    if icon_path and icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    
    # 리소스 데이터 파일 번들링 (--add-data src;dst)
    for res in resources:
        res_path = project_root / res
        if res_path.exists():
            cmd.extend(["--add-data", f"{res_path};."])
    
    # orca_history 폴더 (빈 폴더라도)
    orca_hist = project_root / "orca_history"
    if orca_hist.exists():
        cmd.extend(["--add-data", f"{orca_hist};orca_history"])
    
    # Hidden imports
    hidden_imports = [
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtSvg",
        "PyQt6.QtOpenGLWidgets",
        "OpenGL",
        "OpenGL.GL",
        "OpenGL.GLU",
        "matplotlib",
        "matplotlib.backends.backend_qtagg",
        "numpy",
        "scipy",
        "networkx",
        "rdkit",
        "rdkit.Chem",
        "requests",
    ]
    
    for hi in hidden_imports:
        cmd.extend(["--hidden-import", hi])
    
    # 메인 스크립트
    cmd.append(str(draw_script))
    
    print(f"  명령: pyinstaller --onefile --windowed --name ChemGrid ...")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )
        
        # 출력 표시
        if result.stdout:
            # 마지막 20줄만 출력
            lines = result.stdout.strip().split('\n')
            for line in lines[-20:]:
                print(f"  {line}")
        
        if result.returncode != 0:
            print(f"\n  ❌ 빌드 실패 (exit code: {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split('\n')[-10:]:
                    print(f"  ERR: {line}")
            return False
        
    except subprocess.TimeoutExpired:
        print("  ❌ 빌드 타임아웃 (10분 초과)")
        return False
    except Exception as e:
        print(f"  ❌ 빌드 오류: {e}")
        return False
    
    # 4. 결과 확인
    print("\n[4/4] 빌드 결과 확인...")
    
    exe_path = project_root / "dist" / "ChemGrid.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ ChemGrid.exe 빌드 성공!")
        print(f"  📁 경로: {exe_path}")
        print(f"  📏 크기: {size_mb:.1f} MB")
        
        # 프로젝트 루트로 복사
        root_exe = Path(r"c:\chemgrid\ChemGrid.exe")
        try:
            import shutil
            shutil.copy2(exe_path, root_exe)
            print(f"  📋 루트 복사: {root_exe}")
        except Exception as e:
            print(f"  ⚠️  루트 복사 실패: {e}")
        
        return True
    else:
        print("  ❌ ChemGrid.exe 미생성")
        return False


if __name__ == "__main__":
    # PyInstaller 설치 확인
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller 미설치. 설치 중...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    success = build_chemgrid_exe()
    
    if success:
        print("\n" + "=" * 60)
        print("🟢 BUILD COMPLETE — ChemGrid.exe 사용 가능")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("🔴 BUILD FAILED")
        print("=" * 60)
        sys.exit(1)
