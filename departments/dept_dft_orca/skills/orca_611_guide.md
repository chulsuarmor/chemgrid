# ORCA 6.1.1 사용 가이드

## 핵심 주의사항
- ORCA 6.1.1에는 `orca_plot` 유틸리티가 **없음**
- cube 파일 생성: `%plots` 블록을 input 파일에 직접 작성
- MOREAD+NOITER: 기존 orbital로 cube 생성 시 사용

## ORBITAL_PLOT_TEMPLATE
orca_interface.py에 정의된 템플릿:
- B3LYP/6-31G(d) 기본 수준
- %plots 블록으로 .cube 생성

## 파일 경로
- ORCA 실행 경로: C:\chemgrid\Orca.6.1.1\
- 계산 결과: orca_history/
