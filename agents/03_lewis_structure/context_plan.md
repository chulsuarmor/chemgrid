# 📋 Local Domain Plan: 03_lewis_structure
## PDF 구조 이미지 누락 및 렌더링 디버깅

### 1. 세부 구현 목표
- [ ] 현재 생성된 `Theoretical_Structures_All.pdf` 내에 분자 이름만 있고 이미지가 없는 치명적 오류 조사.
- [ ] 2D 구조 벡터(SVG/PNG) 생성 시 사용되는 `canvas` 렌더링 호출 유효성 검사.
- [ ] 개별 분자별 이미지 추출 및 `agents/09_data_export`가 사용할 수 있는 스토리지 경로 확보.

### 2. 마일스톤
- Phase 1: PDF 생성 라이브러리(ReportLab/PyPDF2 등) 호출부 전수 조사 및 이미지 데이터 인라인 여부 확인.
- Phase 2: 이미지 렌더링 버퍼 처리 최적화 (데이터가 휘발되는 현상 방지).
- Phase 3: 수정된 이론적 구조 PDF 재발행 및 무결성 검증.

> **상태:** [승인 완료] - 정밀 분석 시작하십시오.
