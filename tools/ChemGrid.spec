# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['../src/app/draw.py'],
    pathex=['../src/app'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'rdkit',
        'rdkit.Chem',
        'rdkit.Chem.AllChem',
        'rdkit.Chem.Descriptors',
        'rdkit.Chem.rdMolDescriptors',
        'rdkit.Chem.rdDepictor',
        'rdkit.Chem.rdmolops',
        'scipy',
        'scipy.spatial',
        'numpy',
        'matplotlib',
        'matplotlib.backends.backend_qtagg',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtPrintSupport',
        'PyQt6.QtSvg',
        'PyQt6.QtOpenGLWidgets',
        'OpenGL',
        'OpenGL.GL',
        'OpenGL.GLU',
        'networkx',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # --- ML/DL ライブラリ (src/app/ 미사용 — M1371 audit) ---
        # torch ROCm build 1164 MB — draw.py/src/app/*.py 어디에도 import 없음
        'torch',
        'torchvision',     # 9 MB — torch 의존
        'torchaudio',      # 3 MB — torch 의존
        'torchsde',        # sinktank 전용
        # transformers 86 MB — src/app/ 미사용, sinktank/housing 전용
        'transformers',
        # accelerate 3 MB — HuggingFace 학습 루프, 프로덕션 미사용
        'accelerate',
        # bitsandbytes — QDLORA 양자화, 프로덕션 미사용 (설치 여부 무관)
        'bitsandbytes',
        # --- dev-only (pytest/lint/format) ---
        'pytest',          # 테스트 프레임워크 — 배포본 불필요
        'black',           # 코드 포매터 — 배포본 불필요
        'ruff',            # 린터 — 배포본 불필요
        'mypy',            # 타입 체커 — 배포본 불필요
        # --- Jupyter/IPython (src/app/iupac_analyzer.py try/except로 감싸져 있음) ---
        'IPython',
        'jupyter',
        'notebook',
        'ipykernel',
        'ipywidgets',
        'nbformat',
        'nbconvert',
        # --- sinktank/housing 전용 대용량 — src/app/ 미사용 ---
        # pyarrow 84 MB — datasets/HuggingFace 파이프라인 전용
        'pyarrow',
        # selenium 26 MB — 브라우저 자동화, 배포본 불필요
        'selenium',
        # grpcio 12 MB — gRPC 서비스, 배포본 미사용
        'grpcio',
        'grpcio_status',
        # kornia 7 MB — 이미지 변환 CV, 배포본 미사용
        'kornia',
        # scikit-learn 39 MB — sinktank ML, src/app/ 미사용
        'sklearn',
        # scikit-image 23 MB — 이미지 처리, src/app/ 미사용
        'skimage',
        # av 4 MB — PyAV 비디오, 배포본 불필요
        'av',
        # diffsynth 2 MB — Stable Diffusion, 완전 무관
        'diffsynth',
        # comfyui 계열 — 화학 앱 완전 무관
        'comfy',
        'comfy_extras',
        # yt_dlp — 미디어 다운로더, 배포본 불필요
        'yt_dlp',
        # cv2 (opencv) — src/app/ 미사용
        'cv2',
        # sphinx — 문서 생성기, 배포본 불필요
        'sphinx',
        # tkinter — PyQt6 앱이므로 불필요
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ChemGrid',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
