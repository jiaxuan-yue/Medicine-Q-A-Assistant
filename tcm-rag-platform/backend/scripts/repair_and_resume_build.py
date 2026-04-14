#!/usr/bin/env python3
"""
repair_and_resume_build.py — export repair targets, repair saved FAISS, then resume build.

Examples:
    python scripts/repair_and_resume_build.py --log-file build.log --all --workers 3 --skip-graph
    python scripts/repair_and_resume_build.py --log-file build.log --repair-only

Behavior:
    1. Parse failed batches from the given build log.
    2. Export targets to stdout and to a small text file under data/processed/.
    3. If a saved FAISS index exists, repair matching batches in-place.
    4. Resume build_index.py using the existing checkpoint.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from repair_failed_batches import parse_targets_from_log

setup_logging("INFO")
logger = get_logger(__name__)

DEFAULT_INDEX_DIR = Path(settings.PROCESSED_DOCUMENTS_DIR) / "faiss_index"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export failed repair targets, repair saved FAISS, and resume build_index."
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        required=True,
        help="Current or previous build log file.",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"FAISS index directory (default: {DEFAULT_INDEX_DIR})",
    )
    parser.add_argument(
        "--repair-only",
        action="store_true",
        help="Repair saved FAISS only; do not resume build_index afterwards.",
    )
    parser.add_argument(
        "--export-file",
        type=Path,
        help="Optional custom file path for exported repair targets.",
    )
    return parser


def export_targets(targets: list[tuple[str, int]], export_file: Path) -> None:
    export_file.parent.mkdir(parents=True, exist_ok=True)
    with open(export_file, "w", encoding="utf-8") as f:
        for title, batch_no in targets:
            f.write(f"{title}:{batch_no}\n")


def run_subprocess(cmd: list[str]) -> None:
    logger.info("Run command: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = build_parser()
    args, build_args = parser.parse_known_args()

    if not args.log_file.exists():
        raise FileNotFoundError(f"log file not found: {args.log_file}")

    targets = parse_targets_from_log(args.log_file)
    if not targets:
        print("No failed batches found in log.")
    else:
        print("Exported repair targets:")
        for title, batch_no in targets:
            print(f"  - {title}:{batch_no}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_file = args.export_file or (
        Path(settings.PROCESSED_DOCUMENTS_DIR) / f"repair_targets_{timestamp}.txt"
    )
    export_targets(targets, export_file)
    print(f"\nTargets file: {export_file}")

    index_path = args.index_dir / "index.faiss"
    meta_path = args.index_dir / "metadata.pkl"
    can_repair = bool(targets) and index_path.exists() and meta_path.exists()

    if can_repair:
        repair_cmd = [
            sys.executable,
            str(Path(__file__).with_name("repair_failed_batches.py")),
            "--index-dir",
            str(args.index_dir),
        ]
        for title, batch_no in targets:
            repair_cmd.extend(["--target", f"{title}:{batch_no}"])
        run_subprocess(repair_cmd)
    else:
        if not targets:
            print("Skip repair: no parsed failed targets.")
        else:
            print(f"Skip repair: saved FAISS files not found under {args.index_dir}")

    if args.repair_only:
        return 0

    if not any(arg == "--all" or arg.startswith("--max-books") for arg in build_args):
        build_args = ["--all", *build_args]

    build_cmd = [
        sys.executable,
        str(Path(__file__).with_name("build_index.py")),
        *build_args,
    ]
    run_subprocess(build_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
