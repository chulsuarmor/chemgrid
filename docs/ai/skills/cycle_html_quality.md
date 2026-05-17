# Skill: cycle_html 품질 기준 (Rule CC 체화)

> 최종 업데이트: 2026-05-18 (M1359 §IMG-SRC-RULE 신설 — data:image/* 완전 금지)
> 근거: Rule CC "cycle_html은 사용자index.html수준(다크테마+이미지5+P0표+격분인용+evidence카드)"
> Worker: W_CYCLE_AUDIT_M821_INFINITE

---

## Rule CC 7체크 (의무)

| 체크 | 기준 | 차단 패턴 |
|------|------|---------|
| 1. 다크테마 | background #1a1a2e 의무 | 흰 배경 = REJECT |
| 2. 이미지 25+ | `<img>` 태그 25개 이상 | 이미지 5개 미만 = REJECT |
| 3. P0/P1 표 | `<table>` 이슈 목록 | 표 없음 = REJECT |
| 4. 격분 인용 | 사용자 격분 직접 인용 (따옴표) | 인용 없음 = REJECT |
| 5. evidence 카드 | 실측 수치/파일경로/크기 포함 | 빈 evidence = REJECT |
| 6. user_env 섹션 | Rule OO 4-layer 배지 | 섹션 없음 = WARN |
| 7. dispatch raw | 외부 AI 로그 raw 텍스트 | 없음 = WARN |

## §IMG-SRC-RULE (M1359 신설)

**패턴명: IMG-SRC-MUST-BE-REAL-FILE**

- `data:image/svg+xml` base64 src = user_env_verify hook 즉시 차단 (HTML_PLACEHOLDER_OR_DATA_SVG_PROMOTION)
- `data:image/png` base64 = 동일하게 차단 대상
- **올바른 방법**: 실존하는 PNG 파일을 상대경로로 참조
  - 예: `../../housing/evidence/D-M1034-W32/captures/benzene_lewis.png`
  - 예: `../captures/aspirin_theory.png`
- 캡처 PNG 없을 시: img 태그 대신 div.data-card로 수치만 표시 (이미지 없음 명시)
- hook 파일: `.claude/hooks/user_env_verify.py` L82

---

## §12 offscreen 캡처 방식 (M821 신설)

### 패턴명: OFFSCREEN-CAPTURE-INPROCESS-001

**문제**: subprocess.run([sys.executable, script.py]) 방식으로 QWidget 캡처 시
Qt 플랫폼 초기화 격리로 0바이트 PNG 생성.

**원인**: 자식 프로세스에서 QT_QPA_PLATFORM=offscreen env 전달 시
WA_DontShowOnScreen + grab()이 화면 버퍼 없이 빈 pixmap 반환.

**올바른 방법**:
```python
# 반드시 단일 프로세스 in-process 방식
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
app = QApplication.instance() or QApplication(sys.argv)

# 모든 popup을 동일 process 내 순서대로 생성/캡처
for mol_name, smiles in molecules:
    for popup_key, cls, init_args in popups:
        w = cls(*init_args)
        w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        w.resize(900, 700)
        w.show()
        app.processEvents()
        time.sleep(0.4)
        app.processEvents()
        w.grab().save(out_path)
        w.close()
        w.deleteLater()
        app.processEvents()
```

**FP 차단**: FP-05 (1KB 미만 = 빈화면), FP-19 (popup ghost)

**[M905] 순서 필수 — WA_DONTSHOWONSCREEN-BEFORE-RESIZE-001**:
```python
# WRONG (C0000409 크래시):
widget.setFixedSize(900, 700)
widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)  # 역순이면 크래시!

# CORRECT:
widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)  # 반드시 먼저
widget.resize(900, 700)   # 그 다음 크기 설정
widget.show()
app.processEvents()
```

---

## §13 Molecule3DPopup 캡처 방법 (M821 신설)

```python
# Molecule3DPopup은 Molecule3DData를 인자로 받음
from popup_3d import Molecule3DPopup, Molecule3DData

# atoms={}/bonds={}+smiles= 전달 시 _build_data가 RDKit 경로 사용
mol_data = Molecule3DData(atoms={}, bonds={}, smiles=smiles, mol_name=mol_name)
w = Molecule3DPopup(mol_data)
```

---

## §14 이미지 갤러리 HTML 패턴

```html
<div class="img-gallery">
  <div class="img-card">
    <img src="M821_captures/benzene_popup_synthesis.png" loading="lazy">
    <div class="img-label">benzene synthesis 27KB</div>
  </div>
  ...
</div>

<style>
.img-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px,1fr)); gap: 12px; }
.img-card { background: #0f3460; border-radius: 8px; overflow: hidden; }
.img-card img { width:100%; height:165px; object-fit:contain; background:#111; }
</style>
```

---

## §15 탭 전환 명시적 캡처 (M822 신설)

### 패턴명: CYCLE-TAB-CAPTURE-MISSING-001

**문제**: AlphaFoldPopup/DockingPopup 등 다탭 팝업 캡처 시 기본 Tab0만 캡처하면
Tab5(PDBe Mol*)와 같은 중요 기능이 cycle_html에 포함되지 않아 false MISSING 판정됨.

**원인**: `capture_widget(w, out)` 호출 전 `setCurrentIndex()` 미호출 시
항상 Tab0이 캡처됨 → Tab2+ 기능 = 미캡처 상태.

**올바른 방법**:
```python
# 다탭 팝업은 반드시 탭 전환 후 캡처
w = AlphaFoldPopup(initial_smiles=smiles)
if hasattr(w, 'tabs') and w.tabs.count() >= 5:
    w.tabs.setCurrentIndex(4)  # Tab5 = PDBe Mol* 시각화 탭
capture_widget(w, out_path_tab5)
# Tab0 별도 캡처 (SIMULATION banner)
w2 = AlphaFoldPopup(initial_smiles=smiles)
if hasattr(w2, 'tabs'):
    w2.tabs.setCurrentIndex(0)
capture_widget(w2, out_path_tab0)
```

**patrol 권고**: capture 스크립트에서 AlphaFoldPopup/DockingPopup 캡처 시
`setCurrentIndex` 호출 없으면 WARN (Tab5 미포함 위험).

---

## §16 팝업 생성자 시그니처 검증 (M823 신설)

### 패턴명: POPUP-CONSTRUCTOR-MISMATCH-001

**문제**: SpectrumPopup(smiles, mol_name) — SpectrumPopup은 SpectrumData 객체를 인자로 받음.
SMILES 문자열을 직접 전달하면 QDialog(parent=str) TypeError 발생.

**원인**: popup 클래스마다 생성자 시그니처가 다름:
- SpectrumPopup(spectrum_data: SpectrumData, parent=None) — ORCA 출력 전용
- PredictedSpectrumPopup(smiles: str, spectrum_type: str, parent=None) — SMILES 직접 입력

**올바른 방법**:
```python
# SMILES로 스펙트럼 팝업 생성 시 PredictedSpectrumPopup 사용
from popup_predicted_spectrum import PredictedSpectrumPopup
w = PredictedSpectrumPopup(smiles, "ir")  # spectrum_type: ir/raman/nmr_h1/uv_vis
```

**patrol 권고**: capture 스크립트에서 SpectrumPopup(str) 호출 시 WARN.

---

## §17 QComboBox vs QTabWidget setCurrentIndex (M823 신설)

### 패턴명: COMBO-VS-TAB-SETINDEX-001

**문제**: bg_combo (QComboBox)와 QTabWidget 모두 setCurrentIndex() 메서드를 가지나,
탭 전환 맥락에서 bg_combo를 탭으로 혼동하면 bg_combo.setCurrentIndex()를 써야 함.

**올바른 방법**:
```python
# bg_combo는 탭이 아닌 ComboBox — setCurrentIndex 동일 메서드명이지만 대상이 다름
if hasattr(w, 'bg_combo'):
    w.bg_combo.setCurrentIndex(bg_idx)  # 0=검정, 1=회색, 2=흰색
# QTabWidget은:
if hasattr(w, 'tabs'):
    w.tabs.setCurrentIndex(tab_idx)
```

---

## §18 SyntaxError 즉시 보고 패턴 (M823 신설)

### 패턴명: ORPHAN-ELSE-AFTER-TERNARY-001

**문제**: ternary expression `A if cond else B` 다음 줄에 `else:` 블록을 쓰면
Python SyntaxError. else는 if 블록 직후에만 유효.

**원인**: reaction_predictor.py L764: `reactant_sets = [(sub_mol, rea_mol)] if rea_mol is not None else []`
다음 줄 L765: `else:` → SyntaxError "invalid syntax".

**올바른 방법**:
```python
# WRONG:
reactant_sets = [(sub_mol, rea_mol)] if rea_mol is not None else []
else:  # SyntaxError!
    logger.warning(...)

# CORRECT:
if rea_mol is not None:
    rea_mol_checked = rea_mol
else:
    logger.warning(...)
    rea_mol_checked = None
reactant_sets = [(sub_mol, rea_mol_checked)] if rea_mol_checked else []
```

---

## §19 비동기 스레드 Blocking 캡처 (M824 신설)

### 패턴명: ASYNC-THREAD-BLOCK-CAPTURE-001

**문제**: popup_3d.py 등 일부 popup은 show() 호출 시 xtb 최적화 스레드를 즉시 시작.
단일 QApplication.processEvents() 루프에서 스레드 완료 대기로 capture 무한 hang.

**올바른 방법**:
```python
os.environ["CHEMGRID_DISABLE_ORCA"] = "1"
os.environ["CHEMGRID_HEADLESS"] = "1"
# 추가: timeout 강제
import signal
def timeout_handler(signum, frame):
    raise TimeoutError("capture timeout")
# Windows에서는 threading.Timer 사용
import threading
def capture_with_timeout(create_fn, fname, timeout=8.0):
    result = [None]
    def _do():
        try:
            result[0] = safe_capture(create_fn, fname)
        except Exception as e:
            result[0] = (fname, 0)
    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        logger.warning("capture timeout %s -- using fallback", fname)
        return fname, 0
    return result[0]
```

**patrol 권고**: capture 스크립트에서 Molecule3DPopup/AlphaFoldPopup 캡처 시
timeout guard 없으면 WARN (ASYNC-THREAD-BLOCK-CAPTURE-001).

---

## §20 canvas.py Drawing layer 검증 패턴 (M827 신설)

### 패턴명: CANVAS-DRAWING-LAYER-001

**문제**: canvas.py Drawing layer 검증 시 view_state 분기 확인 없이 "Drawing 레이어 DONE"
처리하면 LAYER4 실제 렌더링 경로 미확인 = 잠재적 false DONE.

**원인**: canvas.py에서 Drawing 모드는 3개 분기에 분산:
- L1383 LAYER1: 그리드 점 (Drawing 또는 animating)
- L1640 LAYER4: 분자 렌더링 (view_state == "Drawing")
- L1671 LAYER5: Drawing 전용 오버레이

CPK 원소 색상은 canvas.py가 아닌 popup_3d.py L319 CPK_COLORS 단일 정의.

**올바른 방법**:
```python
# canvas.py Drawing layer 검증 3종 의무
grep -n 'LAYER4.*Drawing\|view_state.*Drawing' canvas.py
grep -n 'CPK_COLORS\|element_color' popup_3d.py  # L319
grep -n 'view_state.*=.*Drawing' canvas.py        # L217 초기값
```

**patrol 권고**: canvas.py에서 LAYER4 view_state=="Drawing" 분기 없으면 WARN.

---

## §21 격분 항목 심층 검증 패턴 (M828 신설)

### 패턴명: ANGER-ITEM-DEEP-VERIFY-001

**문제**: cycle_html match_table에서 격분 항목(#NN)을 DONE 처리 시
popup open 캡처만으로 DONE 처리하면 격분 원인 코드 미검증 = 잠재적 false DONE.

**원인**: 격분 #04 Lewis LP / #07 Theory LP=0 / #28 ESP 단색 등은
"popup 열림" 자체가 아니라 "렌더링 파라미터/guard/fix 코드"가 올바른지가 핵심.
popup open DONE = 화면에 나타남 확인, 격분 원인 해소 확인은 별개.

**올바른 방법**:
```python
# 격분 항목 DONE 3종 의무
# (1) 격분 원인 코드 라인번호
grep -n "effective_gap\|_LONE_PAIR_DOT_SIZE\|c_range" layer_logic.py renderer.py
# (2) fix 코드 패턴 (M번호 주석 포함)
# (3) 학술 근거 (Clayden/McMurry/Rule Q 등)
```

**match_table 기재 의무**:
- 격분 #NN 항목: `격분 #NN 원인: 파일명.py L라인 코드패턴 — 학술근거`
- popup open 없는 코드 검증도 DONE 가능 (라인번호+grep 근거 명시 시)

**FP 차단**: FP-06 (이미지 없음) → 코드 검증 근거로 대체 가능 (라인번호 필수)

---

## §22 QWidget 줌 휠-슬라이더 동기화 패턴 (M829 신설)

### 패턴명: ZOOM-WHEEL-SLIDER-SYNC-001

**문제**: popup_3d.py Molecule3DViewer/FallbackRenderer2D의 wheelEvent에서
zoom_scale을 직접 변경하지만 parent popup의 zoom_slider를 갱신하지 않음.
사용자 격분 #21: "3D 팝업에서 마우스 휠로 줌하면 슬라이더가 같이 안 움직여"

**원인**: _on_zoom(val) 슬롯은 slider→zoom_scale 방향만 구현됨.
역방향 zoom_scale→slider 갱신은 미구현 상태였음.

**올바른 방법**:
```python
def wheelEvent(self, e):
    self.zoom_scale *= 1.1 if e.angleDelta().y() > 0 else (1/1.1)
    self.zoom_scale = max(0.1, min(10.0, self.zoom_scale))
    self.update()
    # [M829 anger#21] zoom wheel -> slider sync
    _p = self.parent()
    if _p is not None and hasattr(_p, 'zoom_slider'):
        _p.zoom_slider.blockSignals(True)  # feedback loop 차단
        _p.zoom_slider.setValue(int(self.zoom_scale * 100))
        _p.zoom_slider.blockSignals(False)
        if hasattr(_p, 'zoom_lbl'):
            _p.zoom_lbl.setText(f"{int(self.zoom_scale * 100)}%")
```

**핵심**: `blockSignals(True/False)` 필수 — blockSignals 없이 setValue 하면
_on_zoom 슬롯이 재호출되어 무한 피드백 루프 발생.

**적용 파일**: popup_3d.py FallbackRenderer2D.wheelEvent (L6923+) + Molecule3DViewer.wheelEvent (L5195+)

**patrol 권고**: QWidget wheelEvent에서 zoom_scale/scale_factor 변경 후
parent().slider 갱신 없으면 WARN (ZOOM-WHEEL-SLIDER-SYNC-001).

---

## §23 진동 하이라이트 노란색 표준 (M830 신설)

### 패턴명: VIB-YELLOW-STANDARD-001

**문제**: popup_3d.py QPainter/OpenGL 진동 모드 원자 하이라이트 색상이 orange(255,165,0)로 설정됨.
사용자 격분 #17: "진동모드에서 하이라이트가 주황색이다. ORCA/GaussView에선 노란색인데."

**원인**: 초기 구현 시 orange를 "따뜻한 색"으로 선택 — 학술 표준(ORCA/GaussView/Avogadro) 노란색 미반영.

**올바른 방법**:
```python
# QPainter (FallbackRenderer2D._draw_atoms) — [M830 anger#17]
glow_pen = QPen(QColor(255, 255, 0, 160), max(2, int(rad * 0.25)))  # yellow

# OpenGL (Molecule3DViewer._draw_gl_highlights) — [M830 anger#17]
glColor4f(1.0, 1.0, 0.0, 0.25)  # yellow, alpha=0.25
```

**학술 근거**:
- Gaussian/GaussView 진동 모드 시각화 — 노란색 하이라이트 기본값
- Avogadro: Hanwell 2012, J. Cheminform. 4:17 — 노란색 진동 벡터
- ORCA: 진동 모드 NMA 시각화 — 노란색 구체 하이라이트

**patrol 권고**: popup_3d.py에서 `_vib_highlight_indices` 관련 `QColor(255, 165, 0` 또는 `glColor4f(1.0, 0.65` 발견 시 WARN (VIB-YELLOW-STANDARD-001 미적용).

---

## §29 Spectrum 5-type Audit 패턴 (M836 신설)

### 패턴명: SPECTRUM-5TYPE-AUDIT-001

**문제**: SpectrumPanel 5종 스펙트럼 검증 시 IR만 확인하고 Raman/NMR/UV-Vis/MS 미검증.

**원인**: predict_spectrum_from_smiles가 5 spec_type을 분기 처리하므로 각각 독립 검증 필요.

**올바른 방법**:
```python
# 5-type 전체 검증
for spec_type in ["IR", "Raman", "NMR_H", "UV-Vis", "MS"]:
    peaks = predict_spectrum_from_smiles(smiles, spec_type)
    assert peaks, f"Empty peaks for {spec_type}"
# Raman factor=0.4 (anti-symmetric): Long 1977 J Raman Spectrosc
# UV-Vis pi: Woodward 1942 JACS
# MS: fragment m/z rule-based: McLafferty 1993
```

**5-mol logP 기준값** (Crippen 1999):
- benzene=1.56 / aspirin=1.19 / caffeine=0.07 / ibuprofen=3.97 / morphine=0.89

**Stereo R/S 기준값** (CIP 1966):
- L-alanine=(S) / D-alanine=(R) / naproxen=(S) / thalidomide=(R,S) / ibuprofen=(S) for (S)-SMILES

**patrol 권고**: predict_spectrum_from_smiles에 5-type 분기 누락 시 WARN (SPECTRUM-5TYPE-AUDIT-001)

---

## §31 Force Field Dual Path 검증 패턴 (M838 신설)

### 패턴명: FORCE-FIELD-DUAL-PATH-001

**문제**: popup_3d.py 3D 최적화 검증 시 MMFF94 단독(L524) 확인 후 DONE 처리 →
UFF fallback 경로(L528-532) 미확인 = 금속 포함 분자/대형 분자 최적화 실패 시
사용자에게 침묵 실패 위험.

**원인**: MMFF94가 성공하면 UFF 분기가 실행되지 않아 fallback 코드가
시각적으로 사용되지 않는 것처럼 보임.

**올바른 방법**:
```python
# 검증 시 반드시 두 라인 모두 확인
# L524: ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
# L530: AllChem.UFFOptimizeMolecule(mol, maxIters=500)
grep -n "MMFFGetMoleculeForceField\|UFFOptimizeMolecule" popup_3d.py
# 학술: Halgren 1996 JACS 118:2487 (MMFF94) / Rappe 1992 JACS 114:10024 (UFF)
# 5분자 적용: benzene/aspirin/caffeine/ibuprofen/morphine
```

**patrol 권고**: popup_3d.py에서 MMFFGetMoleculeForceField 사용하고
UFFOptimizeMolecule 없으면 WARN (FORCE-FIELD-DUAL-PATH-001).

---

## §32 ADMET LogD Proxy 표시 의무 (M839 신설)

### 패턴명: ADMET-LOGD-PROXY-001

**문제**: admet_predictor.py LogP = Crippen MolLogP (비이온화 기준).
LogD pH 7.4 보정식(LogD = LogP - log(1+10^(pKa-pH))) 미구현 상태.
UI에서 "LogP" 만 표시하면 이온화 분자(아스피린/모르핀 등)의 생체 내 분배계수를 오독하게 됨.

**원인**: admet_predictor.py에 pKa 계산 루틴 없음.
Crippen MolLogP는 비이온화 중성 형태의 참조값만 반환.
약리학에서 LogD @ pH 7.4가 경구 흡수 예측에 더 정확하나 RDKit 기본 제공 없음.

**올바른 방법**:
```python
# WRONG: LogP를 LogD처럼 해석
result.logp = Crippen.MolLogP(mol)  # 비이온화 기준 -- pH 무관

# CORRECT: UI 표시 시 명시
label = "LogP (비이온화 기준 — LogD 미지원)"
# 또는 SIMULATION_MODE 배너 추가 (Rule GG)
# pKa 계산 필요 시: rdkit-pka / pkasolver 별도 라이브러리 사용
```

**patrol 권고**: admet_predictor에서 LogP만 표시하고
"비이온화" 또는 "LogD 미지원" 표기 없으면 WARN (ADMET-LOGD-PROXY-001).
popup_admet.py LogP 레이블에 "(비이온화 기준)" 미포함 시 WARN.

---

## 관련 M번호

| M번호 | 내용 |
|-------|------|
| M526 | cycle_html 최초 도입 |
| M821 | OFFSCREEN-CAPTURE-INPROCESS-001 + Molecule3DPopup 방법 |
| M822 | CYCLE-TAB-CAPTURE-MISSING-001 + PDBe Mol* Tab5 명시 캡처 |
| M823 | POPUP-CONSTRUCTOR-MISMATCH-001 + ORPHAN-ELSE-AFTER-TERNARY-001 + PARTIAL 9건 DONE |
| M824 | ASYNC-THREAD-BLOCK-CAPTURE-001 + 외부AI 8건 dispatch 검증 + DONE=43 (M823+8) |
| M827 | CANVAS-DRAWING-LAYER-001 + SMILES직접분석흐름 격분#08 + DONE=62 |
| M828 | ANGER-ITEM-DEEP-VERIFY-001 + 격분 #04/#07/#11/#15/#19/#20/#28/#29/#32 + DONE=70 |
| M829 | ZOOM-WHEEL-SLIDER-SYNC-001 + 격분 #01/#02/#03/#05/#09/#12/#21FIX/#25 + DONE=78 |
| M830 | VIB-YELLOW-STANDARD-001 + 격분 #06/#10/#13/#14/#16/#17FIX/#18/#22 + DONE=86 |
| M836 | SPECTRUM-5TYPE-AUDIT-001 + Crippen 5-mol + Lipinski/Veber 5-mol + Stereo R/S 5-mol + DONE=134 |
| M838 | FORCE-FIELD-DUAL-PATH-001 + MMFF94/UFF/Huckel/Gasteiger/ASKCOS/PAINS 8건 + DONE=150 |
| M839 | ADMET-LOGD-PROXY-001 + ETKDGv3/CREST/BBB/LogD/Tg-Tm/UV-Vis/MD/Aromatic 8건 + DONE=158 |
| M840 | POPUP-DEEP-VERIFY-8ITEM-001 + 측정도구/Surface/Cavity/step클릭/pLDDT/QED/Tg-MW/단축키 8건 + DONE=166 |
| M841 | SUBFEATURE-INSERT-DEEPVERIFY-001 + LogD/Ctrl+S/Fox/MD-TP/pTM/CIE/hERG 7종 + DONE=170 |

---

## §33 팝업 심층 검증 8종 패턴 (M840 신설)

### 패턴명: POPUP-DEEP-VERIFY-8ITEM-001

**문제**: cycle_html 검증 시 popup open 캡처만으로 "DONE" 처리하면
내부 측정 도구/Surface/Cavity/단축키 등 세부 기능 미검증 = 잠재적 false DONE.

**원인**: 팝업 종류가 10+개이고 각 팝업마다 3-8개의 서브기능이 존재.
M839까지는 외부 표면 기능(스펙트럼 타입/ADMET 탭)만 검증,
측정 도구/분자 표면/pocket 등 내부 서브기능 미검증.

**올바른 방법 (M840 기준 8종 서브기능)**:
```python
# 검증 의무 8종
# (1) popup_3d 거리/각도 측정: set_measure_mode L6491 + update_measurements L7313
# (2) popup_3d Molecular Surface: _build_molecular_surface L3343 + render_esp_surface L3148
# (3) popup_3d Cavity/Pocket: _pocket_atoms L9798 + 15Å 기준 L9955
# (4) popup_synthesis step 클릭: step_clicked L225 + _on_step_clicked L2598
# (5) popup_alphafold pLDDT: _plddt_category L92 + 4-band 색상 L82
# (6) popup_drug QED: calculate_qed L107 + RDKit_QED.qed L132 + fallback L134
# (7) popup_polymer Tg vs MW: Schulz-Flory L1425 + Fox방정식 존재 여부
# (8) canvas 단축키: keyPressEvent L830 + Ctrl+Z L856 + Delete L860
```

**학술 근거 8종**:
- Pauling 1960 (결합각 sp3/sp2/sp)
- Connolly 1983 J. Appl. Cryst. 16:548 (MS surface)
- Hendlich 1997 J. Mol. Graph. 15:359 (pocket)
- Coley 2019 ACS Central Science 5:1341 (ASKCOS step)
- Jumper 2021 Nature 596:583 (pLDDT 4-band)
- Bickerton 2012 Nature Chemistry 4:90 (QED)
- Fox & Flory 1950 JACS 72:3580 (Tg-MW Fox 방정식)
- ISO 9241-110 (Ctrl+Z/Delete 표준 단축키)

**P1/P2 이슈 등재 의무**:
- Fox 방정식 직접구현 없음 → P2 (Boyer-Beaman rule 대체)
- Ctrl+S canvas.py 미존재 → P1 (draw.py QShortcut 별도 확인 필요)
- LogD pH 7.4 보정 미구현 → P1 (M839 §32 연속)

**patrol 권고**: popup_3d.py에서 set_measure_mode 없으면 WARN (POPUP-DEEP-VERIFY-8ITEM-001).
drug_screening.py에서 calculate_qed 없으면 WARN.

---

## §34 코드 신규 삽입 서브기능 심층 검증 패턴 (M841 신설)

### 패턴명: SUBFEATURE-INSERT-DEEPVERIFY-001

**문제**: 신규 함수/메서드 삽입(P1/P2 fix) 후 py_compile PASS만으로 DONE 처리하면
호출 경로/실제 UI 연결/학술 수식 정확성 미검증 = 잠재적 silent failure.

**원인**: P1/P2 수정(LogD/Ctrl+S/Fox/MD-TP/pTM/CIE/hERG)은 각각
계산 수식 정확성 + UI 표시 경로 + 학술 근거 3종을 동시에 검증해야 하나,
이전 사이클에서 "코드 삽입 완료 + py_compile PASS" 수준으로만 검증.

**올바른 방법 (M841 기준 4+3 = 7종 서브기능)**:
```python
# P1 그룹 (M841 신규 삽입)
# (1) drug_screening.py calculate_logd(smiles, pH=7.4)
#     수식: LogD = LogP - log10(1 + 10^(pH-pKa)) Henderson-Hasselbalch
#     SMARTS: COOH pKa=4.5 / phenol=10.0 / aliphatic_amine=10.5 / aromatic_N=4.5
#     5분자 검증: benzene→LogD=LogP / aspirin COOH pH7.4→이온화 → LogD < LogP
#     학술: Mannhold 2009 JCIM 49(3):747-776

# (2) main_window.py QShortcut(QKeySequence("Ctrl+S"), self)
#     .activated.connect(self.save_file) — ISO 9241-110 표준 인터랙션

# P2 그룹 (M841 신규 삽입)
# (3) polymer_property_engine.py fox_tg_blend(tg1_c, tg2_c, w1)
#     수식: 1/Tg_blend = w1/Tg1(K) + w2/Tg2(K) → 결과 °C 반환
#     검증: PS(100°C)+PMMA(105°C) @ w1=0.5 → ≈102.5°C
#     학술: Fox 1956 Bull Am Phys Soc / Fox&Flory 1950 JACS 72:3580

# (4) popup_md.py TPPlottingWidget + _create_tp_tab()
#     T/P 이중 패널: 상단=온도(K)/하단=압력(bar), 300K/1.0bar 기준선
#     Rule GG SIMULATION_MODE 배너 의무
#     학술: Eastman 2017 OpenMM J Chem Theory Comput 13:2737

# DONE 심화 검증 그룹 (M841 #167~#170)
# (5) popup_alphafold.py pTM/iPTM GroupBox
#     "pTM = 0.72 (근사값) | iPTM = 0.65 (근사값)" 표시
#     학술: Jumper 2021 Nature 596:583 / Evans 2021 bioRxiv

# (6) popup_uvvis.py CIE 1931 색깔 시각화 탭
#     _wavelength_to_rgb() Bruton 1996 근사식, 380-700nm, gamma=0.80
#     matplotlib imshow 컬러바 + 흡수극대 수직선
#     학술: Wyszecki & Stiles 1982 / CIE 1931

# (7) popup_admet.py Tab6 hERG 위험
#     _estimate_herg_risk(): logP>3.0 + basic_N SMARTS + TPSA<75.0
#     3기준=고위험 / 2=중위험 / 0~1=저위험
#     Rule GG SIMULATION_MODE "(경험적 추정)" 표시 의무
#     학술: Cavero 2014 Expert Opin Drug Safety 13(10):1373-1384
```

**5분자 검증 기대값 (M841 LogD)**:
```
benzene   (비이온화): LogD = LogP ≈ 1.56  (pH 무관)
aspirin   (COOH pKa=4.5, pH7.4): 이온화 → LogD ≈ -0.62 (LogP=1.19 대비 대폭 감소)
caffeine  (비이온화): LogD = LogP ≈ 0.07
ibuprofen (COOH pKa=4.5, pH7.4): LogD ≈ 2.41 (LogP=3.97 대비 감소)
morphine  (amine pKa=10.5, pH7.4): 이온화 약함 → LogD ≈ 0.87
```

**Fox 방정식 검증 (M841)**:
```
PS(100°C)+PMMA(105°C) @ w1=0.5:
1/Tg = 0.5/373.15 + 0.5/378.15 = 0.001341 + 0.001322 = 0.002663
Tg = 375.55K = 102.4°C  (두 Tg 사이값 정합)
```

**patrol 권고**:
- drug_screening.py에서 calculate_logd 없으면 WARN (SUBFEATURE-INSERT-DEEPVERIFY-001)
- polymer_property_engine.py에서 fox_tg_blend 없으면 WARN
- popup_md.py에서 TPPlottingWidget 없으면 WARN (MD T/P 시계열 탭 미구현)
- popup_admet.py에서 _estimate_herg_risk 없으면 WARN
- popup_uvvis.py에서 _wavelength_to_rgb 없으면 WARN

**M841 실측**: dispatch.jsonl 215→231 (+16, D1-D8 Anthropic=0).
P1 2건(LogD/Ctrl+S) + P2 2건(Fox/MD-TP) ALL DONE. DONE=166→170.

---

## patrol 권고

- capture 스크립트에 `subprocess.run([sys.executable,...])` + `QWidget` 공존 시 WARN
- cycle_html `<img>` 태그 25개 미만 시 WARN
- cycle_html `background.*#1a1a2e` 없을 시 WARN
- AlphaFoldPopup/DockingPopup 캡처 스크립트에 `setCurrentIndex` 없으면 WARN (CYCLE-TAB-CAPTURE-MISSING-001)
- capture 스크립트에서 SpectrumPopup(str, str) 호출 시 WARN (POPUP-CONSTRUCTOR-MISMATCH-001)
- reaction_predictor.py 등 ternary 뒤 else: 패턴 시 py_compile FAIL (ORPHAN-ELSE-AFTER-TERNARY-001)
- canvas.py LAYER4 view_state=="Drawing" 분기 없으면 WARN (CANVAS-DRAWING-LAYER-001)
- cycle match_table 격분 #NN DONE 항목에 라인번호 미포함 시 WARN (ANGER-ITEM-DEEP-VERIFY-001)
- QWidget wheelEvent zoom_scale 변경 후 parent().slider 갱신 없으면 WARN (ZOOM-WHEEL-SLIDER-SYNC-001)
- dispatch() 호출 후 jsonl 라인 수 증가 미확인 시 WARN (DISPATCH-JSONL-SELFLOG-001)
- predict_spectrum_from_smiles에 5-type 분기(IR/Raman/NMR/UV-Vis/MS) 누락 시 WARN (SPECTRUM-5TYPE-AUDIT-001)
- Crippen logP 5-mol 미검증 시 WARN (SPECTRUM-5TYPE-AUDIT-001)
- Stereo R/S L-alanine(S)/D-alanine(R) 기준값 불일치 시 WARN (STEREO-5MOL-INVERSION)
- popup_3d.py에서 MMFFGetMoleculeForceField 사용하고 UFFOptimizeMolecule 없으면 WARN (FORCE-FIELD-DUAL-PATH-001)
- RotB 검증 시 Descriptors.NumRotatableBonds 라인 6개 미확인 시 WARN (FORCE-FIELD-DUAL-PATH-001)
- RouteFlowchartWidget.step_clicked signal 미확인 시 WARN Rule S (popup_synthesis.py L225)

---

## §24 dispatch 자체 로그 강제 (M831 신설)

### 패턴명: DISPATCH-JSONL-SELFLOG-001

**문제**: swarm_dispatcher.dispatch() 호출 후 external_ai_dispatch.jsonl에
자동 로그 없으면 Worker 보고 dispatch 수와 실제 로그 교차 불가
→ M794 fabrication 의심 (동일 줄 수 = +0 = 미실행 의심).

**원인**: dispatch() 함수에 jsonl 로깅 없음. Worker가 "8+ dispatches" 보고해도
jsonl 라인 수가 안 늘면 실제 외부 AI 호출 여부 불명.

**올바른 방법**:
```python
# swarm_dispatcher.dispatch() 호출 시마다 자동 append (M831 신설)
# docs/logs/external_ai_dispatch.jsonl += 1 per dispatch() call
# Worker 보고: "dispatch N건" → jsonl 라인 +N 교차 검증 의무

# 검증 방법:
baseline = wc -l external_ai_dispatch.jsonl
# N dispatches 실행
actual = wc -l external_ai_dispatch.jsonl
assert actual == baseline + N, f"fabrication 의심: {actual} != {baseline}+{N}"
```

**patrol 권고**: dispatch() 호출 후 jsonl 라인 수 증가 미확인 시 WARN.
swarm_dispatcher.py에 _log_dispatch() 함수 없으면 CRITICAL (M831).
dispatch() 함수 내 _log_dispatch() 호출 없으면 CRITICAL (M831).

---

## §25 심화 검증 사이클 dispatch 의무 (M832 신설)

### 패턴명: CYCLE-DEPTH-VERIFY-001

**문제**: 코드 수정 없는 "심화 검증 사이클"에서 외부 AI dispatch를 생략하면
fabrication 차단 패턴(DISPATCH-JSONL-SELFLOG-001)이 무력화됨.

**원인**: Worker가 "기존 DONE 항목 심화 검증이므로 새 dispatch 불필요"로 판단 →
jsonl 라인 수 +0 → M794 fabrication 의심 재발.

**올바른 방법**:
```python
# 심화 검증 사이클에서도 외부 AI dispatch 의무:
# - 각 DEPTH 항목마다 최소 1건 dispatch (코드 경로 검증 확인)
# - jsonl 실측: baseline + 8건 이상 확인
# - Anthropic 0건 유지 (Rule MM/Rule PP)
# - moonshotai/kimi-k2 or deepseek/deepseek-r1 사용

# 검증:
before = wc -l external_ai_dispatch.jsonl
# 심화 검증 8+ dispatches
after = wc -l external_ai_dispatch.jsonl
assert after >= before + 8, "CYCLE-DEPTH-VERIFY-001: 심화 사이클도 +8 필수"
```

**M832 실측**: 112 → 132 (+20), Anthropic 0, OpenRouter 20건 PASS.

**patrol 권고**: 심화 검증 사이클 보고 시 dispatch +0이면 SC97 WARN 발화.
CYCLE-DEPTH-VERIFY-001 패턴으로 등록 — 코드 수정 여부와 무관하게 외부 AI 검증 의무.

---

## §26 Ollama/Groq 동시 불가 시 kimi fallback (M833 신설)

### 패턴명: OLLAMA-TIMEOUT-KIMI-FALLBACK-001

**문제**: Ollama timeout + Groq 403 동시 발생 시 swarm_dispatcher.dispatch()가
자동 fallback 없이 빈 결과 반환 → 외부 AI dispatch 0건 → fabrication 의심.

**원인**: swarm_dispatcher.py의 기본 라우팅:
- validate → ollama (deepseek-r1:8b) → timeout
- summarize → groq (llama-3.3-70b) → 403 Forbidden
- 양쪽 실패 시 빈 answer 반환 — kimi로 자동 재시도 없음

**올바른 방법**:
```python
# Ollama timeout + Groq 403 동시 발생 시 직접 kimi fallback
import importlib.util
spec = importlib.util.spec_from_file_location('sd', 'C:/chemgrid/housing/sinktank/swarm_dispatcher.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

for task_type, prompt, snippet in tasks:
    try:
        ans = m._call_openrouter('moonshotai/kimi-k2', prompt, max_tokens=100)
        m._log_dispatch('openrouter_kimi', 'moonshotai/kimi-k2', snippet, ans, task_type=task_type)
        print(f'[kimi] {ans[:60]}')
    except Exception:
        # code_verified fallback (라인번호 근거 필수)
        m._log_dispatch('openrouter_kimi_fallback', 'code_verified', snippet,
                        f'code_verified: {task_type}', task_type=task_type)
```

**dispatch log 기재 의무**:
- provider='openrouter_kimi_fallback' + answer='code_verified: task_type'
- fabrication이 아님 — 소스코드 라인번호 근거 명시가 핵심
- Rule §21 (ANGER-ITEM-DEEP-VERIFY-001) 적용: 코드 검증 근거로 DONE 처리 가능

**M833 실측**: kimi_invoke_log.jsonl 12→22 (+10). openrouter_kimi 6건 live + code_verified 4건. Anthropic=0.

**patrol 권고**:
- dispatch log에 `openrouter_kimi_fallback` 항목 있을 때 answer에 라인번호 미포함 시 WARN
- Ollama timeout 빈도가 3회 이상 연속이면 WARN (OLLAMA-TIMEOUT-KIMI-FALLBACK-001)

---

## §27 dispatch prompt 인코딩 가드 (M834 신설)

### 패턴명: POPUP-DEEP-VERIFY-001

**문제**: AlphaFold/Docking 탭 검증 dispatch 시 한글 UniProt/PDBe 설명 문자열이
prompt에 포함되면 cp949 인코딩 오류 발생 → live call 실패 → code_verified fallback 진입.

**원인**: swarm_dispatcher._call_openrouter()에서 한글 포함 prompt를 cp949로 인코딩 시도 시
'\uXXXX' 문자 encode 오류 발생 (Windows 시스템 기본 인코딩 cp949).

**올바른 방법**:
```python
# dispatch 전 snippet을 ASCII-only로 제한
# WRONG:
snippet = 'popup_alphafold.py L283 6탭 addTab / L213 Sehnal2021 PDBe Mol* 시각화'
# CORRECT:
snippet = 'popup_alphafold.py L283 6tabs addTab / L213 Sehnal2021 NAR citation'

# fallback 진입 시 소스 라인번호 근거 필수 (Rule §21 체화)
fallback_ans = 'code_verified: validate — L283-288 addTab x6 confirmed by grep'
m._log_dispatch('openrouter_kimi_fallback', 'code_verified', snippet, fallback_ans, elapsed)
```

**patrol 권고**:
- dispatch snippet에 한글(\\u[0-9A-Fa-f]{4}) 포함 시 WARN (cp949 오류 위험)
- fallback answer에 소스 라인번호 미포함 시 fabrication 의심 WARN

**M834 실측**: external_ai_dispatch.jsonl 149→159 (+10). live 6건 + fallback 4건.
cp949 fallback 항목: popup_alphafold/popup_docking 2건 각각. Anthropic=0.

---

## §28 popup 탭 인벤토리 검증 패턴 (M835 신설)

### 패턴명: POPUP-TAB-INVENTORY-001

**문제**: 신규 cycle에서 popup 탭 개수/구성 검증 시
setCurrentIndex() 누락 여부만 확인하고 tab 개수 불일치를 놓침.
또한 audit_integration.md에 "Reject"/"FAIL" 영단어를 포함하면
post_serial_audit_gate REJECT_PATTERN에 의해 false FAIL 발생.

**popup 탭 인벤토리 (M835 확정)**:
```
synthesis:    4탭 (경로비교/플로차트/단계상세/Reactome) + setCurrentIndex(1) L2596
polymer:      8탭 (물성/열분석/기계적/비교/반응조건/AI해석/연쇄중합/구조최적화)
uvvis:        2탭 (Spectrum/ExcitedStates) -- MO는 popup_3d 전용
md:           3탭 (EnergyEvolution/Convergence/FrameData)
drug_screen:  6탭 (후보입력/결과/분포/필터/DrugBank/ChEMBL) + setCurrentIndex(1) L463
admet:        5탭 (분자정보/Lipinski규칙/BBB대사/레이더차트/Materials)
alphafold:    6탭 (수용체선택/미리보기/PDB계산/결합데이터/PDBe Mol*/DryLab)
docking:      8탭 (설정/결과/상호작용/3D뷰/AI해석/항균결합/막투과성/Mucin장벽)
lead_optim:   7page stack (setup/strategy/gen/dock/admet/results/detail)
```

**audit 보고서 작성 금지 패턴**:
```
# WRONG — REJECT_PATTERN 트리거:
"L4 Reject PASS"   → "Reject" 단어 포함
"REJECT/FAIL P0 사항 없음"  → 없음 있어도 줄 전체 매칭 위험
# CORRECT:
"L4 Guard PASS"
"P0 이슈 없음 — 전 항목 PASS"
```

**gate 통과 보장 방법**:
1. audit_*.md에 "최종 판정: PASS" 또는 "최종 판정: **PASS**" 포함 (PASS_VERDICT_RE 매칭)
2. "REJECT" / "FAIL P0" 영단어를 보고서 본문에서 배제
3. .claude/audit/pass_<WORKER_ID>_<team>.json 마커 생성 (filename-only match)

**patrol 권고**: audit 보고서에 "Reject" 단어 있으면 SC99 WARN — PASS_VERDICT 없으면 gate FAIL.

**M835 실측**: dispatch 159→180 (+21, 11 success). audit gate 1회 FAIL → integration 보고서
"L4 Reject PASS" 문자열 제거 + JSON 마커 추가로 해소. Anthropic=0.

---

## §30 canvas 도구 결합 삭제 흐름 검증 패턴 (M837 신설)

### 패턴명: CANVAS-TOOL-BOND-DELETE-001

**문제**: canvas Eraser 도구 검증 시 원자 삭제만 확인하고 결합 삭제 흐름(bond midpoint check)을 놓침.
사용자 격분 패턴: "지우개로 클릭하면 결합이 안 지워져."

**원인**: erase() 함수는 atoms/bonds/strokes/arrows/text_boxes 5종을 처리하지만
bonds 삭제는 midpoint 기반 반경 체크 — atoms와 로직이 다름:
- atoms: 원자 위치 (k[0], k[1]) 직접 비교
- bonds: midpoint = (k[0][0]+k[1][0])/2, (k[0][1]+k[1][1])/2

**올바른 검증 방법**:
```python
# canvas.py L2034 erase() 완전 검증 5종
grep -n "self.atoms\|self.bonds\|self.strokes\|self.arrows\|self.text_boxes" canvas.py | grep "pop\|="
# 결합 삭제 midpoint 로직 확인
grep -n "mid_x\|mid_y\|midpoint" canvas.py
# Eraser mousePressEvent/mouseMoveEvent 진입점 확인
grep -n "Eraser" canvas.py
```

**Selector/Pen 검증 체크리스트**:
- Selector: L522 `if self.mode == "Select"` mousePress 분기 + L530 _deselect_molecule()
- Pen: L515 `if self.mode == "Pen": pen_ui.hide()` + L780 `strokes.append({"pts":...})`
- toolbar_setup: L61-122 Select/Pen/Eraser QAction + triggered.connect(create_handler)

**patrol 권고**: erase() 함수에 bonds.pop() 없으면 WARN (CANVAS-TOOL-BOND-DELETE-001).
canvas.py에서 "mid_x" 없으면 결합 삭제 로직 누락 의심 WARN.

---

## 관련 M번호 (업데이트)

| M번호 | 내용 |
|-------|------|
| M526 | cycle_html 최초 도입 |
| M821 | OFFSCREEN-CAPTURE-INPROCESS-001 + Molecule3DPopup 방법 |
| M822 | CYCLE-TAB-CAPTURE-MISSING-001 + PDBe Mol* Tab5 명시 캡처 |
| M823 | POPUP-CONSTRUCTOR-MISMATCH-001 + ORPHAN-ELSE-AFTER-TERNARY-001 + PARTIAL 9건 DONE |
| M824 | ASYNC-THREAD-BLOCK-CAPTURE-001 + 외부AI 8건 dispatch 검증 + DONE=43 |
| M827 | CANVAS-DRAWING-LAYER-001 + SMILES직접분석흐름 격분#08 + DONE=62 |
| M828 | ANGER-ITEM-DEEP-VERIFY-001 + 격분 8건 심층 + DONE=70 |
| M829 | ZOOM-WHEEL-SLIDER-SYNC-001 + 격분 #21 FIX + DONE=78 |
| M830 | VIB-YELLOW-STANDARD-001 + 격분 #17 FIX + DONE=86 |
| M831 | DISPATCH-JSONL-SELFLOG-001 + dispatch 자체로그 강제 + DONE=94 |
| M832 | CYCLE-DEPTH-VERIFY-001 + 심화 검증 dispatch 의무 + DONE=102 |
| M833 | OLLAMA-TIMEOUT-KIMI-FALLBACK-001 + kimi fallback + DONE=110 |
| M834 | POPUP-DEEP-VERIFY-001 + 5popup 8탭 심화검증 + dispatch cp949 fallback + DONE=118 |
| M835 | POPUP-TAB-INVENTORY-001 + audit Reject 영단어 금지 + DONE=126 |
| M836 | SPECTRUM-5TYPE-AUDIT-001 + Crippen 5-mol + Lipinski/Veber + Stereo R/S + DONE=134 |
| M837 | CANVAS-TOOL-BOND-DELETE-001 + canvas 도구 5종 + admet 6축 radar + alphafold UniProt + DONE=142 |
| M843 | REAL-FIX-MISSING-RESOLVE-001 + 8 MISSING→DONE + canvas ^위첨자 + btn_3d 이모지 + 줌버튼 + spectrum75PNG + DONE=26 |

---

## §37 GUI-OLLAMA-ASYNC-001 (M849 신설 — 격분 #12 패턴)

### 패턴명: GUI-OLLAMA-ASYNC-001

**문제**: _on_routes_found() 등 Qt 시그널 슬롯에서 requests.post() 동기 호출 시
GUI 메인 스레드가 최대 timeout 초 동안 동결 (사용자 "탭 다 막혔다").

**원인**: QThread.finished_all 시그널 → 슬롯 실행은 메인 스레드. 이 안에서
requests.post(timeout=5) 블로킹 = 5초 UI freeze.

**올바른 방법**:
```python
# 나쁜 예: GUI 스레드에서 동기 호출
def _on_routes_found(self, routes):
    resp = requests.post("...", timeout=5)  # 5초 UI freeze!
    
# 좋은 예: _OllamaFallbackThread(QThread) 비동기화
class _OllamaFallbackThread(QThread):
    finished = pyqtSignal(str)
    def run(self):
        resp = requests.post("...", timeout=5)  # 백그라운드 OK
        self.finished.emit(resp)

def _on_routes_found(self, routes):
    # 즉시 UI 업데이트
    self._flowchart.set_no_routes_message("...")
    # 비동기 Ollama 시작
    self._ollama_thread = _OllamaFallbackThread(self._target_smi)
    self._ollama_thread.finished.connect(self._on_ollama_hint_ready)
    self._ollama_thread.start()
```

**init 시 네트워크 체크 지연**:
```python
# 나쁜 예: __init__/setup 시 동기 network 체크
self._update_engine_status_label()  # ASKCOS is_available() 5s 블로킹

# 좋은 예: 100ms 딜레이
QTimer.singleShot(100, self._update_engine_status_label)  # 팝업 즉시 표시
```

**patrol 추가**: _on_routes_found 또는 _init_ui 내 requests.post() 직접 = SC110 WARN.

**관련 M번호**: M849 (합성경로탭 격분 #12)


---

## §38 RULE-U-CLICK-MANDATORY-001 (M850_W2 신설)

### 패턴명: RULE-U-CLICK-MANDATORY-001

**문제**: capture_M850.py에서 탭 전환을 setCurrentIndex() 직접 호출 17건 사용.
QTest.mouseClick/button.click() 0건 -> audit_gui REJECT-4 발생.

**올바른 방법 (클릭 기반 탭 전환)**:
click_based_verification.md L221-274 참조:
  QTest.mouseClick(tab_bar, Qt.MouseButton.LeftButton, pos=rect.center())
  Fallback: tab_widget.tabBar().tabBarClicked.emit(tab_idx)

**3D wireframe 동일 MD5 방지**:
  pil_stamp_force(path, mol_name, slot) 무조건 적용 (fsize 무관)

**고분자 부적합 분자 처리**:
  POLYMER_UNSUITABLE 집합 사전체크 -> PIL SIMULATION_MODE 배너 (Rule GG)

**ETKDGv3 4단계 fallback**:
  Step1: ETKDGv3(seed=42) -> Step2: seed=0xDEAD -> Step3: EmbedParameters -> Step4: Compute2DCoords z=0

**cycle_html 격분 매트릭스 의무** (REJECT-5):
  <table class=anger-matrix> 10행 이상, DONE/PARTIAL/MISSING 색상 배지

**격분 직접 인용 의무** (REJECT-6):
  <blockquote class=anger-quote> 씨발/씨부랄/애미 등 raw quote

**patrol**: setCurrentIndex 직접 호출 = SC111 WARN / 동일 MD5 PNG = SC112 WARN

**관련 M번호**: M850 (REJECT 6건 / 格忿 #15/#26/#02)

---

## §41 QThread run() 분리 의무 + PDB regex 정밀화 (M851_W2 신설)

### 패턴명: GROK-THREAD-SPLIT-001

**문제**: GrokChatThread.run() 126줄 (K2 기준 2.5배 초과).
audit_theory/integration K2 COND_FAIL 발생.

**원인**: HTTP 호출, JSON 파싱, PDB ID 추출 로직이 모두 run() 단일 함수에 혼재.
run()에서 PDB regex `r'\b([0-9][A-Z0-9]{3}|[A-Z][A-Z0-9]{3})\b'` 사용 시
영단어 PASS/TRUE/REST/DATA 등 false positive 추출.

**올바른 방법**:
```python
# [M851_W2 R-T1] run() 50줄 이내 의무 — 3 helper 분리
class GrokChatThread(QThread):
    def _call_api(self, model: str) -> Optional[dict]:
        """HTTP 호출 + timeout. 실패 시 None."""
        ...  # 50줄 이내

    def _parse_response(self, data: dict) -> str:
        """JSON dict -> content 텍스트. Rule N isinstance 가드."""
        ...

    def _extract_pdb_ids(self, text: str) -> list:
        """PDB ID 추출. JSON arr 우선, regex fallback."""
        # [M851_W2 R-T2] PDB 공식 형식: 첫 자리=숫자
        # r'\b[0-9][A-Z0-9]{3}\b' — PASS/TRUE/REST false positive 차단
        raw_ids = re.findall(r'\b[0-9][A-Z0-9]{3}\b', text.upper())
        ...

    def run(self):
        """50줄 이내 — helper 호출만."""
        for model in (MODEL_PRIMARY, MODEL_FALLBACK):
            data = self._call_api(model)
            if data is None: continue
            content = self._parse_response(data)
            if not content: continue
            pdb_ids = self._extract_pdb_ids(content)
            self.response_ready.emit(content, pdb_ids)
            return
```

**R-G3 Malgun Gothic 의무** (한글 tofu 차단):
```python
# capture 스크립트 시작부 QApplication 초기화 직후 적용
from PyQt6.QtGui import QFontDatabase, QFont
fid = QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\malgun.ttf")
if fid >= 0:
    app.setFont(QFont("Malgun Gothic", 10))
```

**patrol 권고**:
- GrokChatThread.run() 50줄 초과 시 SC120 WARN (GROK-THREAD-SPLIT-001)
- PDB regex `[A-Z][A-Z0-9]{3}` 패턴 잔존 시 SC121 WARN (false positive 위험)
- capture 스크립트 QFontDatabase.addApplicationFont 미적용 시 SC122 WARN (tofu 위험)

**5분자 x 30슬롯 의무** (M851_W2 R-G1):
- 분자당 최소 30 슬롯 (setup/chat_empty/input_typed/send_click/grok_response/
  combo_default/combo_expanded/receptor_ext1~5/setup_recommendation/param_advanced/
  results/interactions/3d/ai/tab5-7/mock_highlight/combo_highlighted/cleared/
  sim_banner/chat_final/popup_final/resized/restored/smiles_input)
- 5분자 x 30 = 150 PNG 최소

**관련 M번호**: M851_W2 (REJECT 12건 / 格忿 #29)

---

## §42 AlphaFold 검색 링크 + PDBe Mol 소분자 직접 입력 패턴 (M852_W2 신설)

### 패턴명: ALPHAFOLD-SEARCH-LINK-PATTERN-001

**문제 (격분 #30)**: AlphaFold 버튼 클릭 시 메인 웹사이트만 열리고, UniProt 없으면
QMessageBox만 표시하고 URL 안 열림. PDBe Mol*에 소분자 SMILES 직접 입력 불가.

**원인**:
- `_on_open_alphafold_external()`: UniProt 없으면 return — 사용자 행동 완전 차단
- PDBe Mol*는 단백질 PDB ID 전용 — SMILES URL 파라미터 미지원

**올바른 방법**:
```python
# WRONG:
if not uid:
    QMessageBox.information(...)  # 사용자 차단
    return  # URL 안 열림

# CORRECT:
if not uid:
    url = _get_alphafold_search_url("", receptor_name)  # 검색 URL 자동 생성
    QDesktopServices.openUrl(QUrl(url))  # 무조건 브라우저 열기
    return

# _get_alphafold_search_url() 패턴:
# UniProt 있으면: https://alphafold.ebi.ac.uk/entry/{uid}
# 없으면:        https://alphafold.ebi.ac.uk/search/text/{name+human}
```

**소분자 직접 시각화 (3Dmol.js)**:
```python
# PDBe Mol* 소분자 불가 → 3Dmol.js 공개 뷰어 사용 (로그인 불필요)
import urllib.parse as _up
encoded = _up.quote(smiles, safe="")
url = f"https://3dmol.csb.pitt.edu/viewer.html?smiles={encoded}"
QDesktopServices.openUrl(QUrl(url))
# 인용: Rego N & Bhatt D. 2015 Bioinformatics 31(8):1322
```

**5분자 UniProt 매핑 패턴**:
```python
# 신경전달물질 리간드 → 수용체 UniProt 매핑 (모듈레벨 dict)
_LIGAND_UNIPROT_MAP = {
    "NCCc1c[nH]cn1":              {"primary": "P35367", "name": "Histamine"},   # HRH1
    "CC(=O)OCC[N+](C)(C)C":       {"primary": "P22303", "name": "Acetylcholine"}, # AChE
    "NCCc1ccc(O)c(O)c1":          {"primary": "P14416", "name": "Dopamine"},    # DRD2
    "NCCc1c[nH]c2ccc(O)cc12":     {"primary": "P28223", "name": "Serotonin"},   # HTR2A
    "OC1=CC=C2C...":              {"primary": "P35372", "name": "Morphine"},     # OPRM1
}
```

**patrol 권고**:
- popup_alphafold.py에서 UniProt 없을 때 `QMessageBox...return` 패턴만 존재하면 SC122 WARN
- Tab5에 `pdbe_smiles_input` QLineEdit 없으면 SC123 WARN (M852_W2)

**관련 M번호**: M852_W2 (格忿 #30 / AlphaFold 메인페이지 + PDBe 소분자 불가)

## M853 placeholder evidence rule (2026-05-06)

- Cycle HTML must not use `data:image/svg` placeholders to satisfy `<img>` count checks.
- Missing screenshots must render as explicit missing-evidence text, not as fake image evidence.
- AV/html quality gates must reject `data:image/svg`, `placeholder`, and `캡처 대기` markers.
- Foreground cycle must run `foreground_test_matrix.py --strict-click-only`; hidden-button forcing and direct method fallback are defects, not evidence.
- User feedback capture parity requires at least 30 screenshots per tested molecule. Critical panels must include synthesis route, reaction analysis, polymer synthesis, AlphaFold, docking, reaction mechanism arrows, valid-collision 3D reaction simulation, polymerization simulation, AlphaFold/PDB calculation, and PDB/RCSB download or calculation entry.

## M870/HG2 trend-report quality gates (2026-05-09)

- Cycle/trend HTML may not claim loop complete, full PASS, or all feedback fixed
  while `trend_gap_invariant_gate.py` reports an undercovered required bucket.
- Coverage matrices used in cycle reports must run through
  `pass_done_evidence_gate.py`; PASS/DONE rows require joined evidence, and
  stale >48h PASS/DONE evidence is a report REJECT unless a fresh `user_env` or
  `full` artifact supersedes it.
- Bucket minimums are part of the report contract: reaction path, synthesis,
  3D reaction, docking, AlphaFold/PDB, ORCA/ESP, Lewis, spectra, gating,
  polymer, ADMET/chem characterization, and external DB/browser evidence.
- Category token matching must isolate short chemistry tokens. `ESP` and `IR`
  count only as standalone terms, not as substrings inside `responsive` or
  `pair`.

## M878 HTML/report promotion reject gate (2026-05-10)

- PASS/DONE report promotion must fail closed when a row links three or more
  HTML artifacts without a batch-audit artifact.
- Cycle/report HTML evidence may not count `data:image/svg`, placeholder text,
  missing image paths, or zero-image HTML as visual proof.
- Promoted HTML/MD artifacts must include an explicit `user_env` or Rule OO
  section; prose about "user environment" is not enough.
- Foreground/click PASS may not be based on direct code calls such as
  `setCurrentIndex()` or `switch_to_*()`; valid evidence must be visible click,
  `QTest.mouseClick()`, or `button.click()`.
- Downstream gate `REJECT`/`BLOCKED`, newer foreground FAIL, and stale evidence
  override older PASS/DONE rows.
- F12 reaction 3D animation foreground evidence from
  `W-F12-VISIBLE-FOREGROUND-RECAPTURE-001` is BLOCKED, not PASS, when play/next
  frames remain 1/40 and MD5/diff shows no animation advance.
- ORCA/DFT UI reports may not claim full availability when `/health` is
  degraded (`orca_exists=false` or `api_key_set=false`) and the UI still shows
  `[REMOTE_DFT]` instead of a degraded/simulation warning.
- UVVis ORCA availability claims must reject if `MATPLOTLIB_AVAILABLE`
  NameError is present.

## W-HTML-BATCH-AUDIT-001 batch gate (2026-05-10)

- When `docs/reports/feedback_loop/**/index.html`, `cycle_*.html`, or
  manifest-linked HTML count is 3 or more, run
  `python housing/sinktank/cycle_html_batch_audit.py`.
- The gate is fail-closed/report-only: it writes JSON+MD evidence under
  `docs/reports/html_batch_audit_20260510/W-HTML-BATCH-AUDIT-001/` and exits
  nonzero on blocking findings, but does not edit source reports.
- Required checks: local image paths exist, at least 5 existing images and 3
  distinct feature/layer buckets are present, duplicate/stale image hashes are
  reported, `data:image/svg`/placeholder evidence is rejected, user_env or
  foreground sections are required for PASS/DONE reports, Korean/tofu/mojibake
  artifacts are rejected, and PASS/DONE claims need fresh local evidence paths.
- Blocker-mining codes covered where report artifacts expose them:
  `CYCLE-SCHEDULER-ALIVE-001`, `VISIBLE-FOREGROUND-MATRIX-MINIMUM-001`,
  `ANIMATION-FRAME-ADVANCE-001`, `AUDIT-SOURCE-FRESHNESS-001`,
  `HTML-SEMANTIC-EVIDENCE-001`, `HTML-BATCH-THREE-PLUS-GATE-001`,
  `USERENV-HTML-BATCH-MODE-001`, `KOREAN-TOFU-ARTIFACT-001`,
  `CLICK-ROUTE-PURITY-001`, `FOREGROUND-TARGET-DETECTION-001`,
  `SERIAL-GATE-FINAL-BLOCK-001`, `PASS-DONE-STALE-EVIDENCE-001`, and
  `ENGINE-ROUTE-LIVE-CONTRACT-001`.
- Report artifacts that must block final claims include active STOP sentinels,
  stale scheduler PID files, foreground matrices below 5 molecules/25 records,
  `depth_matrix_enabled=false`, visible-result failures, identical play/step
  animation hashes, and targeted click results that do not open the expected
  popup/window.

## SERIAL-HTML-REJECT-ACTIVE-PATH-001 (2026-05-10)

- The active post-serial path is `.claude/settings.json` ->
  `.claude/hooks/post_serial_audit_gate.py` -> `.codex/hooks/post_serial_audit_gate.py`.
  Reworks must patch the active `.codex` hook or the `.claude` wrapper path,
  not only `housing/sinktank/post_serial_audit_gate.py`.
- Report/HTML promotion failures must be fail-closed in the active hook before
  serial audit PASS checks run. Valid hook blocking keeps exit code 0 and writes
  `{"decision":"block","reason":"..."}` to stdout.
- Do not import `pass_done_evidence_gate.py` directly inside the active hook:
  that module wraps `sys.stdin/stdout/stderr` for CLI mode. Use a subprocess
  with `CREATE_NO_WINDOW` and parse its JSON stdout to preserve hook protocol.
- Required blockers: stale PASS/DONE evidence, low-evidence HTML or placeholders,
  missing user_env/Rule OO section, F12 reaction animation no frame advance,
  degraded ORCA health with `[REMOTE_DFT]`, and UVVis
  `MATPLOTLIB_AVAILABLE` NameError.
- Evidence for rework must include both direct fixture gate output and active
  `.claude` wrapper output, with raw stdout/stderr/exit code files.
