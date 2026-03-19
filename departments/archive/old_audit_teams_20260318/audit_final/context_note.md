# 최종감사팀 기술 노트
## 마지막 업데이트: 2026-03-18 (초기 생성)

### GUI 테스트 핵심 주의사항
- reveal_radius = 0이면 Lewis/Theory 모드에서 빈 화면 (반드시 max_r 설정)
- conda env chemgrid 활성화 필수
- 창 탐지: "ChemGrid" 대소문자 주의 (VS Code 오인 방지)
- VBScript + in-process 방식으로 GUI 자동화 (Git Bash에서 Qt 창 직접 생성 불가)
- --auto-mol / --auto-smiles CLI 인자 활용 가능
