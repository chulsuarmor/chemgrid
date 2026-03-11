# Skill: Dual Codebase 동기화

## 규칙
ChemGrid는 두 개의 코드베이스를 유지합니다:
- `src/app/` — 메인 활성 코드 (Run_ChemGrid.bat이 실행)
- `_source/` — 축소된 이전 버전 (백업/폴백)

**모든 파일 수정 시 양쪽 모두 반영해야 합니다!**

## 동기화 방법
```bash
# 단일 파일
cp src/app/modified_file.py _source/modified_file.py

# 여러 파일
cp src/app/analyzer.py _source/analyzer.py
cp src/app/layer_logic.py _source/layer_logic.py
cp src/app/popup_3d.py _source/popup_3d.py

# 신규 파일 — _source에도 복사
cp src/app/new_module.py _source/new_module.py
```

## 주의
- `_source/`에는 일부 파일이 없을 수 있음 (예: docking_interface.py) → 새로 복사
- import 경로는 동일 (같은 디렉토리 내 상대 import)
- `_source/draw.py`는 `src/app/draw.py`와 동일한 진입점이지만,
  실제 실행은 `src/app/draw.py`만 사용
- 구문 검사: `python -c "import py_compile; py_compile.compile('path', doraise=True)"`
