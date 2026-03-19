# 전학공 #1 — 감사팀 직렬 교차학습
> 실시일: 2026-03-18 | Cascade #3 사후
> 참여 대상: audit_rendering_qa, audit_popup_qa, audit_integration_qa, audit_visual_feedback
> 참여 대상: audit_professional_structural_chemistry, audit_professional_spectral_properties, audit_professional_pharmacology_docking

---

## 1. 전문감사 실적 요약 (Cascade #3)

| 감사팀 | 검토 건수 | 결과 | 비고 |
|--------|----------|------|------|
| structural_chemistry | 9+1 항목 | PASS | 구조화학 교과서 대조 |
| spectral_properties | 14/14 항목 | PASS | Silverstein/Pretsch 참조 |
| integration_qa | 11/11 항목 | PASS | 크로스 모듈 호환성 |
| pharmacology_docking | 다수 항목 | COND PASS | halogen bond 각도 미적용, PAINS 확장 필요 |
| popup_qa | 다수 항목 | COND PASS | popup 크기 표준화 미완 |
| visual_feedback | 36 시나리오 | 34/36 PASS | 오비탈 이모지 인코딩 1건 |

---

## 2. 감사 품질 향상 교훈

### 교훈 A: CONDITIONAL PASS의 후속 관리
- **상황**: pharma/popup 감사에서 COND PASS → 미해결 항목이 다음 Cascade로 이월
- **문제**: COND PASS 항목이 추적되지 않으면 영구 미해결 상태
- **표준 절차**: COND PASS 시 CT에게 미해결 항목 목록을 명시적으로 상신 → CT가 다음 Cascade context_list.md에 PENDING으로 기록

### 교훈 B: GUI 실행 기반 최종감사의 필수성
- **Cascade #2 실수**: audit_final이 py_compile만 수행, 실제 앱 미실행
- **Cascade #3 개선**: test_visual_auto.py 36 시나리오 자동 스크린샷 + 사용자 직접 확인
- **표준 절차**: 최종감사는 반드시 앱 실행 + QWidget.grab() 스크린샷 + 주요 기능 시각적 확인

### 교훈 C: 학술 기준의 구체성
- **좋은 예**: "H-bond 거리 3.5Å (Bissantz et al., 2010)" → 구체적 출처
- **나쁜 예**: "화학적으로 적절해 보임" → 근거 불명
- **표준 절차**: 감사 판정 시 반드시 참고 문헌/교과서/데이터 출처 명시

### 교훈 D: 감사팀 간 중복 검증 방지
- **상황**: structural_chemistry와 spectral_properties가 동일 분자의 다른 측면을 검증
- **비효율**: 같은 코드 경로를 중복으로 py_compile
- **표준 절차**: 감사팀별 검증 범위를 명확히 구분. py_compile은 1회만 (첫 감사팀이 수행, 결과 공유)

---

## 3. 감사 도메인별 체크리스트 공유

### 구조화학 감사 (structural_chemistry)
- [ ] Bond length: CRC Handbook ±0.01Å 이내
- [ ] Aromatic detection: Hückel (4n+2) + RDKit 이중 확인
- [ ] Partial charge: Gasteiger 60/40 블렌딩 적용 확인
- [ ] Carbon = '' 규칙 준수

### 분광물성 감사 (spectral_properties)
- [ ] IR peak: Silverstein Table 참조, ±30 cm⁻¹ 이내
- [ ] NMR shift: 표준 참조값 ±2 ppm 이내
- [ ] UV-Vis: Woodward-Fieser 규칙 적용 확인
- [ ] Functional group priority: specific → generic 순서

### 약리도킹 감사 (pharmacology_docking)
- [ ] H-bond 거리: ≤3.5Å (donor-acceptor)
- [ ] Hydrophobic: ≤4.0Å
- [ ] Pi-stacking: ≤5.5Å, 각도 분류 (face/T-shaped)
- [ ] Binding affinity: Vina 실제 vs simulation 구분 플래그

### 통합 QA 감사 (integration_qa)
- [ ] Import chain: 모든 conditional import에 AVAILABLE 플래그
- [ ] API 호환성: popup 생성자 파라미터 서명 일치
- [ ] 크로스 모듈 데이터 흐름: analyzer → popup 데이터 전달 무결성

### 시각 피드백 감사 (visual_feedback)
- [ ] 36 시나리오 스크린샷 전수 촬영
- [ ] 비정상 렌더링(빈 화면, 잘림, 겹침) 감지
- [ ] 아카이브 zip 생성 + results.json 메타데이터

---

## 4. Cascade #4 감사 지침

1. **COND PASS 이월 항목**: Cascade #3 미해결 3건 (halogen bond 각도, PAINS 확장, popup 크기 표준화) → 해당 부서 context_list.md에 PENDING 확인
2. **학술 근거 필수**: 모든 수치 판정에 출처(교과서/논문/데이터베이스) 명시
3. **GUI 최종감사**: test_visual_auto.py 실행 + 스크린샷 필수
4. **py_compile 1회 원칙**: 첫 감사팀이 수행 후 결과를 공유 문서에 기록
5. **COND PASS 후속**: 미해결 항목을 CT에 명시적으로 리스트 상신
