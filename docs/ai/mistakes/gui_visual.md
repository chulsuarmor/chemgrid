# GUI Visual / Screenshot Mistakes (16 entries)
> 20-cycle undetected incident. Key lesson: py_compile PASS means nothing for visual bugs.
> Must run actual GUI + screenshot for every visual change. Code review alone = auto-FAIL.
> See: Rule F, Rule U, docs/ai/skills/user_environment_feedback.md

---

## [2026-03-10] live_test.py window detection - VS Code false positive
- **Mistake:** `find_win("ChemGrid")` matched VS Code window title containing "chemgrid"
- **Fix:** Explicitly exclude VS Code, Explorer, Discord before matching "ChemGrid V5"

---

## [2026-03-10] live_test.py input field coordinate - wrong offset
- **Mistake:** `iy = win.top + win.height - INPUT_H - 18 - 90` clicked canvas instead of input
- **Fix:** Remove -90 offset. `win.top + win.height` is absolute window bottom.

---

## [2026-03-10] current_state.json stale SMILES verification
- **Mistake:** Read current_state.json for SMILES after text input, but file only updates on explicit save
- **Fix:** Use visual screenshot verification or app log file, not stale JSON

---

## [2026-03-10] Screenshot capture - Windows overlay interference
- **Mistake:** pyautogui.typewrite() triggered Windows Start menu; ImageGrab captured system overlay
- **Fix:** w.activate() + sleep(1.0) before capture; use QT API directly when possible

---

## [2026-03-10] Test script timeout - 30s limit too short
- **Mistake:** pyautogui GUI test needs 90s+, but execute_command timeout = 30s
- **Fix:** Background process: `Start-Process python -ArgumentList "tools/live_test.py"`

---

## [2026-03-10 session-3] "Fixed" label without actual app verification
- **Mistake:** Marked renderer.py ring_atoms_all fix as [x] complete without running app
- **Result:** Cp- still showed single GREEN dot instead of uniform RED clouds
- **Lesson:** Code logic correct != runtime correct. Always run app and verify visually.

---

## [2026-03-10] Background code verification without visual app test (repeated)
- **Mistake:** py_compile + script execution only. Never launched ChemGrid with mouse/keyboard.
- **Rule:** After every fix: Run_ChemGrid.bat -> screenshot -> mouse click test -> repeat loop

---

## [2026-03-14] No visual verification after code-only modifications (Nth repeat)
- **Affected:** ESP clouds, vibration modes, docking 3D, orbitals, reaction popup
- **Mistake:** 6 features modified with zero app screenshots. 1 molecule tested for vibration.
- **Rule:** Every visual feature needs screenshot-based verification loop with 5+ molecules

---

## [2026-03-14] QTextEdit.appendPlainText() - nonexistent method
- **Mistake:** QTextEdit has no appendPlainText(). Only QPlainTextEdit does.
- **Fix:** Use QTextEdit.append(text). Fixed 4 locations in popup_3d.py.

---

## [2026-03-14] QScrollArea missing - 3D popup bottom panel compressed
- **Mistake:** PropertiesPanel without QScrollArea -> widgets clipped when window too small
- **Fix:** Always wrap variable-height panels in QScrollArea(widgetResizable=True)

---

## [2026-03-14] Spectrum graph SizePolicy not set
- **Mistake:** FigureCanvas default SizePolicy=Fixed -> graph doesn't resize with tab
- **Fix:** QSizePolicy.Policy.Expanding both directions + setMinimumHeight(300)

---

## [2026-03-14] Spectrum graph shrinks on tab switch
- **Mistake:** figure swap without matching canvas widget size -> IR shrinks to corner
- **Fix:** canvas.get_width_height() -> new_fig.set_size_inches() + tight_layout()

---

## [2026-03-18] Cascade #3 GUI feedback lesson 6: QScrollArea missing
- **Lesson:** Variable-height panels MUST have QScrollArea. Repeated from 2026-03-14.

---

## [2026-03-19] 3D reaction animation button missing in app
- **Mistake:** Code exists in popup_synthesis but button not visible in running app
- **Lesson:** Code addition must be followed by app launch + screenshot + button visibility check

---

## [2026-04-11] 20-cycle unmanned loop without GUI verification (Critical Incident)
- **Situation:** Cycles #35-55: M4 6619->9500+, M8 933->20 reported as "evolution"
- **Mistake:** Only py_compile + import test. Zero GUI execution (Rule F completely ignored)
- **Discoveries:** isinstance UnboundLocalError, reportlab not installed, DryLab hang
- **Lesson:** patrol must include G7_RUNTIME gate (MainWindow/predict_all/mechanism/DryLab test)

## [2026-04-12] PWA 저품질 감사 미경유
- API 16/16 PASS인데 UI가 어두운 화면+영어+빈 캔버스
- 스크린샷 감사 안 거침 → "100% PASS" 보고
- 교훈: API PASS ≠ 제품 완성. UI 이미지 감사 필수 (Rule U)

## [2026-04-23] MoleculeCanvas.grab() exit:127 크래시 (Worker G-2)
- **상황**: menu_matrix_test.py에서 MoleculeCanvas.grab() 호출 시 exit:127 발생
- **실수 내용**: cv.update() 후 2번째 app.processEvents() 호출 → paintEvent → draw_bond 내부에서 크래시
- **올바른 방법**:
  1. Drawing/Theory/Lewis: RDKit Draw.MolToImage + PIL 라벨로 캡처 (canvas 사용 안 함)
  2. Popup들: popup.show() + 1회 processEvents + QWidget.render(QPainter) 방식
  3. QTimer.singleShot(300, go) + app.exec() 단일 이벤트 루프 패턴 사용
- **추가**: subprocess 독립 프로세스로 각 캡처를 분리하면 상태 오염 방지
- **결과**: 21/21 PASS 달성 (aspirin/caffeine/ibuprofen × 7메뉴)

---

## [2026-04-23] M218 — Ctrl+PageDown 탭 전환 비결정적 → setCurrentIndex 강제
- **상황:** D-2 feedback_match_foreground.py가 B6-1/B7-1/B10-1/B10-3 4건 탭 미도달 캡처
- **원인:** Molecule3DPopup에 PostMessage Ctrl+PageDown 전송 시 포커스가 QTabBar 외부 위젯에 전달 → 실행별 비결정 동작 (79KB/45KB 랜덤 tab index)
- **해결:** in-process QApplication + Molecule3DPopup(data) 직접 인스턴스 → `tabs.setCurrentIndex(i)` → `assert tabs.currentIndex()==i`
- **교훈:** 외부 subprocess로 QTabWidget 탭 전환 시도 전 in-process 대안 우선 검토

## [2026-04-23] M219 — btn_ribbon.click() offscreen hang (Worker_batch2_capture)
- **상황:** B10-2 Molecule3DPopup(benzene) 탭 0에서 `btn_ribbon.click()` 호출 시 테스트 스크립트 수 분 이상 hang.
  3차례 재시도 모두 "MATCH" 로그 이후 무응답.
- **원인:** `_toggle_ribbon` 슬롯이 내부적으로 `_secondary_structure` DSSP 계산 + `viewer.update()` 체인 호출.
  offscreen QT_QPA_PLATFORM + QPainter 2.5D 폴백에서 render loop 가 블로킹됨.
- **해결:** click() 대신 `btn_ribbon.setChecked(True)` + `viewer._ribbon_mode=True` + `viewer.update()` 직접 조작.
  내부 DSSP 계산을 회피하고 플래그만 세팅 → grab() 정상 동작.
- **교훈:** QPushButton.click()은 슬롯 전체 체인을 트리거하므로 offscreen 캡처 환경에서 hang 위험.
  상태 플래그만 필요한 경우 setChecked/setValue + 필요한 내부 플래그 직접 대입 → 안전.
- **참조:** tools/feedback_match_batch2.py case_B10_2 분기

## [2026-04-23] M220 — 클래스 이름 별칭 혼동 (popup_synthesis / popup_polymer)
- **상황:** CT 지령에 `PopupSynthesis` / `PolymerSynthesisPopup`으로 클래스 언급되었으나 실제 소스는 `SynthesisPopup` / `PolymerAnalysisPopup`.
- **실수 가능성:** 지령 그대로 `from popup_synthesis import PopupSynthesis` 시 ImportError.
- **해결:** Grep으로 실 클래스 이름 선확인 후 `as _PopupSynthesis` 별칭 매핑. 각 import 실패 시 per-case 기록 + 전체 중단 금지.
- **교훈:** Grep `^class\s+\w+` 선확인 1줄로 크래시 방지. 문서상 이름 ≠ 실제 이름.
- **참조:** tools/feedback_match_batch2.py import 블럭 + _POPUP_IMPORT_ERRORS dict
- **스크립트:** `tools/feedback_match_in_process.py` (4/4 PASS, MD5 4종 상이, size 46-70KB)

## [2026-04-28] M645_W14 — view_guard 정적값 부족 → 7px overlap (LITE-EXE-002 refix)
- **상황:** W3가 view_guard=418 정적값 설정. W13 audit_gui에서 btn_right=932, vc_left=925 → 7px overlap REJECT.
- **실수 내용:** view_container.x() = width-425 인데 view_guard=418을 사용 → max_right가 vc_left보다 7px 오른쪽
- **올바른 방법:** resizeEvent 내에서 view_container.move() 후 view_container.x() 동적 읽기 → max_right = vc_left - 8 (safety gap)
- **폴백:** view_container.x()==0(초기화 중)이면 self.width()-433 정적값 사용
- **교훈:** 레이아웃 충돌 방지값은 동일 resizeEvent 내 실측값에서 계산. 정적 magic number는 margin 변경 시 즉시 무효화됨.
- **파일:** src/app/main_window.py L1086-1093

## [2026-05-07] M854 foreground popup harness stalled by modal exec + heavy Ollama fallback
- **Situation:** 20-minute thread watchdog repeatedly found `popup_screenshot_matrix.py` stuck after aspirin 3D tab capture. Ollama reloaded `qwen2.5:14b` (~9.7GB GPU) and the foreground cycle produced REJECT HTML without synthesis/reaction/polymer evidence.
- **Mistake:** The harness treated popup button clicks as harmless, but `open_synthesis_popup()` used `popup.exec()`, so `btn.click()` blocked before the screenshot harness could set its own timeout/capture tabs. A separate synthesis no-route path also attempted `qwen2.5:14b` during headless capture.
- **Correct method:** In `CHEMGRID_CAPTURE_MODE=1` or `QT_QPA_PLATFORM=offscreen`, open required popups with `show()` plus a retained reference, not `exec()`. Disable heavy Ollama fallback during GUI evidence capture; use current UI state/fallback text as evidence and let AV reject missing panels instead of freezing the loop.
- **Prevention:** Every popup screenshot harness must verify that the clicked slot returns control. If a popup path uses modal `exec()`, add capture/headless non-modal guard before relying on QTimer or process timeout.

## [2026-05-07] M855 background/offscreen evidence mislabeled as foreground
- **Situation:** The loop produced screenshots and HTML, but the user could not see ChemGrid being operated. Earlier evidence mixed offscreen popup summons, direct Qt clicks, and raw canvas mouse drawing of hydrocarbon-like shapes.
- **Mistake:** Treating "a molecule-looking drawing exists" and "popup code path exists" as ChemGrid foreground validation. Raw mouse drawing does not populate the same SMILES/analysis pipeline as text input, and old button coordinates clicked the wrong right-side stack entries.
- **Correct method:** Visible proof must use the real `ChemGrid V5` window with pyautogui: click the visible SMILES input, paste a meaningful SMILES (aspirin/styrene/reaction pair), press Enter, click the bottom-right Theory button, then click the visible right-side popup buttons. PASS requires a new popup window title plus a popup screenshot.
- **Prevention:** `tools/visible_foreground_click_driver.py` is the required Stage 2 foreground gate. The loop must not claim foreground PASS from offscreen `popup_screenshot_matrix.py` alone.

## [2026-05-07] M856 Korean IME SMILES input not repaired
- **Situation:** User typed `CC(=O)ㅒㅊ1ㅊㅊㅊㅊㅊ1ㅊ(=)ㅒ`, an aspirin-like SMILES entered while Korean IME was active.
- **Mistake:** Treating this as an ordinary PubChem name/search failure would hide the real issue. The user intended English-key SMILES characters, and ChemGrid should give immediate, specific feedback instead of silently failing or falling back to a wrong molecule.
- **Correct method:** If input contains Korean 2-beolsik jamo, restore intended English keys, try minimal chemistry-specific repairs such as `(=)` -> `(=O)` and `c(=O)O` -> `C(=O)O`, then accept only candidates that pass RDKit `MolFromSmiles()`.
- **Prevention:** `main_window._normalize_ime_smiles_input()` runs before SMILES/name routing. If no valid repair exists, statusBar warns about Korean IME characters rather than pretending the molecule was searched normally.
## [2026-05-07] M857 ChemGrid popup title confused with main window
- **Situation:** Visible foreground driver missed a real 3D popup because the popup title also started with `ChemGrid`, then stale pygetwindow handles crashed the loop.
- **Mistake:** Matching any title that starts with `ChemGrid` as the main window, and deciding popup success from fragile title fragments instead of visible non-main windows.
- **Correct method:** Main window match must be exact `ChemGrid V5`. Popup evidence must be a visible non-main window screenshot after the real button click.
- **Prevention:** Foreground watchdog must classify this as harness failure, not app PASS/FAIL ambiguity.

## [2026-05-07] M858 Dot-SMILES reaction pair collapsed into one visible fragment
- **Situation:** Foreground reaction test entered `C=C.BrBr`, but the canvas showed mainly `Br-Br`, so the reaction popup condition was not reliably satisfied.
- **Mistake:** Treating RDKit dot-SMILES as one drawing layout. Disconnected fragments can overlap or leave only one visually obvious molecule.
- **Correct method:** Split dot-SMILES with `Chem.GetMolFrags(..., asMols=True)` and draw each fragment through the append path so every fragment is visible as a separate island.
- **Prevention:** Reaction foreground tests must confirm both reactant islands are visible before clicking reaction analysis.

## [2026-05-07] M859 Electrophilic-addition mechanism omitted acid fragments
- **Situation:** User rejected the reaction mechanism arrows as unusable. The Markovnikov HBr mechanism did not include HBr/H+/Br-/solvent context in the rendered mechanism panel.
- **Mistake:** `electrophilic_addition` used `reactant_smiles="C=C"` for step 1, so the renderer had no electrophile/nucleophile fragments to route real intermolecular curved arrows to.
- **Correct method:** Include electrophile/nucleophile fragments in the step graph (`C=C.[H+].[Br-]`), order electrophilic additions as substrate -> electrophile -> nucleophile, start inter-fragment arrows from pi/sigma bond midpoints, and display solvent/temperature/leaving-group context.
- **Prevention:** Mechanism audits must fail if a step mentions HBr/H+/Br-/solvent in text but those species are absent from the rendered evidence.

## [2026-05-07] M860 Popup-open PASS hid broken HBr mechanism composition
- **Situation:** Foreground reaction popup opened successfully, but the Markovnikov mechanism screenshot still compressed C=C/H+/Br- into a narrow row and made HBr/solvent chemistry look like annotation noise.
- **Mistake:** The harness graded window existence and rough arrow presence, not whether the mechanism panel showed textbook species composition: substrate, polarized acid pair, nucleophile, solvent, and readable curved electron-flow arrows.
- **Correct method:** Multi-fragment electrophilic addition steps must render the current reactant in a full-width row, draw Hδ+—Brδ− as a polarized acid pair, include a visible H2O/ROH solvent mini-structure or solvent cage, and suppress overlapping terminal carbon labels in favor of a pi-bond label.
- **Prevention:** Reaction screenshot audit must reject cramped same-row layouts where HBr/solvent context cannot be visually identified without reading code or trusting text.

## [2026-05-07] M861 Harness convenience leaked into learner layer UI
- **Situation:** Foreground verification needed AlphaFold/docking/lead/DryLab evidence and new direct buttons appeared on the Theory layer, breaking the learner-optimized stack.
- **Mistake:** Treating hidden or nested verification targets as permission to expose new top-level learner buttons. That bypasses the existing exploration order: polymer synthesis, synthesis route, reaction analysis/path, 3D structure, back.
- **Correct method:** Keep the learner layer stack unchanged. Verification must click through the established visible path or nested popup tabs, and only add learner-facing controls after explicit user/CT approval.
- **Prevention:** Before any Theory-layer button or layout change, grep skills/mistakes/context for protected flow notes and reject if the change is only for harness convenience.

## [2026-05-07] M862 Foreground Theory false PASS from button-existence marker
- **Situation:** `tools/visible_foreground_click_driver.py` recorded a Theory-layer PASS after clicking the bottom-right Theory button, but the screenshot still showed the Drawing layer and the reaction popup click hit empty canvas space.
- **Mistake:** The harness trusted a click attempt and generic layer-button location instead of verifying that the protected Theory stack was actually visible. This reproduced the old path/string marker failure in GUI form.
- **Correct method:** After every foreground layer transition, inspect visible screen state. For Theory, require the protected vertical stack colors/buttons to be visible before clicking polymer/synthesis/reaction/3D entries.
- **Prevention:** Foreground reports must mark layer transition as FAIL when the visual state probe fails, and must stop the feature click sequence for that molecule rather than producing popup-open guesses.

## [2026-05-07] M863 Nested popup tab evidence reused base screenshot
- **Situation:** The foreground report marked 3D popup docking and AlphaFold/lead tabs PASS, but the screenshots were the same base 3D properties view. Polymer chain-growth was also marked opened without proving animation movement.
- **Mistake:** The harness clicked content-area coordinates instead of the real nested QTabWidget tab bar, and it did not compare pre/post screenshots for animation.
- **Correct method:** Nested features must click the actual tab-bar coordinates and capture a visibly different tab state. Animation routes must capture before/after frames and fail if the image does not change after the start button click.
- **Prevention:** For every protected subfeature, the report must include a feature-specific screenshot, not just a popup window. Image-diff or visual-state checks are required for simulation claims.

## [2026-05-07] M864 Small-fragment mechanism arrows hidden by generic guard
- **Situation:** Br2 anti-addition foreground screenshot showed the alkene-to-Br arrow, but the Br-Br sigma cleavage arrow was absent or invisible, so the mechanism looked chemically incomplete.
- **Mistake:** The generic "skip intramolecular arrows on fragments smaller than five atoms" guard also suppressed legitimate Br-Br cleavage and bromonium ring-opening arrows. Even when allowed, the short sigma arrow sat directly on the black bond line.
- **Correct method:** Mechanism-specific small-fragment bond arrows must be allowed when the textbook step requires sigma-bond cleavage. For Br2 anti-addition, draw an explicit visible Br-Br sigma-to-Br- curved arrow overlay and verify it in foreground screenshots after restarting the app process.
- **Prevention:** Reaction mechanism audits must reject screenshots that only show a pi-to-electrophile arrow when the text describes leaving-group or sigma-bond cleavage.

## [2026-05-09] M845 Morphine 3D N/A from harness fixture
- **Situation:** M844 W3 marked morphine `02_3d_ball_stick` and `29_vibration_mode` as `UNAVAILABLE` while other morphine popup slots rendered.
- **Mistake:** The evidence harness used a non-app morphine fixture and pre-called RDKit embedding before opening `Molecule3DPopup`. The current fixture parses as C17H19NO3 but ETKDGv3/ETKDG/randomCoords all return `-1`; a related sidecar fixture fails `MolFromSmiles()` outright. The valid main-window/PubChem morphine SMILES embeds and renders.
- **Correct method:** For named molecules, verify harness fixtures against the app canonical lookup/PubChem SMILES and then exercise the actual `Molecule3DData` popup route. Do not classify app popup failure from a pre-popup harness embed failure alone.
- **Prevention:** 3D popup evidence reports must list invalid-parse, parse-ok/embed-failed, and valid-app-fixture outcomes separately, plus screenshots from the valid app route.
