# NEW_MINIMAL_REPLACEMENT_WITH_NO_PROVENANCE
"""Minimal ChemGrid Lite feedback capture companion.

This file is a new replacement helper for test_feedback_chemgrid.bat. It is
not recovered original code.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import logging
import platform
import re
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path("C:/chemgrid")
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "feedback"
SPEC_PATH = ROOT / "ChemGrid_Lite.spec"
LOGGER = logging.getLogger("feedback_capture_app")
POLL_MS = 1000
CAPTURE_DELAY_MS = 220

PLACEHOLDER_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhg"
    "GAWjR9awAAAABJRU5ErkJggg=="
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def timestamp_for_filename(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_platform_info() -> dict[str, str]:
    host = platform.node()
    host_hash = hashlib.sha256(host.encode("utf-8", "replace")).hexdigest()
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.replace("\n", " "),
        "hostname_sha256": host_hash,
    }


def read_text_if_exists(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("Failed to read version text from %s: %s", path, e)
    return ""


def build_marker_from_spec(spec_path: Path) -> str:
    try:
        if not spec_path.is_file():
            return ""
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("Failed to read spec for build marker %s: %s", spec_path, e)
        return ""

    match = re.search(r"v?(\d+\.\d+\.\d+(?:[-_][A-Za-z0-9.]+)*)", text)
    if match:
        return match.group(0).replace(" ", "_")
    return ""


def detect_build_marker(exe_path: Path) -> str:
    for version_path in (exe_path.with_name("_VERSION.txt"), exe_path.parent / "_VERSION.txt"):
        marker = read_text_if_exists(version_path)
        if marker:
            return sanitize_marker(marker)

    marker = build_marker_from_spec(SPEC_PATH)
    if marker:
        return sanitize_marker(marker)

    try:
        mtime = dt.datetime.fromtimestamp(exe_path.stat().st_mtime, tz=dt.timezone.utc)
        return "build_" + mtime.strftime("%Y%m%d_%H%M")
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("Failed to use exe mtime for build marker %s: %s", exe_path, e)
    return "unknown"


def sanitize_marker(marker: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", marker.strip())
    return cleaned[:80] if cleaned else "unknown"


def make_item(
    raw_text: str,
    screenshot_base64: str,
    screenshot_path: str,
    screenshot_note: str,
    created_at: dt.datetime | None = None,
) -> dict[str, Any]:
    created = created_at or utc_now()
    return {
        "created_at_utc": iso(created),
        "raw_feedback": raw_text,
        "screenshot": {
            "base64_png": screenshot_base64,
            "path": screenshot_path,
            "note": screenshot_note,
        },
    }


def write_outputs(
    output_dir: Path,
    exe_path: Path,
    build_marker: str,
    start_time: dt.datetime,
    end_time: dt.datetime,
    items: list[dict[str, Any]],
    synthetic: bool,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = "synthetic_feedback" if synthetic else "user_feedback"
    stem = f"{prefix}_{timestamp_for_filename(start_time)}_build_{sanitize_marker(build_marker)}"
    html_path = output_dir / f"{stem}.html"
    json_path = output_dir / f"{stem}.json"

    screenshot_count = sum(1 for item in items if item["screenshot"].get("base64_png"))
    payload = {
        "schema": "chemgrid_feedback_capture_minimal_replacement_v1",
        "replacement_label": "NEW_MINIMAL_REPLACEMENT_WITH_NO_PROVENANCE",
        "synthetic_self_test": synthetic,
        "start_time_utc": iso(start_time),
        "end_time_utc": iso(end_time),
        "exe_path": str(exe_path),
        "build_marker": build_marker,
        "platform": safe_platform_info(),
        "item_count": len(items),
        "screenshot_count": screenshot_count,
        "raw_feedback_entries": [item["raw_feedback"] for item in items],
        "items": items,
        "claim_boundary": (
            "Synthetic self-test evidence; does not recover or fabricate May 5 raw feedback HTML."
            if synthetic
            else "User-run capture output from this minimal replacement helper."
        ),
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    return html_path, json_path


def render_html(payload: dict[str, Any]) -> str:
    title = "ChemGrid Feedback Capture"
    cards = []
    for index, item in enumerate(payload["items"], start=1):
        raw = item["raw_feedback"]
        image = item["screenshot"].get("base64_png", "")
        img_html = ""
        if image:
            img_html = (
                '<img alt="feedback screenshot" '
                f'src="data:image/png;base64,{html.escape(image, quote=True)}">'
            )
        cards.append(
            "<section class=\"user-card\">"
            f"<h2>Feedback {index}</h2>"
            f"{img_html}"
            f"<pre>{html.escape(raw, quote=False)}</pre>"
            f"<p class=\"muted\">Captured: {html.escape(item['created_at_utc'])}</p>"
            "</section>"
        )

    metadata = {
        "replacement_label": payload["replacement_label"],
        "synthetic_self_test": payload["synthetic_self_test"],
        "start_time_utc": payload["start_time_utc"],
        "end_time_utc": payload["end_time_utc"],
        "exe_path": payload["exe_path"],
        "build_marker": payload["build_marker"],
        "item_count": payload["item_count"],
        "screenshot_count": payload["screenshot_count"],
        "claim_boundary": payload["claim_boundary"],
    }
    meta_rows = "\n".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in metadata.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #0d1117; color: #e0e0e0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ color: #00d4ff; margin: 0 0 16px; }}
    h2 {{ color: #f5a623; margin: 0 0 12px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; background: #161b22; }}
    th, td {{ border: 1px solid #30363d; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ width: 220px; color: #f5a623; }}
    .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
    .user-card {{ background: #161b22; border-left: 4px solid #e94560; border-radius: 6px; overflow: hidden; padding: 16px; }}
    .user-card img {{ width: 100%; height: auto; display: block; background: #0a0a1a; margin-bottom: 12px; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; color: #e0e0e0; }}
    .muted {{ color: #888; font-size: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <table>{meta_rows}</table>
  <div class="gallery">
    {''.join(cards)}
  </div>
</main>
</body>
</html>
"""


class FeedbackWindow:
    def __init__(self, exe_path: Path) -> None:
        import tkinter as tk
        from tkinter import messagebox

        self.tk = tk
        self.messagebox = messagebox
        self.exe_path = exe_path
        self.start_time = utc_now()
        self.build_marker = detect_build_marker(exe_path)
        self.items: list[dict[str, Any]] = []
        self.proc = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
        self.output_written = False

        self.root = tk.Tk()
        self.root.title("ChemGrid Feedback")
        self.root.geometry("520x360")
        self.status_var = tk.StringVar(value="ChemGrid Lite launched. Capture and save feedback.")

        toolbar = tk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=8, pady=8)
        tk.Button(toolbar, text="Capture", command=self.capture_screenshot).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="Save Feedback", command=self.save_feedback).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="Finalize HTML", command=self.finalize_and_quit).pack(side=tk.LEFT, padx=4)

        self.text = tk.Text(self.root, height=10, wrap=tk.WORD)
        self.text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill=tk.X, padx=8, pady=8)

        self.current_screenshot_base64 = PLACEHOLDER_PNG_BASE64
        self.current_screenshot_path = ""
        self.current_screenshot_note = "placeholder until capture"
        self.root.protocol("WM_DELETE_WINDOW", self.finalize_and_quit)
        self.root.after(POLL_MS, self.poll_process)

    def capture_screenshot(self) -> None:
        self.root.withdraw()
        self.root.after(CAPTURE_DELAY_MS, self.grab_and_restore)

    def grab_and_restore(self) -> None:
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab()
            capture_dir = DEFAULT_OUTPUT_DIR / "_feedback_captures"
            capture_dir.mkdir(parents=True, exist_ok=True)
            name = f"capture_{timestamp_for_filename(utc_now())}.png"
            path = capture_dir / name
            image.save(path)
            with path.open("rb") as handle:
                self.current_screenshot_base64 = base64.b64encode(handle.read()).decode("ascii")
            self.current_screenshot_path = str(path)
            self.current_screenshot_note = "captured with PIL ImageGrab"
            self.status_var.set(f"Screenshot captured: {path.name}")
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("Screenshot capture failed: %s", e)
            self.current_screenshot_base64 = PLACEHOLDER_PNG_BASE64
            self.current_screenshot_path = ""
            self.current_screenshot_note = f"capture failed: {e}"
            self.status_var.set("Screenshot failed; placeholder will be recorded.")
        finally:
            self.root.deiconify()

    def save_feedback(self) -> None:
        raw = self.text.get("1.0", "end-1c")
        if not raw:
            self.messagebox.showwarning("Feedback required", "Enter feedback text before saving.")
            return
        self.items.append(
            make_item(
                raw,
                self.current_screenshot_base64,
                self.current_screenshot_path,
                self.current_screenshot_note,
            )
        )
        self.text.delete("1.0", self.tk.END)
        self.status_var.set(f"Saved feedback item {len(self.items)}.")

    def poll_process(self) -> None:
        if self.proc.poll() is not None:
            self.finalize_and_quit()
            return
        self.root.after(POLL_MS, self.poll_process)

    def finalize_and_quit(self) -> None:
        if not self.output_written:
            end_time = utc_now()
            html_path, json_path = write_outputs(
                DEFAULT_OUTPUT_DIR,
                self.exe_path,
                self.build_marker,
                self.start_time,
                end_time,
                self.items,
                synthetic=False,
            )
            LOGGER.info("Wrote feedback HTML: %s", html_path)
            LOGGER.info("Wrote feedback JSON: %s", json_path)
            self.output_written = True
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run_self_test(evidence_dir: Path) -> int:
    start_time = utc_now()
    output_dir = evidence_dir / "self_test_output"
    exe_path = evidence_dir / "synthetic" / "ChemGrid.exe"
    build_marker = "synthetic_self_test_build"
    raw_text = "SYNTHETIC RAW FEEDBACK: keep <tags> & spacing\nline 2 stays exact"
    item = make_item(
        raw_text,
        PLACEHOLDER_PNG_BASE64,
        "",
        "synthetic placeholder image, no ChemGrid launch",
        start_time,
    )
    html_path, json_path = write_outputs(
        output_dir,
        exe_path,
        build_marker,
        start_time,
        utc_now(),
        [item],
        synthetic=True,
    )
    result = {
        "status": "PASS",
        "html_path": str(html_path),
        "json_path": str(json_path),
        "raw_text": raw_text,
        "chemgrid_launched": False,
        "gui_opened": False,
        "docs_feedback_written": False,
    }
    result_path = evidence_dir / "self_test_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChemGrid Lite feedback capture companion")
    parser.add_argument("exe_path", nargs="?", help="Path to ChemGrid Lite ChemGrid.exe")
    parser.add_argument("--self-test", dest="self_test", help="Write synthetic self-test output under evidence dir")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parse_args(argv)
    if args.self_test:
        return run_self_test(Path(args.self_test))

    if not args.exe_path:
        LOGGER.error("Missing ChemGrid Lite EXE path argument.")
        return 2
    exe_path = Path(args.exe_path)
    if not exe_path.is_file():
        LOGGER.error("ChemGrid Lite EXE path is missing or invalid: %s", exe_path)
        return 2

    try:
        return FeedbackWindow(exe_path).run()
    except Exception as e:  # noqa: BLE001
        LOGGER.error("Feedback capture app failed: %s", e)
        LOGGER.error("%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
