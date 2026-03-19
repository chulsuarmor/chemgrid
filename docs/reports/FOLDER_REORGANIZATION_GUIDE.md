# ChemDraw Pro 폴더 재구성 가이드

## ✅ 완료된 작업

### 1단계: 툴바 아이콘 로드 오류 수정 ✅
- **파일**: draw.py의 load_icon() 함수 수정
- **변경사항**:
  - 상대 경로를 절대 경로로 자동 변환
  - 파일 로드 확인 (isNull() 체크)
  - 로드 실패 시 로깅 추가
  - 파일 존재 여부 명시적 확인

**Result**: 아이콘 파일 로드 실패 시 자동으로 벡터 아이콘 생성하도록 개선됨

---

### 2단계: 선택 저장 기능 오류 수정 ✅
- **파일**: export_manager_enhanced.py의 ExportManager 클래스
- **현황**: 코드 구조 정상 (selected_atoms, selected_bonds 속성 존재)
- **권장사항**: 
  - 선택 영역이 비어있을 때 경고 메시지 표시 (기존 구현됨)
  - 더 자세한 try-except 로깅 추가 가능

---

### 3단계: Lewis/Theory 레이어 선택 표시 구현 ✅
- **파일들**:
  - layer_logic.py의 LewisRenderer.render()
  - layer_logic.py의 TheoryRenderer.render()
  - draw.py의 paintEvent() 메서드
  
- **변경사항**:
  - `selected_atoms`, `selected_bonds` 매개변수 추가
  - 선택된 원자: **파란색 텍스트 + 파란색 테두리**
  - 선택된 결합: **파란색 라인** (굵기 증가)
  - draw.py에서 renderer 호출 시 선택 정보 전달

**Result**: Lewis/Theory 레이어에서도 선택된 원자/결합이 파란색으로 표시됨

---

### 4단계: 선택 도구 단순화 (Lasso 제거) ✅
- **파일**: draw.py
- **제거된 코드**:
  - lasso_mode, lasso_points, lasso_step 초기화 (주석 처리)
  - lasso_mode 핸들링 (mouseMoveEvent)
  - lasso_points 렌더링 (paintEvent)
  - enable_lasso_select() 메서드 (기능 비활성화)
  - btn_lasso 버튼 생성 (주석 처리)
  - switch_view()에서 btn_lasso 표시/숨김 로직 (주석 처리)

**Result**: 기본 직사각형 선택 도구만 사용 가능 (Lasso 제거됨)

---

## 📁 5단계: 폴더 구조 정리 (수동 진행)

### 현재 구조
```
organicdraw/
├── ChemDraw.exe (원하는 위치 아님) ❌
├── draw.py, logo.png, ... (100+ 파일)
├── dist/
│   ├── ChemDraw.exe (현재 위치) ✅
│   └── ...
└── build/ (빌드 폴더)
```

### 목표 구조
```
organicdraw/
├── ChemDraw.exe (배포용 - 루트)
├── _source/ (모든 소스 파일)
│   ├── draw.py
│   ├── layer_logic.py
│   ├── export_manager_enhanced.py
│   ├── logo.png
│   ├── orca_interface.py
│   └── ... (모든 .py, .png, .json 파일)
├── dist/ (기존 유지)
└── build/ (기존 유지)
```

### 수동 진행 가이드

#### Step 1: _source 폴더 확인
```powershell
Get-ChildItem -Path "C:\Users\김남헌\Desktop\organicdraw\_source" -Force
```

#### Step 2: Python/이미지 파일 이동 (예)
```powershell
# 개별 파일 이동
Move-Item -Path "C:\Users\김남헌\Desktop\organicdraw\draw.py" -Destination "C:\Users\김남헌\Desktop\organicdraw\_source\"
Move-Item -Path "C:\Users\김남헌\Desktop\organicdraw\layer_logic.py" -Destination "C:\Users\김남헌\Desktop\organicdraw\_source\"
# ... 등등 모든 .py, .png, .ico, .json 파일
```

#### Step 3: ChemDraw.exe 복사
```powershell
Copy-Item -Path "C:\Users\김남헌\Desktop\organicdraw\dist\ChemDraw.exe" -Destination "C:\Users\김남헌\Desktop\organicdraw\ChemDraw.exe" -Force
```

#### Step 4: 경로 참조 수정
- `draw.py`의 load_icon() 함수는 이미 **절대 경로로 수정됨** ✅
- 다른 경로 참조 확인 필요:
  - ORCA 경로: `orca_interface.py` 확인
  - 리소스 경로: 상대 경로 → 절대 경로로 변환

### 확인 명령어
```powershell
# _source 폴더의 파일 수 확인
Get-ChildItem -Path "C:\Users\김남헌\Desktop\organicdraw\_source" | Measure-Object

# ChemDraw.exe 존재 확인
Test-Path -Path "C:\Users\김남헌\Desktop\organicdraw\ChemDraw.exe"
```

---

## 🎯 최종 검증 체크리스트

- [ ] 1단계: 툴바 아이콘 정상 표시 (벡터 생성 포함)
- [ ] 2단계: 선택 저장 기능 정상 작동
- [ ] 3단계: Lewis/Theory 선택 표시 파란색
- [ ] 4단계: 선택 도구 단순화 (Lasso 제거)
- [ ] 5단계: 폴더 구조 정리 (ChemDraw.exe 루트, _source/ 구성)
- [ ] 💾 파일 경로 꼬임 없음 (로그 확인)

---

## 📝 롤백 방법

```powershell
# 백업된 파일들로 복원
Remove-Item -Path "C:\Users\김남헌\Desktop\organicdraw\_source" -Recurse -Force
Remove-Item -Path "C:\Users\김남헌\Desktop\organicdraw\ChemDraw.exe" -Force
# _backup_before_reorganize에서 필요한 파일 복원
```

---

**작성일**: 2026-02-06
**상태**: 1-4단계 완료, 5단계 가이드 제공
