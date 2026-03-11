"""
render_spectra_check.py
========================
에틸 벤조에이트 (SMILES: CCOC(=O)c1ccccc1) 기준으로
수정된 popup_predicted_spectrum.py의 5개 탭 그래프를 PNG로 저장 후
HTML 리포트를 생성한다.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'app'))

import matplotlib
matplotlib.use('Agg')  # 화면 없이 파일 저장

from matplotlib.figure import Figure
from popup_predicted_spectrum import (
    _make_ir_figure, _make_raman_figure,
    _make_nmr_h1_figure, _make_nmr_c13_figure,
    _make_uvvis_figure
)
from predict_spectra import predict_all

# ── 테스트 분자 ──────────────────────────────────────────────────────
TEST_SMILES  = "CCOC(=O)c1ccccc1"  # 에틸 벤조에이트
TEST_LABEL   = "Ethyl Benzoate"
OUT_DIR      = os.path.join(os.path.dirname(__file__), '..', 'docs', 'exports', 'spectra_assets')
os.makedirs(OUT_DIR, exist_ok=True)

spec = predict_all(TEST_SMILES)
print(f"[예측 완료] 분자식: {spec.formula}")
print(f"  IR 피크: {len(spec.ir_peaks)}, Raman: {len(spec.raman_peaks)}")
print(f"  1H: {len(spec.h1_nmr_peaks)}, 13C: {len(spec.c13_peaks)}, UV: {len(spec.uvvis_peaks)}")

# ── 각 Figure 저장 ────────────────────────────────────────────────────
def save_fig(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=120, bbox_inches='tight', facecolor='white')
    print(f"  [저장] {path}")
    return path

figs = {}
figs['ir']     = save_fig(_make_ir_figure(spec.ir_peaks),                                        "check_ir.png")
figs['raman']  = save_fig(_make_raman_figure(spec.raman_peaks, spec.ir_peaks),                   "check_raman.png")
figs['h1nmr']  = save_fig(_make_nmr_h1_figure(spec.h1_nmr_peaks, spec.formula, TEST_SMILES),     "check_h1nmr.png")
figs['c13nmr'] = save_fig(_make_nmr_c13_figure(spec.c13_peaks, spec.formula, TEST_SMILES),        "check_c13nmr.png")
figs['uvvis']  = save_fig(_make_uvvis_figure(spec.uvvis_peaks),                                   "check_uvvis.png")

# ── HTML 리포트 생성 ──────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>ChemGrid 분광 렌더링 검증 — {TEST_LABEL}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; }}
  h1 {{ color: #60a5fa; border-bottom: 2px solid #334155; padding-bottom: 10px; }}
  h2 {{ color: #94a3b8; font-size: 1em; margin: 8px 0 4px 0; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }}
  .full {{ grid-column: span 2; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 16px; box-shadow: 0 4px 12px #0004; }}
  img {{ width: 100%; border-radius: 8px; border: 1px solid #334155; }}
  .badge {{ display: inline-block; background: #1d4ed8; color: white; border-radius: 6px;
            padding: 2px 10px; font-size: 0.8em; margin-left: 8px; }}
  .badge.fix {{ background: #15803d; }}
  .badge.new  {{ background: #7c3aed; }}
  .meta {{ background: #0f2644; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;
           font-family: monospace; font-size: 0.9em; color: #7dd3fc; }}
  .checklist {{ list-style: none; padding: 0; margin: 0; }}
  .checklist li {{ padding: 4px 0; font-size: 0.88em; }}
  .checklist li::before {{ content: "✅ "; }}
  .checklist li.fix::before {{ content: "🔧 "; color: #34d399; }}
  .warn {{ color: #fbbf24; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>🔬 ChemGrid 분광 렌더링 검증 보고서</h1>
<div class="meta">
  분자: <strong>{TEST_LABEL}</strong> &nbsp;|&nbsp;
  SMILES: <code>{TEST_SMILES}</code> &nbsp;|&nbsp;
  분자식: <strong>{spec.formula}</strong>
</div>

<h2>수정 사항 요약</h2>
<ul class="checklist">
  <li class="fix">IR: <code>ax.invert_yaxis()</code> 제거 → ylim(108, -12)으로 직접 지정 — 피크가 아래 방향(흡수↓)으로 올바르게 표시</li>
  <li class="fix">¹H-NMR / ¹³C-NMR: GridSpec 좌측 패널에 RDKit 구조식 추가 (없으면 SMILES 텍스트로 fallback)</li>
  <li class="fix">¹³C-NMR: ylim(0, 1.35) — y=0이 바닥이 되어 피크가 기준선에서 시작, 음수 y annotation 완전 제거</li>
  <li class="fix">UV-Vis: x축 200→700 nm (NIR 800nm 구간 제거), 라벨 y좌표 5단계 순환(0.88→0.62→0.40→0.74→0.52)으로 중첩 방지</li>
</ul>

<div class="grid">

  <div class="card">
    <h2>📈 IR 스펙트럼 <span class="badge fix">FIX: 피크 방향 정상화</span></h2>
    <p class="warn">수정 전: invert_yaxis() 이중 적용으로 피크가 위쪽 → 수정 후: Transmittance % y축, 피크 아래 방향</p>
    <img src="check_ir.png" alt="IR">
  </div>

  <div class="card">
    <h2>📈 Raman 스펙트럼</h2>
    <img src="check_raman.png" alt="Raman">
  </div>

  <div class="card full">
    <h2>📈 ¹H-NMR 스펙트럼 <span class="badge new">NEW: 좌측 구조식 패널</span></h2>
    <p class="warn">좌측 패널에 RDKit 구조식 + 피크 색상 그룹 범례 표시 (RDKit/Pillow/Cairo 없을 시 SMILES fallback)</p>
    <img src="check_h1nmr.png" alt="H1NMR">
  </div>

  <div class="card full">
    <h2>📈 ¹³C-NMR 스펙트럼 <span class="badge fix">FIX: y축 바닥 고정</span> <span class="badge new">NEW: 구조식 패널</span></h2>
    <p class="warn">수정 전: ylim(-0.18, 1.05) → 피크가 바닥에서 떠 있음, 홀수 annotation y=-0.07 (화면 밖)<br>
                   수정 후: ylim(0, 1.35) → y=0이 바닥, 모든 annotation 피크 위 양수 영역</p>
    <img src="check_c13nmr.png" alt="C13NMR">
  </div>

  <div class="card full">
    <h2>📈 UV-Vis 스펙트럼 <span class="badge fix">FIX: 라벨 중첩 + x축 범위</span></h2>
    <p class="warn">수정 전: 모든 라벨 y위치 동일(eps_max*0.88) → 중첩, x축 200~800nm(NIR 포함)<br>
                   수정 후: 라벨 5단계 y분산, x축 200~700nm (유기분자 실용 범위)</p>
    <img src="check_uvvis.png" alt="UVVis">
  </div>

</div>

<hr style="border-color:#334155; margin-top:32px;">
<p style="color:#475569; font-size:0.8em; text-align:center;">
  생성: ChemGrid render_spectra_check.py &nbsp;|&nbsp;
  대상 파일: src/app/popup_predicted_spectrum.py
</p>
</body>
</html>"""

html_path = os.path.join(OUT_DIR, "spectra_render_check.html")
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"\n[HTML 리포트] {html_path}")
print("\n모든 작업 완료 ✅")
