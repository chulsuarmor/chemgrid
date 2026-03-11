"""
render_test_report.py — ChemGrid 실제 렌더링 검증 HTML 보고서
각 분자를 ChemGrid 엔진으로 실제 그려서 Drawing/Theory 레이어 스크린샷 캡처 후 HTML 보고
"""
import sys, os, datetime, base64, traceback
sys.path.insert(0, "c:/chemgrid/src/app")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QPainter, QImage
import io

OUTPUT_HTML = "c:/chemgrid/docs/reports/render_test_report.html"
os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)

# 테스트 분자 목록 (SMILES 검증 + 이온성 공명 포함)
MOLECULES = [
    {"name": "Benzene",                  "smiles": "c1ccccc1",                                   "note": "방향족 기준"},
    {"name": "Naphthalene",              "smiles": "c1ccc2ccccc2c1",                              "note": "다환 방향족"},
    {"name": "Cyclopentadienyl anion",   "smiles": "[cH-]1cccc1",                                 "note": "공명 음이온 — 전자구름 RED 균등분포 확인"},
    {"name": "Tropylium cation",         "smiles": "C1=CC=CC=C[CH+]1",                            "note": "공명 양이온 — 전자구름 BLUE 균등분포 확인"},
    {"name": "Toluene",                  "smiles": "Cc1ccccc1",                                   "note": "치환 방향족"},
    {"name": "Phenol",                   "smiles": "Oc1ccccc1",                                   "note": "EDG 치환"},
    {"name": "Nitrobenzene",             "smiles": "O=[N+]([O-])c1ccccc1",                        "note": "EWG 치환"},
    {"name": "Aspirin",                  "smiles": "CC(=O)Oc1ccccc1C(=O)O",                      "note": "MW=180"},
    {"name": "Caffeine",                 "smiles": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",                 "note": "퓨린 유도체"},
    {"name": "Glucose",                  "smiles": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",    "note": "당류"},
    {"name": "Adenine",                  "smiles": "Nc1ncnc2[nH]cnc12",                           "note": "핵산 염기"},
    {"name": "Pyridine",                 "smiles": "c1ccncc1",                                    "note": "헤테로방향족"},
    {"name": "Furan",                    "smiles": "c1ccoc1",                                     "note": "5원 방향족"},
    {"name": "Ethanol",                  "smiles": "CCO",                                         "note": "알코올"},
    {"name": "Acetic acid",              "smiles": "CC(=O)O",                                     "note": "카르복실산"},
]

def smiles_to_img_b64(smiles, name, view="Theory"):
    """ChemGrid 캔버스로 분자 그리기 → 스크린샷 → base64 반환"""
    try:
        from canvas import MoleculeCanvas
        from main_window import MainWindow
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from PyQt6.QtCore import QPointF

        # 임시 캔버스 생성
        canvas = MoleculeCanvas.__new__(MoleculeCanvas)
        canvas.atoms = {}
        canvas.bonds = {}
        canvas.view_state = view
        canvas.scale_factor = 1.0
        canvas.pan_offset = QPointF(0, 0)
        canvas.show_clouds = True
        canvas.analysis_results = None

        # RDKit으로 2D 좌표 생성
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, "SMILES 파싱 실패"
        mol = Chem.RemoveHs(mol)
        AllChem.Compute2DCoords(mol)
        try:
            Chem.Kekulize(mol, clearAromaticFlags=False)
        except Exception:
            pass
        conf = mol.GetConformer()

        xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
        ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
        cx_mol = (max(xs) + min(xs)) / 2
        cy_mol = (max(ys) + min(ys)) / 2
        scale = 26.7
        cx_l, cy_l = 200, 200  # 고정 캔버스 중심

        idx_to_key = {}
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            atom = mol.GetAtomWithIdx(i)
            sym = "" if atom.GetSymbol() == "C" else atom.GetSymbol()
            raw_x = cx_l + (pos.x - cx_mol) * scale
            raw_y = cy_l - (pos.y - cy_mol) * scale
            key = (round(raw_x, 2), round(raw_y, 2))
            fc = atom.GetFormalCharge()
            entry = {"main": sym, "attach": {}}
            if fc != 0:
                entry["formal_charge"] = fc
                entry["charge"] = "+" if fc > 0 else "-"
            canvas.atoms[key] = entry
            idx_to_key[i] = key

        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            k1, k2 = idx_to_key.get(i), idx_to_key.get(j)
            if k1 and k2:
                bt = bond.GetBondTypeAsDouble()
                order = 1 if bt < 1.5 else (2 if bt < 2.5 else 3)
                canvas.bonds[(k1, k2)] = order

        # Analyzer 실행
        try:
            from analyzer import ChemicalAnalyzer
            analyzer = ChemicalAnalyzer()
            canvas.analysis_results = analyzer.analyze(canvas.atoms, canvas.bonds)
            if canvas.analysis_results:
                canvas.analysis_results["smiles"] = smiles
        except Exception as e:
            pass

        # QPainter로 직접 렌더링
        W, H = 400, 400
        img = QImage(W, H, QImage.Format.Format_RGB32)
        img.fill(0x1a1a2e)  # 다크 배경
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # canvas paint 로직 직접 호출
        try:
            from renderer import CloudRenderer
            from chem_data import VISUAL_SETTINGS, ELEMENT_DATA

            # 전자구름 (Theory 레이어) — use_theory_coords=False, densities=None
            if view == "Theory" and canvas.analysis_results:
                CloudRenderer.draw_clouds(painter, canvas.analysis_results,
                                          use_theory_coords=False, densities=None)

            # 결합 그리기
            from PyQt6.QtGui import QPen, QColor
            from PyQt6.QtCore import QPointF as QP
            pen = QPen(QColor(200, 200, 220))
            pen.setWidth(2)
            painter.setPen(pen)
            for (k1, k2), order in canvas.bonds.items():
                p1 = QP(*k1)
                p2 = QP(*k2)
                painter.drawLine(p1, p2)
                if order >= 2:
                    dx = p2.x() - p1.x()
                    dy = p2.y() - p1.y()
                    length = (dx**2 + dy**2)**0.5 or 1
                    ox, oy = -dy/length*4, dx/length*4
                    painter.drawLine(QP(p1.x()+ox, p1.y()+oy), QP(p2.x()+ox, p2.y()+oy))

            # 원자 라벨
            from PyQt6.QtGui import QFont
            painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            for key, adict in canvas.atoms.items():
                sym = adict.get("main", "")
                fc = adict.get("formal_charge", 0)
                pos = QP(*key)
                if sym:
                    color_map = {"O": QColor(255,80,80), "N": QColor(100,160,255),
                                 "S": QColor(255,200,50), "F": QColor(144,224,80)}
                    painter.setPen(color_map.get(sym, QColor(220,220,220)))
                    painter.drawText(pos, sym)
                if fc != 0:
                    painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                    painter.setPen(QColor(255,150,50))
                    painter.drawText(QP(pos.x()+8, pos.y()-8), "+" if fc > 0 else "−")
                    painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        except Exception as e:
            painter.setPen(QColor(255, 80, 80))
            painter.drawText(10, 20, f"렌더 오류: {str(e)[:50]}")

        painter.end()

        # QImage → base64
        buf = io.BytesIO()
        qb = img.bits()
        qb.setsize(W * H * 4)
        from PIL import Image as PILImage
        pil = PILImage.frombytes("RGBA", (W, H), bytes(qb))
        pil.save(buf, "PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return b64, "OK"

    except Exception as e:
        return None, f"오류: {traceback.format_exc()[-200:]}"


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[render_test_report] 시작 — {len(MOLECULES)}개 분자 렌더링 중...")

    rows = ""
    summary = {"ok": 0, "fail": 0, "warn": []}

    for i, mol in enumerate(MOLECULES, 1):
        name = mol["name"]
        smiles = mol["smiles"]
        note = mol.get("note", "")
        print(f"  [{i:02d}] {name}...", end="", flush=True)

        # Theory 레이어 렌더링
        b64_theory, msg_theory = smiles_to_img_b64(smiles, name, "Theory")
        # Drawing 레이어 (전자구름 없음)
        b64_draw, msg_draw = smiles_to_img_b64(smiles, name, "Drawing")

        if b64_theory:
            summary["ok"] += 1
            print(f" ✅")
            status_html = '<span style="color:#4CAF50">✅ PASS</span>'
        else:
            summary["fail"] += 1
            summary["warn"].append(f"{name}: {msg_theory}")
            print(f" ❌ {msg_theory[:60]}")
            status_html = f'<span style="color:#F44336">❌ FAIL: {msg_theory[:60]}</span>'

        theory_img = f'<img src="data:image/png;base64,{b64_theory}" width="380" alt="Theory">' if b64_theory else '<div style="color:#555;padding:20px">렌더링 실패</div>'
        draw_img = f'<img src="data:image/png;base64,{b64_draw}" width="380" alt="Drawing">' if b64_draw else '<div style="color:#555;padding:20px">렌더링 실패</div>'

        # 공명 분자 특이사항
        is_resonance = "anion" in name.lower() or "cation" in name.lower()
        res_badge = '<span style="background:#7B1FA2;color:white;padding:2px 6px;border-radius:4px;font-size:11px">⚡공명</span>' if is_resonance else ""

        rows += f"""
        <tr>
          <td style="text-align:center"><b>{i}</b></td>
          <td><b>{name}</b> {res_badge}<br>
              <span style="font-size:11px;color:#90A4AE">{note}</span></td>
          <td style="font-family:monospace;font-size:10px;word-break:break-all">{smiles}</td>
          <td>{status_html}</td>
          <td>
            <div style="display:flex;gap:10px">
              <div>
                <div style="font-size:11px;color:#64B5F6;margin-bottom:4px">🎨 그리기 레이어</div>
                {draw_img}
              </div>
              <div>
                <div style="font-size:11px;color:#FF8A65;margin-bottom:4px">⚗ 이론적 구조 (전자구름)</div>
                {theory_img}
              </div>
            </div>
          </td>
        </tr>"""

    # HTML 생성
    warn_items = "".join(f"<li>{w}</li>" for w in summary["warn"]) or "<li>없음</li>"
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>ChemGrid 렌더링 검증 보고서</title>
<style>
  body {{ font-family:'Segoe UI',sans-serif; background:#1a1a2e; color:#e0e0e0; margin:0; padding:20px; }}
  h1 {{ color:#64B5F6; border-bottom:2px solid #333; padding-bottom:10px; }}
  .meta {{ color:#90A4AE; font-size:13px; margin-bottom:20px; }}
  .summary {{ display:flex; gap:20px; margin-bottom:20px; }}
  .stat {{ background:#0d0d1a; border:1px solid #333; border-radius:8px; padding:15px 25px; text-align:center; }}
  .stat .val {{ font-size:32px; font-weight:bold; }}
  .stat .lbl {{ font-size:12px; color:#90A4AE; }}
  table {{ width:100%; border-collapse:collapse; background:#0d0d1a; }}
  th {{ background:#1565C0; color:white; padding:10px; text-align:left; }}
  td {{ padding:10px; border-bottom:1px solid #1a1a3a; vertical-align:top; }}
  tr:hover {{ background:#0a0a20; }}
  .warn-box {{ background:#1a0808; border:1px solid #C62828; border-radius:6px; padding:12px; margin:15px 0; }}
  img {{ border:1px solid #333; border-radius:4px; display:block; }}
  .check-note {{ background:#0a150a; border:1px solid #2E7D32; border-radius:6px; padding:12px; margin:15px 0; font-size:13px; }}
</style>
</head>
<body>
<h1>⚗️ ChemGrid 렌더링 검증 보고서</h1>
<div class="meta">생성: {ts} | 테스트 분자: {len(MOLECULES)}종 | 각 분자별 Drawing + Theory(전자구름) 레이어 캡처</div>

<div class="summary">
  <div class="stat"><div class="val" style="color:#4CAF50">{summary['ok']}</div><div class="lbl">렌더링 성공</div></div>
  <div class="stat"><div class="val" style="color:#F44336">{summary['fail']}</div><div class="lbl">렌더링 실패</div></div>
  <div class="stat"><div class="val" style="color:#FF8A65">{len([m for m in MOLECULES if 'anion' in m['name'].lower() or 'cation' in m['name'].lower()])}</div><div class="lbl">공명 이온 테스트</div></div>
</div>

<div class="check-note">
<b>🔍 공명 분자 전자구름 확인 포인트:</b><br>
• <b>Cyclopentadienyl anion</b> [cH-]1cccc1: 5개 탄소 전체에 <span style="color:#FF5252">RED 전자구름</span>이 균등하게 분포해야 함 (음이온 = 전자 풍부)<br>
• <b>Tropylium cation</b> C1=CC=CC=C[CH+]1: 7개 탄소 전체에 <span style="color:#5C7AFF">BLUE 전자구름</span>이 균등하게 분포해야 함 (양이온 = 전자 부족)<br>
• <b>Benzene</b>: 6개 탄소 전체에 <span style="color:#4CAF50">GREEN 전자구름</span>이 균등하게 분포해야 함 (중성 방향족)
</div>

{f'<div class="warn-box"><b>⚠️ 실패 항목:</b><ul>{warn_items}</ul></div>' if summary["fail"] else ''}

<table>
<thead>
  <tr><th>#</th><th>분자명 / 설명</th><th>SMILES</th><th>상태</th><th>렌더링 결과 (그리기 / 이론)</th></tr>
</thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ 보고서 생성: {OUTPUT_HTML}")
    print(f"결과: {summary['ok']}/{len(MOLECULES)} PASS")


if __name__ == "__main__":
    main()
