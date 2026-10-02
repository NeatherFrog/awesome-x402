#!/usr/bin/env python3
"""Manage one bounded subscription-auth research queue; no live trading."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from propdesk.research_runner import CodexExecutor, KINDS, ResearchQueue, ResearchWorker, seed_review_jobs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show queue status without using model tokens")
    sub.add_parser("check", help="check official CLI and ChatGPT login, without a model call")
    sub.add_parser("export", help="write durable registry.json")
    sub.add_parser("seed", help="queue six deduplicated source/hypothesis/result reviews")
    sub.add_parser("resume", help="resume after auth repair or elapsed quota cooldown; does not reset quota")
    add = sub.add_parser("enqueue", help="queue one bounded frozen-context research job")
    add.add_argument("kind", choices=KINDS)
    add.add_argument("question")
    add.add_argument("--context", action="append", default=[], help="relative docs/*.md or docs/*.json")
    run = sub.add_parser("run", help="run one sequential worker; default stops when queue is empty")
    run.add_argument("--max-jobs", type=int, default=100)
    run.add_argument("--hours", type=float, default=24)
    run.add_argument("--timeout", type=float, default=900)
    run.add_argument("--idle-wait", type=float, default=0, help="0 stops when empty; 1–60 polls until session deadline")
    run.add_argument("--no-web", action="store_true", help="disable the official native live-search flag")
    args = parser.parse_args(argv)
    queue = ResearchQueue(REPO_ROOT)
    if args.command == "check":
        result = CodexExecutor(REPO_ROOT).preflight()
    elif args.command == "status":
        result = queue.status()
    elif args.command == "export":
        result = queue.export()
    elif args.command == "seed":
        result = {"job_ids": seed_review_jobs(queue)}
    elif args.command == "resume":
        check = CodexExecutor(REPO_ROOT).preflight()
        if not check["ready"]:
            result = check
        else:
            queue.resume()
            result = queue.status()
    elif args.command == "enqueue":
        result = {"job_id": queue.enqueue(args.kind, args.question, context_files=args.context)}
        queue.export()
    else:
        result = ResearchWorker(queue, executor=CodexExecutor(REPO_ROOT, enable_web=not args.no_web)).run(
            max_jobs=args.max_jobs, max_session_hours=args.hours,
            task_timeout_seconds=args.timeout, idle_wait_seconds=args.idle_wait)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
