#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge several report folders (each with an All_Post.md + picture/) into one.

    python3 merge_reports.py report_merged report report2
    python3 merge_reports.py report_merged report report2 --keywords "VIH#,RJH#,PR9#"

Uses the same dedup rules as extract_posts.py (PostStore: normalized-text hash,
truncated-prefix merge, better date/URL/photos win). The output is sorted
newest first; posts without a parseable date go at the end. Per-ticker files and
keyword_matches.md are rebuilt from the merged set. Source folders are not touched.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_posts import NO_DATE, PostStore, parse_markdown_report, save_all_reports  # noqa: E402

_FULL_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s+(\d{4})(?:\s+at\s+(\d{1,2}):(\d{2})\s*([AP]M))?")


def date_key(d: str):
    m = _FULL_DATE_RE.search(d or "")
    if not m:
        return None
    mon, day, year, hh, mm, ampm = m.groups()
    dt = datetime.strptime(f"{mon} {day} {year}", "%B %d %Y")
    if hh:
        h = int(hh) % 12 + (12 if ampm == "PM" else 0)
        dt = dt.replace(hour=h, minute=int(mm))
    return dt


def keywords_from(folder: Path):
    f = folder / "keyword_matches.md"
    if not f.exists():
        return []
    m = re.search(r"- \*\*Keywords:\*\* `([^`]*)`", f.read_text(encoding="utf-8"))
    return [k.strip() for k in m.group(1).split(",") if k.strip()] if m else []


def main():
    ap = argparse.ArgumentParser(description="Merge report folders into one, newest first.")
    ap.add_argument("out", help="Output folder (created; existing All_Post.md there is merged too).")
    ap.add_argument("sources", nargs="+", help="Report folders to merge.")
    ap.add_argument("--keywords", default=None,
                    help="Comma-separated keywords. Default: union of the sources' keyword_matches.md.")
    ap.add_argument("--url", default="https://www.facebook.com/WriterTable")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    folders = [out] + [Path(s) for s in args.sources]

    store = PostStore()
    keywords = []
    for folder in folders:
        posts = parse_markdown_report(folder / "All_Post.md")
        before = len(store.posts)
        for p in posts:
            store.add(p)
        print(f"[+] {folder}: {len(posts)} posts ({len(store.posts) - before:+d} new)")
        for k in keywords_from(folder):
            if k not in keywords:
                keywords.append(k)
        pic_dir = folder / "picture"
        if folder != out and pic_dir.is_dir():
            (out / "picture").mkdir(exist_ok=True)
            for f in pic_dir.iterdir():
                dst = out / "picture" / f.name
                if f.is_file() and not dst.exists():
                    shutil.copy2(f, dst)
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    dated = [p for p in store.posts if date_key(p["date"])]
    undated = [p for p in store.posts if not date_key(p["date"])]
    dated.sort(key=lambda p: date_key(p["date"]), reverse=True)
    posts = dated + undated

    # Rewrite from scratch so the newest-first order sticks (merge appends otherwise).
    for f in out.glob("*.md"):
        f.unlink()
    opts = SimpleNamespace(photos_only=False, no_split_stocks=False, author_suffix="By_Author", tags=None, tags_file=None)
    save_all_reports(posts, opts, out / "All_Post.md", args.url, keywords)

    missing = [pic["filename"] for p in posts for pic in p.get("pictures") or []
               if not (out / "picture" / pic["filename"]).exists()]
    span = f"{date_key(dated[-1]['date']):%Y-%m-%d} .. {date_key(dated[0]['date']):%Y-%m-%d}" if dated else "-"
    print(f"\n[=] {len(posts)} posts  dated={len(dated)}  undated({NO_DATE})={len(undated)}  span {span}")
    print(f"[=] photos referenced but missing on disk: {len(missing)}")


if __name__ == "__main__":
    main()
