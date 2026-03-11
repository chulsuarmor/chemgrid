# Lewis Structure PDF Export & Verification Plan

## 1. Objective
Implement a robust system to:
1.  Convert `.chem` files (containing molecular structures) into Lewis structures.
2.  Export these Lewis structures as high-quality PDF files.
3.  Verify that the exported PDFs correctly represent Lewis structures (checking for electron pairs, formal charges, bond orders).

## 2. Current Status
-   **Blocked**: Previous attempts to create directories and run verification scripts failed due to Windows command-line syntax incompatibilities (e.g., `&&` operator issues, `mkdir` argument handling).
-   **Action Required**: Switch to Python-based automation for all file system operations to ensure cross-platform compatibility and robustness.

## 3. Implementation Plan (Resumption Guide)

### Phase 1: Environment Setup (Robust)
-   Create a safe directory structure using Python's `pathlib`.
-   Target Directories:
    -   `_source/lewis_structures/`
    -   `_source/lewis_structures/pdf/`
    -   `_source/lewis_structures/verification/`

### Phase 2: Conversion Logic (`_convert_lewis.py`)
-   **Input**: `.chem` files from `_source/`.
-   **Process**:
    -   Parse `.chem` to extract connectivity/SMILES.
    -   Use `rdkit.Chem` to generate Lewis structure layout (calculate formal charges, lone pairs).
    -   Validate Lewis rules (octet rule check) *before* export.
-   **Output**: PDF file in `_source/lewis_structures/pdf/`.

### Phase 3: Verification Logic (`_verify_lewis.py`)
-   **Input**: Generated PDF files.
-   **Process**:
    -   Extract vector data/text from PDF (if possible) or use computer vision (OpenCV) on rasterized PDF.
    -   **Criteria**:
        -   Is "LewisStructure" metadata/watermark present?
        -   Are lone pairs visible (dots/lines)?
        -   Do bond angles match VSEPR theory (within tolerance)?
-   **Output**: JSON report in `_source/lewis_structures/verification/`.

## 4. Error Analysis & Solution

### Root Cause of Failure
-   **Issue**: Using shell-specific commands (like chained `mkdir` with `&&`) in a Windows environment caused syntax errors.
-   **Symptom**: "The token '&&' is not a valid statement separator in this version."
-   **Impact**: Directory creation failed, blocking subsequent file generation.

### Solution Strategy
-   **Protocol**: **Always use Python scripts for file system operations** instead of shell commands.
-   **Code Pattern**:
    ```python
    from pathlib import Path
    import os

    def safe_mkdir(path_str):
        try:
            p = Path(path_str)
            p.mkdir(parents=True, exist_ok=True)
            print(f"Verified: {p}")
        except Exception as e:
            print(f"Error creating {p}: {e}")
    ```
-   **Prevention**: Do not rely on `os.system` with complex shell syntax. Use `subprocess` with explicit arguments if CLI tools are needed.

## 5. Next Steps
1.  Run `_robust_lewis_setup.py` to fix directory structure.
2.  Implement `_convert_lewis.py` using RDKit.
3.  Implement `_verify_lewis.py` for validation.
