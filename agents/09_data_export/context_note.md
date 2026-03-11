# 📝 📦 데이터/내보내기 — Technical Notes
## 기술적 판단 및 결정 기록

---

## [2026-02-28] 업무 구조 분석 완료

### 1. 모듈 계층 구조

```
[사용자 입력]
     │
     ▼
┌─────────────────┐     ┌──────────────────┐
│ smiles_validator │────▶│  iupac_analyzer  │
│  (SMILES 검증)  │     │ (IUPAC명명/입체) │
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────────┐     ┌──────────────────────┐
│ molecule_comparator  │     │   batch_processor    │
│ (분자 비교/유사도)   │     │ (배치 ORCA 계산)     │
└─────────────────────┘     └──────────┬───────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │  calculation_logger   │ ◀── 중복!
                            │  (계산 기록/해시검증) │
                            ├──────────────────────┤
                            │   history_manager     │ ◀── 중복!
                            │  (히스토리/캐시/검색) │
                            └──────────┬───────────┘
                                       │
                                       ▼
                    ┌────────────────────────────────────┐
                    │      export_manager_enhanced       │
                    │  (PNG/PDF/SVG 구조 내보내기)       │
                    ├────────────────────────────────────┤
                    │     spectrum_pdf_exporter          │
                    │  (분광 스펙트럼 학술 PDF 보고서)   │
                    └────────────────────────────────────┘
                                       │
                            ┌──────────┴──────────┐
                            │    error_handler     │
                            │ (전 모듈 공통 에러)  │
                            └─────────────────────┘
```

### 2. 발견된 문제점

| # | 문제 | 상세 | 우선순위 |
|---|------|------|----------|
| 1 | **`CalculationEntry` 클래스 중복** | `calculation_logger.py`와 `history_manager.py`에 각각 정의. 필드/메서드 불일치 | 🔴 높음 |
| 2 | **draw.py 미연동** | 9개 모듈 모두 독립 존재. 메인 앱에서 import/호출하는 코드 없음 | 🟡 중간 |
| 3 | **spectrum_pdf_exporter 버그** | `SpectrumSelectionDialog.init_ui()`에서 `QListWidget()`을 `item`으로 사용 — `QListWidgetItem()`이어야 함 | 🔴 높음 |
| 4 | **error_handler 로그 경로** | `Path.cwd()` 사용 → 포터블 경로 규칙 위반 (`__file__` 기반이어야 함) | 🟡 중간 |
| 5 | **history_manager 경로** | `"./orca_history"` 하드코딩 → 포터블 경로 위반 | 🟡 중간 |
| 6 | **calculation_logger 경로** | `Path.cwd()` 사용 → 포터블 경로 위반 | 🟡 중간 |
| 7 | **export_manager의 _paint_selection** | canvas 렌더러를 직접 호출하지 않고 자체 구현 → 실제 렌더링과 불일치 가능 | 🟡 중간 |
| 8 | **iupac_analyzer 불안정** | `Chem.rdMolTransforms.ComputeGasteigerCharges` 잘못된 위치에서 호출 | 🟡 중간 |

### 3. 모듈별 의존성

| 모듈 | PyQt6 | RDKit | reportlab | matplotlib | 순수 Python |
|------|-------|-------|-----------|------------|-------------|
| smiles_validator | ❌ | ✅ | ❌ | ❌ | ✅ |
| iupac_analyzer | ✅ (QThread) | ✅ | ❌ | ❌ | ✅ |
| molecule_comparator | ✅ (QThread, QPainter) | ✅ | ❌ | ❌ | ✅ |
| calculation_logger | ❌ | ❌ | ❌ | ❌ | ✅ |
| history_manager | ❌ | ❌ | ❌ | ❌ | ✅ |
| batch_processor | ✅ (QThread, QObject) | ❌ | ❌ | ❌ | ✅ |
| export_manager_enhanced | ✅ (전체) | ❌ | ❌ | ❌ | ✅ |
| spectrum_pdf_exporter | ✅ (QDialog) | ❌ | ✅ | ✅ | ✅ |
| error_handler | ✅ (QMessageBox) | ❌ | ❌ | ❌ | ✅ |

### 4. 추후 작업 시 핵심 역할

- **1차:** 분광 스펙트럼 학술 PDF 보고서 내보내기 (Agent 08 연동)
- **2차:** 구조 이미지 PNG/PDF/SVG 고품질 내보내기 (Agent 01/02 연동)
- **3차:** calculation_logger + history_manager 통합 → 단일 이력 시스템
- **4차:** 전 모듈 에러 핸들링 중앙화
