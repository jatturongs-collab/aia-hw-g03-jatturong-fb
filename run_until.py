#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run extract_posts.py repeatedly, with cooldowns, until the main report holds a
target number of posts (or progress stalls).

Every run re-scrolls the timeline from the top; results are merged by content
hash, so re-collecting old posts is harmless and each run can reach a bit
deeper once Facebook's throttling has cooled down.

Examples
  python3 run_until.py --target 500
  python3 run_until.py --target 300 --cooldown 300 900 -- --photos-only --keywords "VIH#,RJH#,PR9#"
  python3 run_until.py --target 1000 --escalate -- --output report/claude/hospital_posts.md --headless
  python3 run_until.py --by-year -- --output report_merged/All_Post.md --keywords "VIH#,RJH#"

--by-year: each run starts at the end of a year (extract_posts.py --year) instead of the
top of the timeline, so the page never has to hold every newer post. The first year is
the year of the oldest dated post in the report; when a run gets past its year the next
run starts from the year it reached, otherwise the next run starts one year earlier and
the uncovered span is logged as a gap.

Everything after `--` is passed straight to extract_posts.py.
"""
import argparse
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
POST_HEADER = "## 📌 โพสต์ที่ "


def count_posts(path: Path) -> int:
    try:
        return path.read_text(encoding="utf-8").count(POST_HEADER)
    except FileNotFoundError:
        return 0


_DATE_RE = re.compile(r"- \*\*วันที่/เวลา:\*\* .*?(January|February|March|April|May|June|July|August|"
                      r"September|October|November|December) (\d{1,2}), (\d{4})")


def oldest_date(path: Path):
    """Oldest absolute date in the report, or None."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    dates = [datetime.strptime(f"{m} {d} {y}", "%B %d %Y") for m, d, y in _DATE_RE.findall(raw)]
    return min(dates) if dates else None


def arg_value(args: list, name: str, default=None):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def set_arg(args: list, name: str, value) -> list:
    out, skip = [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a == name:
            skip = True
            continue
        if a.startswith(name + "="):
            continue
        out.append(a)
    return out + [name, str(value)]


def run_and_tee(cmd, log_path):
    """Run the extractor, show its output live AND save it to log_path, so the
    reason a run ended (crash, stagnation, ...) is never lost with the terminal."""
    last_reason = ""
    with open(log_path, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, cwd=str(Path.cwd()), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                lf.write(line)
                lf.flush()
                if "Run ended because:" in line:
                    last_reason = line.split("Run ended because:", 1)[1].strip()
        except KeyboardInterrupt:
            proc.wait()
            raise
        return proc.wait(), last_reason


def main():
    argv = sys.argv[1:]
    passthrough = []
    if "--" in argv:
        k = argv.index("--")
        argv, passthrough = argv[:k], argv[k + 1:]

    ap = argparse.ArgumentParser(description="Loop extract_posts.py until a target post count is reached.")
    ap.add_argument("--target", type=int, default=10 ** 9,
                    help="Stop once the main report has this many posts (default: no limit).")
    ap.add_argument("--by-year", action="store_true",
                    help="Start each run at the end of a year (see module docstring), walking back in time.")
    ap.add_argument("--start-year", type=int, default=None,
                    help="--by-year: first year (default: year of the oldest dated post in the report).")
    ap.add_argument("--min-year", type=int, default=2004,
                    help="--by-year: stop after this year (default 2004).")
    ap.add_argument("--max-runs", type=int, default=20, help="Hard limit on runs (default 20).")
    ap.add_argument("--cooldown", type=float, nargs=2, default=[180, 420], metavar=("MIN", "MAX"),
                    help="Random pause between runs in seconds (default 180 420).")
    ap.add_argument("--stall-runs", type=int, default=3,
                    help="Stop after this many consecutive runs that add 0 posts (default 3).")
    ap.add_argument("--escalate", action="store_true",
                    help="After a run that adds nothing, raise --stagnant-limit by 3 for the next run "
                         "(more patience deep in history).")
    ap.add_argument("--script", default=str(HERE / "extract_posts.py"), help="Path to extract_posts.py.")
    a = ap.parse_args(argv)

    output = Path(arg_value(passthrough, "--output", "report/All_Post.md")).expanduser().resolve()
    stagnant_limit = int(arg_value(passthrough, "--stagnant-limit", 6))
    stalls = 0
    log = output.parent / "run_until.log"
    output.parent.mkdir(parents=True, exist_ok=True)

    def note(msg):
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        print(line, flush=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    note(f"start: target={a.target}, report={output} currently {count_posts(output)} posts")
    year = None
    if a.by_year:
        od = oldest_date(output)
        year = a.start_year or (od.year if od else datetime.now().year)
        note(f"by-year: oldest dated post {od:%Y-%m-%d}, starting at year {year}" if od
             else f"by-year: no dated posts yet, starting at year {year}")
    try:
        for run in range(1, a.max_runs + 1):
            before = count_posts(output)
            if before >= a.target:
                note(f"target reached ({before} >= {a.target})")
                break
            if year is not None and year < a.min_year:
                note(f"by-year: passed --min-year {a.min_year}, done")
                break
            args = set_arg(passthrough, "--stagnant-limit", stagnant_limit)
            if year is not None:
                args = set_arg(args, "--year", year)
            note(f"run {run}/{a.max_runs}: {before} posts so far, stagnant-limit={stagnant_limit}"
                 + (f", year={year}" if year is not None else ""))
            logdir = output.parent / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            run_log = logdir / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
            rc, last_reason = run_and_tee([sys.executable, "-u", a.script] + args, run_log)
            after = count_posts(output)
            note(f"run {run} exit={rc}: {before} -> {after} (+{after - before})  "
                 f"[{last_reason or 'no end reason printed'}]  log: {run_log.name}")

            if rc == 3:
                note("extractor needs a login - run `python3 extract_posts.py --login` first. Stopping.")
                break
            if rc == 4:
                note("extractor could not set the year filter (Facebook UI changed?). Stopping.")
                break
            if year is not None:
                od = oldest_date(output)
                if od and od.year < year:
                    note(f"by-year: run reached {od:%Y-%m-%d}; next run starts at year {od.year}")
                    year = od.year
                else:
                    if od and od.year == year and (od.month, od.day) != (1, 1):
                        note(f"by-year: GAP - nothing collected between {year}-01-01 and {od:%Y-%m-%d} "
                             f"(the run ended inside {year}); next run starts at year {year - 1}")
                    else:
                        note(f"by-year: next run starts at year {year - 1}")
                    year -= 1
            if after >= a.target:
                note(f"target reached ({after} >= {a.target})")
                break
            if after > before:
                stalls = 0
            else:
                stalls += 1
                if a.escalate:
                    stagnant_limit += 3
                if stalls >= a.stall_runs:
                    note(f"{stalls} runs in a row added nothing - Facebook may have served all it will "
                         f"for now. Try again later (hours) or raise --stall-runs.")
                    break
            if run < a.max_runs:
                wait = random.uniform(*a.cooldown) * (1 + 0.5 * stalls)
                note(f"cooldown {wait / 60:.1f} min (Ctrl+C to stop)")
                end = time.time() + wait
                while time.time() < end:
                    print(f"\r    next run in {int(end - time.time()):5d}s ", end="", flush=True)
                    time.sleep(1)
                print()
    except KeyboardInterrupt:
        note("stopped by user")
    note(f"finished: {count_posts(output)} posts in {output}")


if __name__ == "__main__":
    main()
