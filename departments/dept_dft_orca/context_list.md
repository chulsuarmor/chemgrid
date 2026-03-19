# DFT/ORCA 부서 태스크 리스트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 3

## 🔴 PENDING
(없음)

## 🟡 IN PROGRESS
(없음)

## ✅ COMPLETED
- [x] **DFT-001** ORCA %plots cube 파일 생성 [P0] — 기존 ORBITAL_PLOT_TEMPLATE 검증 완료 (MOREAD+NOITER, dim=100, Gaussian_Cube)
- [x] **DFT-002** xtb GFN2-xTB 연동 [P1] — 7개 함수 신규 구현, Mulliken 전하 파싱, graceful fallback

## ⛔ BLOCKED
(없음)

---

## SUBMIT 보고서 (Cascade #3 Wave 3)

### 수정파일

| 파일 | 변경내용 |
|------|----------|
| `src/app/orca_interface.py` | v3.00 → v3.10: 버전 헤더 갱신, xtb GFN2-xTB 통합 (7개 함수 추가: find_xtb_executable, validate_xtb_installation, _generate_xtb_xyz, run_xtb_charges, _parse_xtb_mulliken_charges, map_xtb_charges_to_2d, get_xtb_charges_for_molecule), __main__ 블록 갱신 |
| `_source/orca_interface.py` | 동기화 완료 (src/app/와 동일) |

### 기획자보고 (P-DFT)

**DFT-001**: `ORBITAL_PLOT_TEMPLATE`이 이미 올바른 `%plots` 블록을 포함하고 있음을 확인. ORCA 6.1.1 NO orca_plot 제약을 올바르게 우회하는 2단계 아키텍처 (메인 계산 → MOREAD+NOITER cube 생성) 유지. 수정 불필요.

**DFT-002**: xtb GFN2-xTB 통합을 `orca_interface.py`에 추가. 포터블 경로 탐색 → XYZ 생성 → subprocess 실행 → stdout Mulliken 파싱 → 2D key 매핑의 완전한 파이프라인 구현. xtb 미설치 환경에서 graceful fallback (빈 dict, 에러 없음).

### 검수자판정 (R-DFT)

**판정: PASS**

검증 방법 및 결과:
1. `py_compile.compile('src/app/orca_interface.py', doraise=True)` → PASS
2. `ast.parse()` → PASS (20+ 클래스/함수 정상 인식)
3. `_source/` 동기화 확인 (`diff`) → PASS (동일)
4. `%plots` 포맷 검증 → PASS (Gaussian_Cube, MO, ElDens, MOREAD+NOITER 확인)
5. `DFT_TEMPLATE`에 `%plots` 미포함 확인 → PASS
6. xtb 함수 import 테스트 → PASS (7개 함수 모두 importable)
7. `_parse_xtb_mulliken_charges()` 합성 데이터 테스트 → PASS (4원자 정확 파싱)
8. `map_xtb_charges_to_2d()` 매핑 테스트 → PASS
9. Graceful fallback 테스트 (xtb 미설치 환경) → PASS (빈 dict 반환, 예외 없음)
10. 비인가 파일 수정 확인 → PASS (OWNED_FILES 범위 내만 수정)

### 감사요청
전문 감사 배정: **audit_professional_spectroscopy_properties** (분광물성 감사팀)
- xtb 전하가 향후 ESP 렌더링에 사용될 때 Gasteiger 대비 정확도 개선 여부 확인 필요
- cube 파일 생성 후 3D isosurface 렌더링 호환성 확인 필요
