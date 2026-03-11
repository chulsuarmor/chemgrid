# ChemGrid YOLO Automation & Verification Guide

이 파일은 12종 분자에 대한 자동화된 드로잉, PDF 내보내기, 그리고 AI 검증을 수행하는 방법을 설명합니다.

## 1. 실행 방법

터미널(PowerShell 또는 CMD)에서 다음 배치 파일을 실행하십시오:

```cmd
.\run_yolo.bat
```

## 2. 수행되는 작업 (YOLO Process)

1.  **자동 드로잉 (Drawing Loop):**
    -   12종 분자(Benzene ~ Tropylium Cation)를 순차적으로 캔버스에 그립니다.
    -   각 분자마다 `Lewis` 및 `Theory` 구조를 고해상도 벡터 PDF로 내보냅니다.
    -   특정 분자를 선택(Select)하여 `IUPAC` 이름이 포함된 PDF를 조건부로 생성합니다.

2.  **분광학 리포트 생성 (Spectroscopy):**
    -   각 분자에 대해 고유한 IR, NMR, UV-Vis 데이터를 기반으로 리포트를 생성합니다.
    -   그래프 내부에 "AI Insight (Overlay)" 박스가 추가되어 시각적 설명을 제공합니다.

3.  **자동 검증 (Verification):**
    -   `_verify_pdf_content.py` 스크립트가 자동으로 실행됩니다.
    -   생성된 모든 PDF 파일의 존재 여부를 체크합니다.
    -   PDF 내부 텍스트를 분석하여 분자 이름이 정확한지, 중복된 내용이 없는지 검사합니다.
    -   검증 결과는 터미널에 `PASS` 또는 `FAIL`로 출력됩니다.

## 3. 문제 해결

만약 실행 중 오류가 발생하거나 파일이 생성되지 않는다면, 다음을 확인하십시오:
-   `PyQt6`와 `reportlab` 라이브러리가 설치되어 있어야 합니다. (`pip install PyQt6 reportlab`)
-   GUI 환경(모니터 연결)이 필요합니다. (Headless 서버에서는 작동하지 않을 수 있습니다.)
