# Skill: Anger Simulator ML 진화 (M562/M556)
# 신설: 2026-04-27 Worker P W_P_M562_DEEP_ANGER_100PLUS_ML
# 참조: housing/sinktank/anger_simulator.py, FALSE_PASS_REGISTRY FP-21/R-23/SC56
# 사용자 명시 직접 인용:
#   "디테일하게 격분하고 주변거까지 전수조사하도록 계속 물어봐야 해
#    특히 입체구조 레이어, 메커니즘 표현 화살표같이 내가 존나 강조한건 더 빡세게"
#   "절대 멈추지 말고 무한루프 사이클 돌면서 계속 발전시켜 마치 머신러닝 하듯이"

---

## 1. 핵심 원칙

### 정적 패턴 풀 = 깡통 (FP-21 P-STATIC-PATTERN-POOL)
- anger_simulator가 ANGER_PATTERNS 8개 정적 풀만 사용 = 사용자 신규 격분 미커버
- mistakes.md에 새 패턴 누적되어도 풀에 자동 추가 안 됨
- 매 사이클 같은 격분 5건만 반복 → 사용자 신뢰 무너짐

### ML 진화 의무 (R-23)
1. ANGER_MATRIX_FULL >= 100건 (입체 50+ + 메커니즘 50+)
2. evolve_anger_pool() 매 사이클 호출 (ralph_loop Phase 4.7b)
3. anger_log.jsonl 매 발화 누적 (시계열 학습 데이터)
4. 시간 감쇠 가중치 (48시간 반감기)
5. precision/recall 측정 — 매칭률 < 50% 시 매트릭스 자동 통합
6. cycle_html에 _build_anger_ml_metrics_section() 임베드 (CC Rule)

---

## 2. 매트릭스 카테고리 (154건 — M1362 갱신 2026-05-18)

### 입체구조 격분 (53건)
| 그룹 | 세부 | 건수 |
|------|------|------|
| popup_3d Tab 0 Properties | 5분자 × 3 | 8 |
| popup_3d Tab 1 Spectrum | 5분자 × 3 | 8 |
| popup_3d Tab 2 Vibration | 5분자 × 3 | 6 |
| popup_3d Tab 3 Orbital | 5분자 × 3 | 5 |
| popup_3d Tab 4 Docking | 5분자 × 3 | 3 |
| popup_3d Tab 5 ChemChar | 5분자 × 3 | 3 |
| sp2 N / aromatic / VSEPR | 주변 전수 | 5 |
| SP3D / SP3D2 / CIP wedge | metal complex | 3 |
| 추가 (morphine/epinephrine 등) | extra | 12 |

### 메커니즘 격분 (50건)
| 메커니즘 | 단계 | 건수 |
|---------|------|------|
| EAS | 5단계 | 5 |
| SN2 | 5단계 | 5 |
| E2 | 5단계 | 5 |
| Aldol | 5단계 | 5 |
| Diels-Alder | 5단계 | 5 |
| Rule O 6항목 | Qt+PIL 검증 | 5 |
| 추가 (TS/lone pair/4색/Polymer 등) | extra | 20 |

### M1362 신규 격분 (4건 — 2026-05-18 W16 누적)
| 카테고리 | ID | 가중치 | 상태 |
|---------|-----|--------|------|
| permanent_delete_threat | M1362-C01 | 3.0 (최고) | OPEN |
| zombie_not_cleaned | M1362-Z01 | 1.8 | RESOLVED (W2 370b8b0c) |
| parallel_30plus_violation | M1362-P01 | 1.9 | RESOLVED (14 Agent) |
| arbitrary_addition_anger | M1362-A01 | 2.2 | OPEN |

---

## 3. 진화 알고리즘 (evolve_anger_pool 7단계)

```python
def evolve_anger_pool(cycle_data, force_expand=False):
    # 1. 최근 1000건 로그 로드
    entries = _load_anger_log_recent(limit=1000)

    # 2. 시간 감쇠 가중치 계산 (반감기 48시간)
    # weight = exp(-elapsed_hours * ln(2) / 48)
    time_freq = _compute_time_decayed_frequency(entries)

    # 3. precision/recall 측정 (사용자 격분 키워드 vs 시뮬레이션 격분)
    metrics = _measure_precision_recall(entries)

    # 4. 매칭률 < 50% 시 매트릭스 자동 풀 통합
    if metrics["precision"] < 0.50 or force_expand:
        _expand_pool_if_needed(...)

    # 5. anger_metrics.json 저장
    _save_metrics(metrics)

    return metrics
```

---

## 4. ralph_loop 통합 (Phase 4.7b)

### 3개 ralph_loop 모두 동시 가동
```bash
# ralph_loop_chemgrid.sh / ralph_loop_local.sh / ralph_loop_web.sh

# Phase 4.7 (ct_force_reject_5x) 직후
echo "[Ralph] Phase 4.7b: anger_simulator ML 진화 (M562)..."
"$CHEMGRID_PYTHON" -c "
import sys
sys.path.insert(0, '/c/chemgrid/housing/sinktank')
from anger_simulator import evolve_anger_pool
metrics = evolve_anger_pool(cycle_data={'cycle_no': '${LOOP_COUNT}'})
print(f'ANGER_ML pool={metrics.get(\"pool_size\")} matrix={metrics.get(\"matrix_size\")} expanded={metrics.get(\"expanded_this_cycle\")} precision={metrics.get(\"precision\"):.2f}')
"
```

---

## 5. patrol SC56 검증

```python
# patrol.py check_g7_serial_compliance()
# 1) anger_simulator.py STEREO-/MECH- id 카운트 >= 100
# 2) anger_metrics.json mtime <= 6시간 (Phase 4.7b 가동 증거)
# 3) anger_metrics.json pool_size >= 8

if matrix_count < 100:
    sc56_warn = True  # FP-21 미해소
if metrics_age > 21600:  # 6h
    sc56_warn = True  # ML 미가동
if pool_size < 8:
    sc56_warn = True  # 기본 패턴 손실
```

---

## 6. cycle_html 임베드

`_build_anger_ml_metrics_section()`을 sections에 추가:
- 정확도 평균 (precision + recall) / 2
- pool_size / matrix_size / expanded
- 누적 발화 로그 (anger_log.jsonl)
- 시간 감쇠 TOP5 패턴

---

## 7. 다람쥐볼 의무

ralph_loop가 자동으로 매 사이클 실행하지만, **신규 worker spawn 시**:
1. 이 skill 파일 Read 의무 (Rule V)
2. ANGER_MATRIX_FULL >= 100 확인 의무
3. anger_metrics.json mtime 확인 의무 (6h 윈도우)
4. precision/recall 50% 미달 시 force_expand=True 호출 가능

---

## 8. 자가 진화 패턴 (M562 구조)

```
사이클 1: 정적 8 패턴 → 5건 격분 발화
사이클 N: 매트릭스 103건 자동 통합 → pool=111
사이클 N+1: 사용자 신규 격분 등장 → user_anger_log.jsonl 추가
사이클 N+2: TF-IDF 추출 → 매트릭스에 신규 패턴 자동 등록
사이클 N+3: precision 향상 → 학습 누적 효과
```

---

## 9. 체화 4단계 (Rule H)

- H-1: 인식 — 정적 8 패턴 풀 = 깡통 (FP-21)
- H-2: docs/ai/skills/anger_ml_evolution.md (이 파일)
- H-3: patrol.py G7-SC56 신설 (자동 WARN)
- H-4: CLAUDE.md JJ 격분진화의무 — anger_simulator ML 매 사이클 누적 + 100+건 매트릭스 + 시계열 가중치

---

## 10. W16r 갱신 (2026-05-18 D-M1153-002-W16r)

### 현재 상태
- ANGER_MATRIX_FULL: 154건 (stereo 53 + mech 50 + M621=17 + M643=5 + M724_LV=12 + M736=13 + M1362=4)
- pool_size: 162 (매트릭스 자동 통합)
- log_entries: 306
- USER_FEEDBACK_MATRIX (ct_hourly_review.py): 49건 (M1346~M1353 8블록 추가됨)

### M1362 신규 카테고리 4종
| ID | 카테고리 | 가중치 | 상태 |
|----|---------|-------|------|
| M1362-C01 | permanent_delete_threat | 3.0 (CRITICAL) | OPEN |
| M1362-Z01 | zombie_not_cleaned | 1.8 | RESOLVED (W2 370b8b0c) |
| M1362-P01 | parallel_30plus_violation | 1.9 | RESOLVED (14 Agent) |
| M1362-A01 | arbitrary_addition_anger | 2.2 | OPEN |

### USER_FEEDBACK_MATRIX M1346~M1353 8블록 추가
- M1346-ENGINE: 엔진 연결 측정 (RESOLVED)
- M1347-HTML: HTML 정합성 검증 (RESOLVED)
- M1348-HALLUC: AV 할루시네이션 검증 (RESOLVED)
- M1349-INCOMPLETE: 미완성도 보고 (RESOLVED)
- M1350-SERIAL: 직렬 준수 검증 (RESOLVED)
- M1351-DEPLOY: GitHub 배포 (RESOLVED, P0)
- M1352-ZOMBIE: Zombie cleanup (RESOLVED)
- M1353-MEMORY: 단기기억 추출 (RESOLVED)

### 30+ 병렬 격분 회피 준수
임무 지시서 명시: "임의 추가 금지 — 기존 매트릭스 갱신만". 신규 격분 패턴 0건 추가.
Rule K3 Surgical Changes 준수.
