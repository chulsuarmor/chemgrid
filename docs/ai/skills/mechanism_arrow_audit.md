# Skill: Mechanism Arrow 5종 × Rule O 의무 검증
# 신설: 2026-04-27 Worker P W_P_M562 (M556 task)
# 참조: anger_simulator.py ANGER_MATRIX_MECH 50건, mechanism_visibility_standard.md (M473), mechanism_rendering.md (M548)

---

## 1. 5종 핵심 메커니즘 + Rule O 6항목 매트릭스

| 메커니즘 | 단계 수 | Rule O 검증 | 격분 트리거 |
|---------|--------|-------------|-----------|
| EAS | 3 | arrow_size>=10 / half_w>=0.42 / barb>=0.40 | ANGER MECH-EAS |
| SN2 | 2 | 동일 | ANGER MECH-SN2 |
| E2 | 1 | 동일 | ANGER MECH-E2 |
| Aldol | 4 | 4색 표준 + worktree 동기화 | ANGER MECH-ALDOL |
| Diels-Alder | 2 | 6 화살표 동시 + endo/exo | ANGER MECH-DA |

---

## 2. Rule O 6항목 (Qt/QPainter + PIL 양쪽)

### Qt 경로 (popup_reaction.py)
```python
# CurvedArrowRenderer.draw_full_arrow
arrow_size = max(10, min(0.15 * length, 18))  # >= 10px (Rule O)
half_w = arrow_size * 0.42  # >= 0.42 (McMurry 교과서)

# CurvedArrowRenderer.draw_half_arrow (fishhook)
barb_width = arrow_size * 0.40  # >= 0.40 (라디칼 식별)
```

### PIL 경로 (drylab_report_exporter.py)
```python
# _draw_curved_arrow (M548 후)
head_len = 18  # px (>= 10)
head_w = 0.42  # full arrow >= 0.42
_FISH_W = 0.40  # fishhook >= 0.40
```

**M548 교훈**: Qt 경로만 수정하면 PIL 경로 Rule O 재위반 — **두 경로 동시 점검 의무**.

---

## 3. 4색 표준 (M442) — _ARROW_COLOR_MAP

```python
_ARROW_COLOR_MAP = {
    "lone_pair":       "#2980B9",  # 파랑 (친핵)
    "negative_charge": "#2980B9",
    "pi_bond":         "#8E44AD",  # 보라 (결합끊김)
    "aromatic_pi":     "#8E44AD",
    "sigma_bond":      "#8E44AD",
    "bond":            "#8E44AD",
    "bond_center":     "#8E44AD",
    "pericyclic":      "#27AE60",  # 초록 (결합형성)
}
_AC_DEFAULT = "#E74C3C"  # 빨강 (기본/친전자)
```

**5색 이상 = Rule O 위반**. 4색 표준 반드시 준수.

---

## 4. 메커니즘별 화학적 정확성

### EAS (3 단계)
- step1: pi-e 공격 (lone_pair from_type)
- step2: arenium 중간체
- step3: H+ 이탈 (bond cleavage)

### SN2 (2 단계)
- backside attack 180° (Walden inversion)
- 동시 결합 형성/끊김 (concerted)

### E2 (1 단계)
- anti-periplanar 180° dihedral
- 3 화살표 동시 (염기 H 추출 + π 형성 + LG 이탈)

### Aldol (4 단계)
- step1: alpha-탈양성자화 (lone_pair)
- step2: enolate 공격
- step3: C-C 결합 형성
- step4: protonation

### Diels-Alder (2 단계)
- step1: pi_bond × 3 동시 (concerted [4+2])
- endo/exo selectivity (regio)

---

## 5. 템플릿 충돌 방지 (Rule P)

### 격분 핵심
- **Aldol** 트리거가 Bamford-Stevens 과매칭 가능
- **Sharpless** dihydroxylation Aldol과 충돌
- **Diels-Alder** 1,3-dipolar / Cope 트리거 우선순위

### 검사 의무
- 신규 템플릿 추가 시 기존 트리거 조건과 충돌 검사 필수
- Exclusion guard (가드 조건) 추가
- 범용 패턴은 특수 패턴 뒤 배치
- 최소 5종 반응에 대해 매칭 검증

---

## 6. P-WORKTREE 충돌 방지 (M442/M491/M520/M521 5회 누적)

### 격분 핵심
- arrow_generator.py 메인 vs 워크트리 diff 매번 0건 보장
- audit_gui가 메인 repo만 검사하면 PASS — 실제 빌드 대상 워크트리는 별개

### 검사 의무 (R-12 / SC16)
- diff -q 메인 vs 15 worktree IDENTICAL 확인
- worktree_sync_all.py --all 매 사이클 실행

---

## 7. patrol G7-SC31 자동 검사

```python
# patrol.py mechanism_visibility 검사
SC31_a = "arrow_size = max\\(([0-9]+),"  # >= 10 확인
SC31_b = "half_w = arrow_size \\* ([0-9.]+)"  # >= 0.42 확인
SC31_c = "barb_width = arrow_size \\* ([0-9.]+)"  # >= 0.40 확인
SC31_d = "QColor\\(204, 0, 0\\)"  # 하드코딩 WARN
```

---

## 8. 캡처 자동화 (5 메커니즘 × 5 단계 = 25 조합)

```python
# tools/mechanism_arrow_capture.py 패턴
mechanisms = ['eas', 'sn2', 'e2', 'aldol_condensation', 'diels_alder']
for mech in mechanisms:
    popup = ReactionPopup(mechanism=mech)
    popup.show()
    for step_idx in range(popup.total_steps):
        popup.set_step(step_idx)
        pixmap = popup.grab()
        pixmap.save(f"docs/reports/feedback/M562_mech/{mech}_step{step_idx}.png")
```

---

## 9. 체화 4단계 (Rule H + V)

- H-1: 인식 — 5 메커니즘 × 5 단계 = 25 의무 캡처 (현재 0건)
- H-2: 본 skill 파일 (Rule O 6항목 매트릭스)
- H-3: patrol SC31 + SC56 (자동 WARN)
- H-4: CLAUDE.md Rule O 강화 — Qt+PIL 두 경로 동시 검사 의무

---

## 10. 학회 임박 시연 의무

학회장 학생이 다음 질문에 답할 수 있어야 함:
- "EAS 화살표 5단계 색상이 다른 이유?" → 답: 4색 표준 (lone_pair 파랑 / pi_bond 보라 / pericyclic 초록 / 기본 빨강)
- "fishhook이 뭐냐?" → 답: 1전자 라디칼 화살표 (barb_width >= 0.40)
- "Diels-Alder 6 화살표 동시?" → 답: concerted [4+2] cycloaddition (pericyclic)

---

## 11. M1376 패턴 추가 (2026-05-18 W188 G3 top-10 patch)

### MECHANISM-ARROW-TYPE-MAP-001
> from_type 값은 반드시 _ARROW_COLOR_MAP 키 중 하나여야 한다.
> `bond_center`는 color map에 없음 → silently _AC_DEFAULT(빨강)로 fallback = 잘못된 색상.
> 이탈기 결합 끊김에는 `"bond"` 사용 (map에 있음, → 보라 = 결합끊김 M442 정확).

### MECHANISM-SELF-LOOP-001
> from_atom_idx == to_atom_idx >= 0 = 렌더링 불가 (0길이 화살표).
> ArrowData 생성 시 반드시 from ≠ to 확인.
> from_atom_idx=-1 (외부 분자) ≠ 같은 외부 분자. 두 외부를 구분하려면 -1/-2 사용.

### MECHANISM-ORANGE-COLOR-001
> #FF9800 (orange)는 4색 표준 밖 → `_assign_colors()`가 from_type 기준으로 보라로 덮어씀.
> Wittig P=C 결합 이동 = bond_type → 보라(결합끊김) 표준 색상으로 교체.

### 적용 대상 (top 10 reactions, M1370 G3)
SN2 / E2 / Aldol / Diels-Alder / Grignard / Friedel-Crafts / Wittig / Cannizzaro / Robinson annulation / Mannich

*최종 갱신: 2026-05-18 / Worker W188 / M1376*

---

## 11. M894 내부 버그 3종 패턴 (2026-05-12 신설)

### 패턴: INTERNAL-MECHANISM-ARROW-BUG-3PACK

외부 엔진 대체 불가(M893) 후 내부 버그 3종 직접 수정.

#### Bug 1: curvature 부호 처리 (arrow_generator.py)

`_arrow_for_bond_break`에서 LG 이탈 화살표 curvature를 음수로 설정:
```python
# _arrow_for_bond_break 반환 시
curvature = -abs(raw_curv)  # LG 이탈 = 음수(아래 아치), 교과서 McMurry §7

# _arrow_for_bond_form 반환 시
curvature = +abs(raw_curv)  # Nu 공격 = 양수(위 아치)
```
주의: MECHANISMS dict의 하드코딩 ArrowData curvature는 렌더러 cross product가 재결정하므로 직접 수정 불필요.

#### Bug 2: from_atom_idx==-1 외부 원자 좌표 (popup_reaction.py)

`_draw_mechanism_arrows`에서 from_atom_idx < 0인 경우 from_label 기반 Nu/LG 가상 좌표 생성:
```python
_external_positions = {
    -10: QPointF(bbox_xmin - 50, bbox_cy),  # Nu: 왼쪽 외부
    -11: QPointF(bbox_xmax + 50, bbox_cy),  # LG: 오른쪽 외부
    -12: QPointF(bbox_cx, bbox_ymin - 50),  # 양성자 이탈: 상단
}
# from_label_lower에서 LG/Nu 키워드 감지 → 적절한 가상 좌표 할당
```

#### Bug 3: atom_map_num 기반 idx 보정 (reaction_mechanisms.py)

`resolve_atom_map_indices(arrows, mol)` 함수 추가:
- `ArrowData.from_atom_map` / `to_atom_map` 필드 추가
- RDKit SMILES 재정렬 후에도 atom map number → 현재 idx 역변환

### 검증 기준 (patrol SC107 추가 권고)
- `curvature=-abs` for bond_break 확인
- `_external_positions` dict 존재 확인
- `from_atom_map: int = -1` 필드 확인
- `resolve_atom_map_indices` 함수 호출 확인
- "Aldol enol vs enolate 표시?" → 답: alpha-탈양성자화 후 nucleophile 공격
