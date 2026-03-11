# 📋 ⚛️ ORCA DFT — Task List
## 최종 업데이트: 2026-02-28

- [x] orca_interface.py 구조 분석
- [x] C1 + C5: 포터블 경로 시스템 적용 (하드코딩 절대 경로 → find_orca_executable())
- [x] 인풋 생성 / 실행 / 파싱 3단계 클래스 분리 (OrcaInputGenerator, OrcaExecutor, OrcaOutputParser)
- [x] 에러 처리 강화 (커스텀 예외 5종 + print→logging 교체)
- [x] electron_density_analyzer.py 정리 (print→logging 교체, 코드 클린업)
- [x] 자가 검증 통과 (ast.parse 양 파일 SYNTAX OK)
- [ ] H2O DFT 테스트 통과 (ORCA 실행 환경 필요 — 의존성 설치 후 진행)

### 블로커
- PyQt6, RDKit 미설치 상태 → 앱 통합 테스트 불가
- ORCA 실행 환경 미확인 → H2O DFT 테스트 대기
