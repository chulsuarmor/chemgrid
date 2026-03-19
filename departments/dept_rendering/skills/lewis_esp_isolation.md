# Lewis/ESP 격리 규칙
> Lewis 모드에서 ESP 전자구름이 표시되면 심각한 버그입니다.

## 규칙
ESP 전자구름은 반드시 `self.view_state == "Theory"` 조건 하에서만 렌더링합니다.

## 적용 위치 (canvas.py 3곳)
1. LAYER 2 (animation bg): `if self.view_state == "Theory":`
2. LAYER 3 (main): `if self.view_state == "Theory":`
3. LAYER 4 (Drawing): `if self.view_state == "Theory":`

## 듀얼 코드베이스
src/app/canvas.py와 _source/canvas.py 모두에 동일 조건 적용 필수.
