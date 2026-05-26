import json
import sys
from pathlib import Path
from types import SimpleNamespace


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from popup_alphafold import (  # noqa: E402
    build_alphafold_step6_drylab_payload,
    evaluate_alphafold_step6_drylab_readiness,
    read_item17_guard_sidecar_status,
)


def _synthetic_step6_state():
    variant = {
        "smiles": "CCN",
        "parent_smiles": "CCO",
        "modification_type": "atom_swap",
        "modification_detail": "oxygen-to-nitrogen RDKit-only structural variant",
        "docking_score": -4.2,
        "engine_basis": "Lead optimizer provenance only; no real Vina/Browser/CDP evidence.",
        "rdkit_validated": True,
    }
    return {
        "lead_optimization_provenance": {
            "source": "lead_optimizer",
            "artifact_id": "synthetic-step6-fixture",
            "selected_derivative": variant,
            "derivatives": [variant],
        },
        "selected_derivative": variant,
        "derivatives": [variant],
    }


def test_step6_readiness_blocks_missing_lead_provenance():
    gate = evaluate_alphafold_step6_drylab_readiness({})

    assert gate["can_generate"] is False
    assert gate["status"] == "BLOCKED_MISSING_LEAD_PROVENANCE"
    assert "lead optimizer provenance source" in gate["missing_requirements"]
    assert "lead optimizer artifact/run id" in gate["missing_requirements"]
    assert "selected derivative SMILES" in gate["missing_requirements"]
    assert "lead optimizer derivative list" in gate["missing_requirements"]


def test_step6_readiness_accepts_schema_only_lead_provenance_as_warn_gate():
    gate = evaluate_alphafold_step6_drylab_readiness(_synthetic_step6_state())

    assert gate["can_generate"] is True
    assert gate["status"] == "READY_WARN_ONLY"
    assert gate["lead_optimization_provenance"]["artifact_id"] == "synthetic-step6-fixture"
    assert gate["lead_optimization_provenance"]["has_real_vina_evidence"] is False
    assert gate["selected_derivative"]["smiles"] == "CCN"
    assert gate["derivatives"][0]["smiles"] == "CCN"


def test_step6_payload_raises_when_gate_is_blocked():
    gate = evaluate_alphafold_step6_drylab_readiness({})

    try:
        build_alphafold_step6_drylab_payload(
            smiles="CCO",
            selected_receptor={"name": "EGFR"},
            uniprot_id="P00533",
            pdb_id="1IVO",
            structure=None,
            prediction_result=None,
            binding_site_result={},
            docking_results=[],
            step6_gate=gate,
        )
    except ValueError as exc:
        assert "Step 6 DryLab gate blocked" in str(exc)
    else:
        raise AssertionError("blocked Step6 gate reached payload creation")


def test_step6_bridge_passes_alphafold_fields_without_engine_overclaim():
    residues = [
        SimpleNamespace(name="ALA", seq_num=1, chain_id="A", plddt=92.0),
        SimpleNamespace(name="GLY", seq_num=2, chain_id="A", plddt=76.0),
        SimpleNamespace(name="SER", seq_num=3, chain_id="A", plddt=48.0),
    ]
    structure = SimpleNamespace(residues=residues, source="rcsb", mean_plddt=72.0)
    atom = SimpleNamespace(
        name="CA",
        res_name="GLY",
        chain_id="A",
        res_seq=2,
        x=1.0,
        y=2.0,
        z=2.0,
    )

    gate = evaluate_alphafold_step6_drylab_readiness(_synthetic_step6_state())
    payload = build_alphafold_step6_drylab_payload(
        smiles="CCO",
        selected_receptor={
            "name": "EGFR",
            "uniprot": "P00533",
            "pdb_id": "1IVO",
            "description": "test receptor",
        },
        uniprot_id="P00533",
        pdb_id="1IVO",
        structure=structure,
        prediction_result=SimpleNamespace(method="rcsb_lookup"),
        binding_site_result={"center": (0.0, 0.0, 0.0), "atoms": [atom]},
        docking_results=[
            {"name": "candidate A", "smiles": "CCO", "affinity": -5.4, "plddt_weight": 3.9}
        ],
        step6_gate=gate,
    )

    assert payload["smiles"] == "CCO"
    assert payload["alphafold_uniprot_id"] == "P00533"
    assert payload["receptor_info"]["pdb_id"] == "1IVO"
    assert payload["receptor_info"]["binding_site_residues"] == ["GLY2"]
    assert payload["alphafold_plddt_summary"]["avg_plddt"] == 72.0
    assert payload["alphafold_plddt_summary"]["total_residues"] == 3
    assert payload["alphafold_binding_residues"][0]["plddt"] == 76.0
    assert payload["docking_results"][0]["score"] == -5.4
    assert "AutoDock Vina was not run" in payload["docking_results"][0]["method"]
    assert payload["has_browser_cdp_external_capture"] is False
    assert payload["has_loaded_webgl_structure_proof"] is False
    assert payload["has_nonblank_alphafold_pdbe_image"] is False
    assert payload["external_route_evidence_status"] == "APP_LINK_ONLY_BROWSER_CDP_REQUIRED"
    assert payload["receptor_info"]["step6_lead_gate"]["status"] == "READY_WARN_ONLY"
    assert payload["receptor_info"]["lead_optimization_provenance"]["artifact_id"] == "synthetic-step6-fixture"
    assert payload["derivatives"][0]["smiles"] == "CCN"
    serializable_payload = {k: v for k, v in payload.items() if k != "structure"}
    serialized = json.dumps(serializable_payload, ensure_ascii=False).lower()
    assert "fixed" not in serialized
    assert "completed" not in serialized


def test_step6_bridge_reads_item17_guard_sidecar_status(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = pdf.with_name(pdf.name + ".item17_claim_guard.json")
    sidecar.write_text(
        json.dumps({"claim_validation": {"final_claim_safety": "WARN"}}),
        encoding="utf-8",
    )

    status = read_item17_guard_sidecar_status(str(pdf))

    assert status["status"] == "WARN"
    assert status["sidecar_exists"] is True
    assert status["sidecar_count"] == 1


def test_step6_bridge_warns_when_item17_guard_sidecar_missing(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    status = read_item17_guard_sidecar_status(str(pdf))

    assert status["status"] == "WARN_SIDECAR_NOT_FOUND"
    assert status["sidecar_exists"] is False
    assert status["sidecar_count"] == 0
    assert status["sidecar_path"].endswith("report.pdf.item17_claim_guard.json")


def test_step6_bridge_warns_when_item17_guard_sidecar_payload_malformed(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = pdf.with_name(pdf.name + ".item17_claim_guard.json")
    sidecar.write_text(json.dumps({"claim_validation": {}}), encoding="utf-8")

    status = read_item17_guard_sidecar_status(str(pdf))

    assert status["status"] == "WARN_HELD_MALFORMED_SIDECAR_STATUS"
    assert status["raw_status"] == ""
    assert status["sidecar_exists"] is True
    assert status["sidecar_count"] == 1


def test_step6_bridge_warns_when_item17_guard_sidecar_read_fails(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = pdf.with_name(pdf.name + ".item17_claim_guard.json")
    sidecar.write_text("{not valid json", encoding="utf-8")

    status = read_item17_guard_sidecar_status(str(pdf))

    assert status["status"] == "WARN_SIDECAR_READ_FAILED"
    assert status["sidecar_exists"] is True
    assert status["sidecar_count"] == 0


def test_step6_bridge_collapses_pass_sidecar_status_to_held_warn(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = pdf.with_name(pdf.name + ".item17_claim_guard.json")
    sidecar.write_text(
        json.dumps({"claim_validation": {"final_claim_safety": "PASS"}}),
        encoding="utf-8",
    )

    status = read_item17_guard_sidecar_status(str(pdf))

    assert status["status"] == "WARN_HELD_UNTRUSTED_PASS_SIDECAR_STATUS"
    assert status["raw_status"] == "PASS"
    assert status["sidecar_exists"] is True


def test_step6_bridge_collapses_unknown_sidecar_status_to_held_warn(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    sidecar = pdf.with_name(pdf.name + ".item17_claim_guard.json")
    sidecar.write_text(
        json.dumps({"claim_validation": {"final_claim_safety": "UNKNOWN"}}),
        encoding="utf-8",
    )

    status = read_item17_guard_sidecar_status(str(pdf))

    assert status["status"] == "WARN_HELD_UNKNOWN_SIDECAR_STATUS"
    assert status["raw_status"] == "UNKNOWN"
    assert status["sidecar_exists"] is True


def test_step6_user_facing_overclaim_markers_absent():
    source_text = (APP_DIR / "popup_alphafold.py").read_text(encoding="utf-8")

    rejected_markers = [
        "AlphaFold + " + "docking + " + "lead optimization",
        "Vina " + "precision",
        "Aff" + "inity",
        "Lead optimization, " + "real Vina",
    ]
    for marker in rejected_markers:
        assert marker not in source_text
