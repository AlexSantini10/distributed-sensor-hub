"""Periodically stop and restart one Docker Compose service.

Usage example:
    python scripts/compose_chaos.py \
        --compose-file docker/docker-compose-6-nodes.yml \
        --service node3 \
        --down-seconds 20 \
        --up-seconds 40 \
        --cycles 5
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _run_compose(compose_file: Path, args: list[str]) -> None:
    cmd = ["docker", "compose", "-f", str(compose_file), *args]
    subprocess.run(cmd, check=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stop/start a docker compose service on a timer."
    )
    parser.add_argument(
        "--compose-file",
        required=True,
        type=Path,
        help="Path to docker compose yaml file.",
    )
    parser.add_argument(
        "--service",
        required=True,
        help="Compose service name (e.g. node3).",
    )
    parser.add_argument(
        "--down-seconds",
        required=True,
        type=float,
        help="How long the service stays stopped.",
    )
    parser.add_argument(
        "--up-seconds",
        required=True,
        type=float,
        help="How long to wait after restart before next stop.",
    )
    parser.add_argument(
        "--initial-delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay before the first stop.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of stop/start cycles. Use 0 for infinite loop.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing docker commands.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the chaos stop/start loop and return a process exit code."""
    args = _parse_args()
    compose_file = args.compose_file.resolve()
    if not compose_file.exists():
        print(f"[error] Compose file not found: {compose_file}", file=sys.stderr)
        return 2

    if args.down_seconds < 0 or args.up_seconds < 0 or args.initial_delay_seconds < 0:
        print("[error] Durations must be >= 0", file=sys.stderr)
        return 2

    print(
        f"[info] Starting chaos loop for service={args.service} "
        f"compose_file={compose_file} down={args.down_seconds}s up={args.up_seconds}s "
        f"cycles={'infinite' if args.cycles == 0 else args.cycles}"
    )

    if args.initial_delay_seconds > 0:
        print(f"[info] Initial delay {args.initial_delay_seconds}s")
        time.sleep(args.initial_delay_seconds)

    cycle_index = 0
    while args.cycles == 0 or cycle_index < args.cycles:
        cycle_index += 1
        print(f"[info] Cycle {cycle_index}: stopping {args.service}")
        if not args.dry_run:
            _run_compose(compose_file, ["stop", args.service])

        print(f"[info] Service down for {args.down_seconds}s")
        time.sleep(args.down_seconds)

        print(f"[info] Cycle {cycle_index}: starting {args.service}")
        if not args.dry_run:
            _run_compose(compose_file, ["start", args.service])

        print(f"[info] Service up wait for {args.up_seconds}s")
        time.sleep(args.up_seconds)

    print("[info] Chaos loop completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
