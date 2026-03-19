# 듀얼 코드베이스 동기화 프로토콜

## 규칙
src/app/에서 수정한 모든 파일은 반드시 _source/에도 동일하게 반영.

## 동기화 대상
- src/app/*.py ↔ _source/*.py
- 파일명이 동일한 것만 동기화
- _source/에만 존재하는 레거시 파일은 무시

## 검증
수정 후 diff로 확인:
```bash
diff /c/chemgrid/src/app/[파일명] /c/chemgrid/_source/[파일명]
```

## 주의
_source/는 stripped-down 구버전.
새 파일 추가 시 _source/에도 복사하되, 해당 부서 MM에게 보고.
