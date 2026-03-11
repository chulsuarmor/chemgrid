# r1_gemini_commands.md — 🌈 렌더링 엔진 에이전트 (R1) 논리 구축용 Gemini 명령 체계

## 1. 개요
이 문서는 렌더링 엔진 에이전트(R1)가 Gemini와 소통할 때 사용할 구체적인 논리 흐름과 명령 템플릿을 정의합니다. 모든 명령은 **원시 데이터(Raw data)를 시각적 정보로 변환**하는 데 초점을 맞춥니다.

## 2. R1 논리 대원칙
1. **데이터 기반 통찰:** 단순히 그리라고 하지 않고, "이 Mulliken 전하 분포를 볼 때, 친전자체 공격이 예상되는 부위에 80% 투명도의 Cyan 조준선을 그려야 한다"와 같은 논리를 사용함.
2. **시각적 정교함:** `round(coord, 2)`를 준수하며, CPK 색상 및 가우시안 블러 세기를 물리적 수치에 근거하여 조정함.
3. **사용자 경험(UX):** 반응 메커니즘 표기용 LP와 전자구름 밀도용 전자를 명확히 구분함.

## 3. Gemini 하달 명령 템플릿

### 3.1. ESP 맵 렌더링 논리 정교화
**명령:**
> 분자 데이터 `{molecular_json}`의 ESP 밀도 범위를 분석하여, `renderer.py`의 `calculate_esp_color` 로직을 다음 조건에 맞춰 조정해:
> - 극값이 0.1 이하인 경우 대비를 1.5배 증폭하여 가시성 확보.
> - `_blend` 함수를 사용하여 원자별 구름 경계가 겹칠 때 노이즈가 발생하지 않도록 알파 값을 보간할 것.
> - 결과물의 AST 구문을 체크하여 `CloudRenderer`에 즉시 반영 가능한 코드를 생성해.

### 3.2. 공명 및 고리 시스템 균등화
**명령:**
> `{results_json}`에 포함된 aromaticity 데이터를 기반으로, 고리에 속한 모든 원자의 `mulliken_charge`를 평균화(`avg_charge`)할 때, **융합 고리(Fused Rings)**의 경우 각 고리별 독립 평균이 아닌 전체 고리 시스템의 통합 평균을 사용하도록 `_render_atom_clouds_inner` 논리를 업데이트해. 
> - `charges = dict(charges)` 복사본을 유지하고 원본은 건드리지 마.
> - logging 라이브러리를 통해 "Fused ring equalization applied for {ring_count} rings" 로그를 남길 것.

### 3.3. Gemini API 연동 아키텍처 (Python 초안)
```python
def call_gemini_for_render_logic(context_data):
    """
    R1의 논리를 Gemini에게 전달하여 렌더링 최적화 코드를 제안받음.
    """
    prompt = f\"\"\"
    당신은 화학 데이터 시뮬레이션 전문가입니다.
    현재 분자 상황: {context_data['summary']}
    요청: {context_data['request']}
    제약: renderer.py의 CloudRenderer 클래스 내부 메서드만 수정 가능.
    좌표: round(coord, 2) 준수.
    \"\"\"
    # API 호출 로직 (google-genai)
    return response.text
```

## 4. Act Mode 재개 시 체크리스트
- [ ] `google-genai` 라이브러리 설치 확인 (`py -m pip install google-genai`)
- [ ] API 키 환경변수 (`GEMINI_API_KEY`) 설정 확인
- [ ] `renderer.py`의 `CloudRenderer` 메서드 서명(Signature) 변경 시 `layer_logic.py` 영향 평가
