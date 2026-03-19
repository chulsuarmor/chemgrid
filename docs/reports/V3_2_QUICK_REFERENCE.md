# v3.2 해석적 렌더링 - 빠른 참조

**버전:** renderer.py v3.2
**날짜:** 2026-02-10

---

## 🚀 4가지 이론적 가공 로직

### 1️⃣ 반응성 가중치 (Reactivity Weight)
```python
# 전하 차이를 exp()로 증폭
charge_deviation = charge - ring_avg_charge
reactivity_weight = exp(abs(charge_deviation) * 35.0)
mix = mix * reactivity_weight

효과: ±0.01 차이 → 50%+ 시각적 차이
```

### 2️⃣ 가변 구름 크기 (Variable Cloud Size)
```python
# 비활성 탄소(양전하 > 평균) 구름 축소
if is_ring_carbon and charge > ring_avg_charge:
    radius *= 0.60  # 40% 추가 축소

효과: meta (6px) vs ortho/para (10px) - 크기로 구분
```

### 3️⃣ 조준선 마커 (Crosshair Markers)
```python
# 전자 밀도 상위 2-3개 탄소에 녹색 십자선
electron_rich_carbons.sort(key=lambda x: x[1])
top_sites = electron_rich_carbons[:3]
draw_crosshair(position, color=(0, 200, 0))

효과: ortho/para에 ⊕ 마커 자동 표시
```

### 4️⃣ 고리 탄소 레이어 강도
```python
# 고리 탄소 불투명도 1.5배 강화
if is_ring_carbon:
    base_layer_alpha *= 1.5

효과: 치환기 O가 고리 C 정보를 가리지 못함
```

---

## 📊 니트로벤젠 예상 결과

```
        NO₂
         ↓
    [ortho: 10px, 42% 파랑, ⊕]
    /                         \
[meta: 6px, 52% 빨강]  [para: 10px, 42% 파랑, ⊕]
    \                         /
    [meta: 6px, 52% 빨강]
         ↓
    [ortho: 10px, 42% 파랑, ⊕]
```

**3가지 방법으로 meta 구분:**
1. 크기: 6px (ortho/para는 10px)
2. 색상: 52% 빨강 (ortho/para는 42% 파랑)
3. 마커: 없음 (ortho/para는 ⊕ 있음)

---

## ✅ 테스트 검증 항목

```
✓ meta-C 색상 강도 > ortho/para-C (52% vs 42%)
✓ meta-C 구름 크기 < ortho/para-C (6px vs 10px)
✓ ortho-C, para-C에 녹색 ⊕ 조준선 마커
✓ 고리 C 전하가 NO₂의 O 구름에 묻히지 않음
```

---

## 🔧 주요 파라미터

| 파라미터 | 값 | 용도 |
|---------|-----|------|
| `k` (지수 상수) | 35.0 | 반응성 가중치 증폭률 |
| `deactivation_factor` | 0.60 | 비활성 탄소 구름 축소 (40%) |
| `ring_alpha_boost` | 1.5 | 고리 탄소 불투명도 강화 |
| `num_markers` | 2-3 | 조준선 마커 개수 |
| `marker_color` | (0, 200, 0) | 녹색 조준선 |

---

**상태:** ✅ v3.2 구현 완료
**문서:** VISUAL_ENGINE_V3_2_INTERPRETIVE.md (상세)
