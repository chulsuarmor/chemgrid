# 강화된 GUI 감사 프로토콜 — 실사용자 시뮬레이션

## 기존 감사의 한계
- 코드 import만 테스트 → 실제 GUI에서 안 되는 것 못 잡음
- 1~2개 분자만 테스트 → 다양한 분자에서 깨지는 것 못 잡음
- 저장/내보내기 코드만 확인 → 실제 파일 생성 안 되는 것 못 잡음

## 강화 항목

### A. 실제 앱 실행 테스트 (test_visual_auto.py 확장)
1. 앱 실행 → 모든 메뉴 아이템 클릭 → 팝업 열리는지 확인
2. 각 팝업에서 기본 동작 수행 → 결과 표시되는지 확인
3. 에러 다이얼로그 뜨면 → FAIL + 에러 메시지 기록

### B. 50종 분자 다양성 테스트
아래 50개 분자를 전부 입력하여 각 기능 테스트:

**단순 (1~5)**
1. 메탄 CH4
2. 에탄올 CCO
3. 아세톤 CC(=O)C
4. 벤젠 c1ccccc1
5. 물 O

**방향족 (6~15)**
6. 톨루엔 Cc1ccccc1
7. 아닐린 Nc1ccccc1
8. 나프탈렌 c1ccc2ccccc2c1
9. 피리딘 c1ccncc1
10. 인돌 c1ccc2[nH]ccc2c1
11. 퓨란 c1ccoc1
12. 이미다졸 c1cnc[nH]1
13. 퀴놀린 c1ccc2ncccc2c1
14. 안트라센 c1ccc2cc3ccccc3cc2c1
15. 비페닐 c1ccc(-c2ccccc2)cc1

**헤테로고리 (16~25)**
16. 피롤 c1cc[nH]c1
17. 티오펜 c1ccsc1
18. 피리미딘 c1ccncn1
19. 피라진 c1cnccn1
20. 모르폴린 C1CCOCC1
21. 피페리딘 C1CCNCC1
22. 피페라진 C1CNCCN1
23. THF C1CCOC1
24. 옥시란 C1CO1
25. 아지리딘 C1CN1

**약물 (26~35)**
26. 아스피린 CC(=O)Oc1ccccc1C(=O)O
27. 카페인 Cn1cnc2c1c(=O)n(C)c(=O)n2C
28. 이부프로펜 CC(C)Cc1ccc(C(C)C(=O)O)cc1
29. 아세트아미노펜 CC(=O)Nc1ccc(O)cc1
30. 나프록센 COc1ccc2cc(CC(C)C(=O)O)ccc2c1
31. 디아제팜 CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21
32. 메트포르민 CN(C)C(=N)NC(=N)N
33. 실데나필 CCCc1nn(C)c2c1nc(nc2OCC)c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1
34. 오메프라졸 COc1ccc2[nH]c(S(=O)Cc3ncc(C)c(OC)c3C)nc2c1
35. 타목시펜 CCC(/c1ccccc1)=C(/c1ccc(OCCN(C)C)cc1)c1ccccc1

**생체분자 (36~42)**
36. 아데닌 Nc1ncnc2[nH]cnc12
37. 글루코스 OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O
38. 글리신 NCC(=O)O
39. 콜레스테롤 (SMILES 길이 주의)
40. 레티놀 CC1=C(/C=C/C(C)=C/C=C/C(C)=C/CO)C(C)(C)CCC1
41. 테스토스테론 (스테로이드 골격)
42. 유레아 NC(=O)N

**특수 구조 (43~50)**
43. 페로센 [cH-]1cccc1.[Fe+2].[cH-]1cccc1
44. 시스플라틴 [NH3][Pt]([NH3])(Cl)Cl
45. 부타디엔 C=CC=C
46. 아세틸렌 C#C
47. 시클로옥탄 C1CCCCCCC1
48. 큐반 C12C3C4C1C5C3C4C25 (다리걸침)
49. 아다만탄 C1C2CC3CC1CC(C2)C3
50. 벤조[a]피렌 c1ccc2c(c1)cc1ccc3cccc4ccc2c1c34

### C. 저장/내보내기 실제 파일 생성 테스트
- PNG 내보내기 → 파일 크기 > 1KB 확인
- PDF 내보내기 → 파일 크기 > 10KB + 페이지 수 확인
- XYZ 내보내기 → 파일 내용에 원자 좌표 존재 확인
- 스펙트럼 PDF → 6종 그래프 포함 확인

### D. 기능별 클릭 경로 체크리스트
- [ ] 분자 입력 → Drawing → Theory → Lewis 전환
- [ ] 3D 팝업 열기 → 회전/줌 → 오비탈 ON/OFF
- [ ] 스펙트럼 탭 5종(IR/Raman/1H/13C/UV-Vis) 각각 표시
- [ ] 도킹: 프리셋 수용체 선택 → 도킹 실행 → 결과 표시 → 3D 뷰
- [ ] 합성경로: 역합성 분석 → 다단계 경로 표시
- [ ] ADMET: 분석 실행 → 결과 표시
- [ ] 리드 최적화: 목표 선택 → 유도체 생성 → 랭킹
- [ ] 내보내기: PNG / PDF / 선택영역 / 스펙트럼PDF
- [ ] 신약개발: AlphaFold / ADMET / 스크리닝 / 도킹 각각
