#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Profile Post Extractor  (v2)
=====================================
Scrapes every post on a profile timeline (default: facebook.com/WriterTable) with
Playwright + a persistent Chromium profile, and writes Markdown reports:

  report/All_Post.md                  every post (merged incrementally)
  report/{TAG}_By_Author.md           posts containing a #tag from --tags-file / --tags (optional)
  report/keyword_matches.md           posts matching --keywords
  report/All_Post_excluded_no_photo.md   (--photos-only) posts dropped for having no photo
  report/picture/fb_<hash>.jpg        downloaded post photos

Hard-won rules this file is built around (do not "simplify" these away):
  * Post containers are div[aria-posinset]. role="article" is only comments /
    loading placeholders -> everything inside a nested role="article" is ignored.
  * Never gate on is_visible(): virtualized rows can report zero size. We rely on
    the length of the text we actually extracted.
  * Dates use a strict regex (digit + unit, or month name next to a day number).
    Bare substrings ("may", "d") match names and image alt text.
  * Every per-element loop is capped and each item is isolated in try/catch; the
    whole per-post DOM read is ONE evaluate() with its own short timeout, so one
    stale node can never block for 60 s or kill a whole post.
  * Photo size = getBoundingClientRect(), never naturalWidth (0 until decoded).
  * Scroll loop is wrapped in try/finally + periodic checkpoints, and SIGTERM /
    SIGHUP are turned into KeyboardInterrupt so partial results always save.
  * Chromium's SingletonLock is a *dangling symlink* on Linux — Path.exists()
    returns False for it, so stale-lock cleanup must use os.path.lexists().
  * Dedup key = md5 of *normalized* text (whitespace, "See more/See less" and
    trailing ellipsis removed); a truncated copy that is a prefix of the full
    text is merged into it instead of becoming a duplicate.
"""

import argparse
import hashlib
import os
import random
import re
import signal
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

NO_DATE = "ไม่ระบุเวลา"
DEFAULT_AUTHOR = "Facebook User"
POST_HEADER = "## 📌 โพสต์ที่ "

# Optional #tags that get their own report file (see --tags / --tags-file). Empty by default.
DEFAULT_TAGS = []


def load_tags(args) -> list:
    """Tags from --tags (comma list) and --tags-file (one per line, '#' comments allowed after a space)."""
    tags = []
    if getattr(args, "tags", None):
        tags += [t.strip().lstrip("#") for t in args.tags.split(",") if t.strip()]
    tf = getattr(args, "tags_file", None)
    if tf:
        for line in Path(tf).expanduser().read_text(encoding="utf-8").splitlines():
            line = line.split(" #", 1)[0].strip().lstrip("#")
            if line and not line.startswith("//"):
                tags.append(line)
    seen, out = set(), []
    for t in tags + DEFAULT_TAGS:
        if t.upper() not in seen:
            seen.add(t.upper()); out.append(t)
    return out


# =============================================================================
# CLI
# =============================================================================
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Extract all posts from a Facebook profile timeline into Markdown reports."
    )
    p.add_argument("--url", default="https://www.facebook.com/WriterTable",
                   help="Profile/page URL, or a single post/share URL.")
    p.add_argument("--output", default="report/All_Post.md",
                   help="Main Markdown report (default: report/All_Post.md). Other reports go next to it.")
    p.add_argument("--scrolls", type=int, default=3000,
                   help="Maximum scroll cycles (default 3000). Stagnation normally stops the run earlier.")
    p.add_argument("--repair-every", type=int, default=40,
                   help="Every N cycles, go back and re-capture posts seen only hollow or missing a "
                        "date/link (default 40; 0 = only at the end). Protects against a crash "
                        "before the final repair pass.")
    p.add_argument("--load-media", action="store_true",
                   help="Let the browser download photos/videos while scrolling. Default: blocked - "
                        "they are what exhausts memory (page crash near post ~1000). Photo URLs "
                        "and sizes are still captured and photos are downloaded at the end.")
    p.add_argument("--year", type=int, default=None,
                   help="Start the timeline at the end of this year (profile 'Filters -> Go to: Year'), "
                        "so a run can reach old posts without scrolling through every newer one. "
                        "The feed continues into older years after it.")
    p.add_argument("--js-heap-mb", type=int, default=8192,
                   help="Page JS heap cap in MB (default 8192). At 4096 the page crashed when the heap "
                        "hit the cap, near feed position ~1000.")
    p.add_argument("--max-posts", type=int, default=0,
                   help="Stop after about N posts collected in this run (0 = no limit). Good for a small first test.")
    p.add_argument("--stagnant-limit", type=int, default=6,
                   help="Stop after this many consecutive cycles with 0 new posts (default 6). "
                        "Deep history needs longer pauses, not more attempts - backoff grows each cycle.")
    p.add_argument("--max-backoff", type=float, default=20.0,
                   help="Upper bound (seconds) of the progressive wait on stagnant cycles (default 20).")
    p.add_argument("--checkpoint-every", type=int, default=20,
                   help="Save reports every N new posts during the run (default 20; 0 = only at the end).")
    p.add_argument("--keywords", default=None,
                   help='Comma-separated keywords/tags for a combined keyword_matches.md, e.g. "VIH#,RJH#,PR9#".')
    p.add_argument("--photos-only", action="store_true",
                   help="Keep only posts with >=1 real attached photo. Dropped posts are written to "
                        "<output>_excluded_no_photo.md for verification, never silently discarded.")
    p.add_argument("--include-reels", action="store_true",
                   help="Also keep Reels suggestions (/reel/ links). Excluded by default: they are "
                        "usually other creators' content injected into the feed.")
    p.add_argument("--no-hover", action="store_true",
                   help="Don't hover each post's timestamp to resolve its permalink + full date "
                        "(faster, but many posts will lack date/URL).")
    p.add_argument("--no-download-images", action="store_true", help="Don't download photos.")
    p.add_argument("--no-split-stocks", action="store_true", help="Don't write per-ticker files.")
    p.add_argument("--author-suffix", default="By_Author", help="Per-tag filename suffix (default By_Author).")
    p.add_argument("--tags", default=None, help="Comma-separated #tags to split into their own files, e.g. \"AI,Python\".")
    p.add_argument("--tags-file", default=None, help="Text file with one #tag per line (see tags.example.txt).")
    p.add_argument("--min-photo", type=int, default=100,
                   help="Minimum rendered width/height in px for an <img> to count as a photo (default 100).")
    p.add_argument("--login", action="store_true",
                   help="Open Facebook, let you log in (incl. 2FA), then save the session and exit.")
    p.add_argument("--user-data-dir", default=None,
                   help="Persistent Chromium profile dir. Default: %%LOCALAPPDATA%%/fb-post-extractor/profile on Windows, "
                        "~/.fb_extractor_profile on Linux/WSL.")
    p.add_argument("--browser", choices=["chrome", "chromium"], default="chrome",
                   help="chrome (default) = your installed Google Chrome; chromium = Playwright's bundled "
                        "Chromium. Falls back to chromium automatically if Chrome isn't installed.")
    p.add_argument("--cdp-url", default=None,
                   help="Attach to an already running Chrome via CDP (e.g. http://localhost:9222).")
    p.add_argument("--headless", action="store_true", help="Run headless (only after you have logged in once).")
    p.add_argument("--timeout", type=int, default=60000, help="Navigation timeout in ms (default 60000).")
    p.add_argument("--urls", default=None,
                   help="Fetch specific posts instead of scrolling: comma-separated post/share URLs, or a "
                        "text file with one URL per line. Results merge into the normal reports.")
    p.add_argument("--repair-reports", action="store_true",
                   help="No browser: clean every report in the output folder (dedupe, strip 'See less', "
                        "drop bogus dates, fix photo links). Writes a .bak of each file first.")
    p.add_argument("--debug", action="store_true", help="Print per-container skip reasons every cycle.")
    return p.parse_args(argv)


# =============================================================================
# Environment helpers
# =============================================================================
def is_wsl() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


def is_wsl_without_gui() -> bool:
    return is_wsl() and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def determine_user_data_dir(args) -> Path:
    if args.user_data_dir:
        d = Path(args.user_data_dir).expanduser().resolve()
    elif sys.platform.startswith("linux"):
        # Keep the Chromium profile on the Linux filesystem, NOT under /mnt/c or
        # /mnt/d: drvfs is slow for Chromium's many small files and its symlink
        # handling breaks SingletonLock. A Windows-created profile is unusable
        # from Linux Chromium anyway (cookies are encrypted per-OS).
        d = Path.home() / ".fb_extractor_profile"
    elif sys.platform == "win32":
        # Outside the repo on purpose: the profile holds a logged-in session and must never be committed.
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        d = Path(base) / "fb-post-extractor" / "profile"
    else:
        d = Path.home() / ".fb_extractor_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        # os.kill(pid, 0) would TERMINATE the process on Windows - never use it there.
        try:
            import psutil  # type: ignore
            return psutil.pid_exists(pid)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _other_chromium_uses(profile: Path) -> bool:
    """True if a *browser* process (not this python process) has the profile on its command line."""
    target = str(profile)
    me = os.getpid()
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == me:
                    continue
                name = (proc.info.get("name") or "").lower()
                cmd = " ".join(proc.info.get("cmdline") or [])
                if ("chrom" in name or "chrom" in cmd.lower()) and target in cmd:
                    return True
            except Exception:
                continue
        return False
    except ImportError:
        pass
    if sys.platform.startswith("linux"):
        try:
            import subprocess
            out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) != me:
                    if "chrom" in parts[1].lower() and target in parts[1]:
                        return True
        except Exception:
            pass
    return False


def cleanup_stale_profile_lock(profile: Path) -> None:
    """Remove Singleton{Lock,Cookie,Socket} left behind by a killed run.

    On Linux SingletonLock is a symlink to '<hostname>-<pid>' that does not
    exist as a file, so Path.exists() is False even when the lock is present -
    that is why the old check silently never cleaned anything. We use lexists()
    and treat the lock as live only if that pid is alive on this host AND a
    Chromium process is really using the profile."""
    names = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
    paths = [profile / n for n in names]
    if not any(os.path.lexists(p) for p in paths):
        return

    live = False
    lock = profile / "SingletonLock"
    if os.path.islink(lock):
        try:
            host, _, pid = os.readlink(lock).rpartition("-")
            if host == socket.gethostname() and pid.isdigit() and _pid_alive(int(pid)):
                live = _other_chromium_uses(profile)
        except Exception:
            live = _other_chromium_uses(profile)
    else:
        live = _other_chromium_uses(profile)

    if live:
        print(f"[!] A Chromium process is already using {profile}. Close it first.")
        return

    removed = []
    for p in paths:
        try:
            if os.path.lexists(p):
                os.unlink(p)
                removed.append(p.name)
        except Exception:
            pass
    if removed:
        print(f"[+] Removed stale lock from an interrupted run: {', '.join(removed)}")


def install_signal_handlers():
    """Closing the terminal (SIGHUP) or `kill` (SIGTERM) -> KeyboardInterrupt,
    so the try/finally that saves partial results still runs."""
    def _raise(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _raise)
            except Exception:
                pass


# =============================================================================
# Text helpers
# =============================================================================
_TH_MONTHS = ("มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม|"
              r"ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.")
_EN_MONTHS = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
              r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
# Absolute: a month name directly next to a day number ("September 15", "15 Sep", "27 กันยายน").
_ABS_DATE_RE = re.compile(
    rf"(?:\b(?:{_EN_MONTHS})\.?\s+\d{{1,2}}\b)|(?:\b\d{{1,2}}\s+(?:{_EN_MONTHS})\b)|(?:\d{{1,2}}\s*(?:{_TH_MONTHS}))",
    re.IGNORECASE,
)
# Relative: the WHOLE string must be "<digits><unit>" (optionally "ago"/"ที่แล้ว"),
# or a known word. Thai has no \b between letters, so Thai units are unanchored.
_REL_DATE_RE = re.compile(
    r"^\s*(?:"
    r"\d+\s*(?:ชม\.?|ชั่วโมง|นาที|วินาที|วัน|สัปดาห์|เดือน|ปี)(?:ที่แล้ว)?"
    r"|\d+\s*(?:s|sec|secs|m|min|mins|minutes?|h|hr|hrs|hours?|d|days?|w|wk|wks|weeks?|mo|months?|y|yr|yrs|years?)(?:\s+ago)?"
    r"|yesterday(?:\s+at\s+\d{1,2}:\d{2}\s*(?:am|pm)?)?|just now|เมื่อวาน(?:นี้)?(?:\s*เวลา\s*\d{1,2}:\d{2}\s*น?\.?)?|เมื่อสักครู่|ตอนนี้"
    r")\s*$",
    re.IGNORECASE,
)


def looks_like_date(candidate: str) -> bool:
    if not candidate:
        return False
    c = candidate.strip()
    if not c or len(c) > 65:
        return False
    if _REL_DATE_RE.match(c):
        return True
    return bool(_ABS_DATE_RE.search(c))


def date_quality(d: str) -> int:
    """0 = none/invalid, 1 = relative ("3d"), 2 = absolute, 3 = absolute with year/time."""
    if not d or d == NO_DATE or not looks_like_date(d):
        return 0
    if _ABS_DATE_RE.search(d):
        return 3 if re.search(r"\b(19|20|25)\d{2}\b|\d{1,2}:\d{2}", d) else 2
    return 1


_UI_JUNK = {
    "ถูกใจ", "แสดงความคิดเห็น", "แชร์", "ส่งความคิดเห็น", "ดูความคิดเห็นเพิ่มเติม",
    "Like", "Comment", "Share", "Write a comment...", "Public", "สาธารณะ",
    "ดูเพิ่มเติม", "See more", "... ดูเพิ่มเติม", "... See more", "See less", "ดูน้อยลง",
    "กำลังโหลด...", "Loading...", "แก้ไขแล้ว", "Edited",
    "ตอบกลับ", "Reply", "ซ่อนหรือรายงาน", "Hide or report",
    "Online status indicator", "Active", "ติดตาม", "Follow", "·", "Facebook",
}
# Case-sensitive on purpose: Facebook's toggle is "See more"/"See less"; prose
# like "...come and see more" must survive.
_TRAILING_TOGGLE_RE = re.compile(
    r"(?:\s*(?:…|\.\.\.)?\s*(?:See more|See less|ดูเพิ่มเติม|ดูน้อยลง|แสดงน้อยลง))+\s*$"
)


def clean_text(text: str) -> str:
    if not text:
        return ""
    out = []
    for line in text.replace("\r", "").split("\n"):
        # Shared-post attachments put the toggle at the end of inner lines too.
        line = _TRAILING_TOGGLE_RE.sub("", line.strip()).strip()
        if line and line not in _UI_JUNK:
            out.append(line)
    t = "\n".join(out).strip()
    t = _TRAILING_TOGGLE_RE.sub("", t).rstrip()
    return t


def normalize_for_hash(text: str) -> str:
    t = _TRAILING_TOGGLE_RE.sub("", text or "")
    t = re.sub(r"(…|\.\.\.)\s*$", "", t.strip())
    return re.sub(r"\s+", "", t).lower()


def content_hash(text: str) -> str:
    return hashlib.md5(normalize_for_hash(text).encode("utf-8")).hexdigest()


def canonical_post_url(href: str) -> str:
    """Return a clean, stable permalink, or '' if href is not a post/photo permalink.
    Keeps ?fbid= for /photo/ links (the old code stripped every query string and
    produced 62 useless 'facebook.com/photo/' links)."""
    if not href:
        return ""
    if href.startswith("/"):
        href = "https://www.facebook.com" + href
    try:
        u = urlparse(href)
    except Exception:
        return ""
    if "facebook.com" not in (u.netloc or ""):
        return ""
    q = parse_qs(u.query)
    path = re.sub(r"/+$", "", u.path or "")
    if "story_fbid" in q:
        sid = q["story_fbid"][0]
        pid = q.get("id", [""])[0]
        return f"https://www.facebook.com/permalink.php?story_fbid={sid}" + (f"&id={pid}" if pid else "")
    if re.search(r"/(posts|videos|reel|permalink)/[^/]+", path) or "pfbid" in path:
        return "https://www.facebook.com" + path
    if path.startswith("/photo") or "/photos/" in path:
        if "fbid" in q:
            return f"https://www.facebook.com/photo/?fbid={q['fbid'][0]}"
        if re.search(r"/photos/[^/]+/\d+", path):
            return "https://www.facebook.com" + path
    return ""


def url_quality(u: str) -> int:
    c = canonical_post_url(u)
    if not c:
        return 1 if u else 0
    return 2 if "/photo" in c else 3


def load_url_list(spec: str) -> list:
    """--urls value: a text file (one URL per line, # comments ok) or a comma list."""
    p = Path(spec).expanduser()
    if p.is_file():
        raw = [l.split("#", 1)[0] if not l.strip().startswith("http") else l for l in p.read_text(encoding="utf-8").splitlines()]
    else:
        raw = spec.split(",")
    seen, out = set(), []
    for u in (x.strip() for x in raw):
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_username_from_url(url: str) -> str:
    try:
        path = re.sub(r"^https?://(www\.|m\.)?facebook\.com/", "", url).strip("/")
        return path.split("?")[0].split("/")[0].lower()
    except Exception:
        return ""


# =============================================================================
# Post store (in-run collection AND on-disk report merge use the same rules)
# =============================================================================
def finalize_post(p: dict) -> dict:
    p["text"] = clean_text(p.get("text", ""))
    p["_norm"] = normalize_for_hash(p["text"])
    p["hash"] = hashlib.md5(p["_norm"].encode("utf-8")).hexdigest()
    p.setdefault("pictures", [])
    p.setdefault("author", DEFAULT_AUTHOR)
    p.setdefault("date", NO_DATE)
    p.setdefault("url", "")
    return p


class PostStore:
    MIN_PREFIX = 40

    def __init__(self, posts=()):
        self.posts = []
        self._by_hash = {}
        for p in posts:
            self.add(p)

    def find(self, p):
        i = self._by_hash.get(p["hash"])
        if i is not None:
            return i
        n = p["_norm"]
        if len(n) >= self.MIN_PREFIX:
            for i, e in enumerate(self.posts):
                en = e["_norm"]
                if len(en) >= self.MIN_PREFIX and (en.startswith(n) or n.startswith(en)):
                    return i
        return None

    def add(self, p) -> str:
        """Returns 'added', 'updated' or 'same'."""
        if "_norm" not in p:
            finalize_post(p)
        i = self.find(p)
        if i is None:
            self._by_hash[p["hash"]] = len(self.posts)
            self.posts.append(p)
            return "added"
        return "updated" if self._combine(i, p) else "same"

    def _combine(self, i, p) -> bool:
        e = self.posts[i]
        changed = False
        if len(p["_norm"]) > len(e["_norm"]):  # truncated copy -> full text
            self._by_hash.pop(e["hash"], None)
            e["text"], e["_norm"], e["hash"] = p["text"], p["_norm"], p["hash"]
            self._by_hash[e["hash"]] = i
            changed = True
        if date_quality(p.get("date")) > date_quality(e.get("date")):
            e["date"] = p["date"]
            changed = True
        if url_quality(p.get("url")) > url_quality(e.get("url")):
            e["url"] = p["url"]
            changed = True
        if e.get("author") in ("", DEFAULT_AUTHOR) and p.get("author") not in ("", DEFAULT_AUTHOR, None):
            e["author"] = p["author"]
            changed = True
        e_pics, p_pics = e.get("pictures") or [], p.get("pictures") or []
        if e_pics and p_pics and not any(x.get("src") for x in e_pics):
            # e came from disk. Signed photo URLs change between sessions, so a
            # union would list the same photo twice under two names. Keep the
            # saved set unless this sighting found more photos.
            if len(p_pics) > len(e_pics):
                e["pictures"] = [dict(x) for x in p_pics]
                return True
            return changed
        have = {pic["filename"]: pic for pic in e_pics}
        for pic in p_pics:
            if pic["filename"] not in have:
                e.setdefault("pictures", []).append(pic)
                have[pic["filename"]] = pic
                changed = True
            elif pic.get("src") and not have[pic["filename"]].get("src"):
                have[pic["filename"]]["src"] = pic["src"]
        return changed


# =============================================================================
# Markdown report I/O
# =============================================================================
def parse_markdown_report(md_path: Path) -> list:
    if not md_path.exists():
        return []
    raw = md_path.read_text(encoding="utf-8")
    posts = []
    for chunk in raw.split(POST_HEADER)[1:]:
        lines = chunk.split("\n")
        header = lines[0].strip()
        author = header.split("|", 1)[1].strip() if "|" in header else DEFAULT_AUTHOR
        date, url, content, pictures, in_content = NO_DATE, "", [], [], False
        for line in lines[1:]:
            if line.startswith("- **วันที่/เวลา:**"):
                date = line.split(":**", 1)[1].strip()
            elif line.startswith("- **ลิงก์โพสต์:**"):
                m = re.search(r"\]\((.*?)\)\s*$", line)
                url = m.group(1) if m else line.split(":**", 1)[1].strip()
            elif line.startswith("### เนื้อหา:"):
                in_content = True
            elif line.startswith("### 🖼️ รูปภาพ"):
                in_content = False
            elif line.strip() == "---":
                break
            elif not in_content and line.startswith("!["):
                m = re.search(r"!\[(.*?)\]\((picture/[^)]+)\)", line)
                if m:
                    pictures.append({"src": "", "alt": m.group(1), "filename": Path(m.group(2)).name,
                                     "local_path": m.group(2)})
            elif in_content:
                if line.startswith("> "):
                    content.append(line[2:])
                elif line.startswith(">"):
                    content.append(line[1:])
                elif line.strip():
                    content.append(line)
        if not looks_like_date(date):
            date = NO_DATE  # repairs "May be an image of ...", "October Chris ..." etc.
        canon = canonical_post_url(url)
        if canon:
            url = canon
        elif re.search(r"facebook\.com/(photo|stories)/?$", url or ""):
            url = ""
        text = "\n".join(content).strip()
        if not text:
            continue
        posts.append(finalize_post({"author": author, "date": date, "url": url,
                                    "text": text, "pictures": pictures}))
    return posts


def render_post(idx: int, post: dict, keywords=None) -> list:
    out = [f"{POST_HEADER}{idx} | {post.get('author') or DEFAULT_AUTHOR}",
           f"- **วันที่/เวลา:** {post.get('date') or NO_DATE}"]
    if post.get("url"):
        out.append(f"- **ลิงก์โพสต์:** [{post['url']}]({post['url']})")
    if keywords:
        hits = find_custom_keyword_matches(post["text"], keywords)
        if hits:
            out.append(f"- **คีย์เวิร์ดที่พบ:** `{', '.join(hits)}`")
    out += ["", "### เนื้อหา:", ""]
    out += [f"> {l}" if l.strip() else ">" for l in post["text"].split("\n")]
    pics = post.get("pictures") or []
    if pics:
        out += ["", f"### 🖼️ รูปภาพ ({len(pics)} ภาพ):"]
        for i, pic in enumerate(pics, 1):
            alt = (pic.get("alt") or f"ภาพประกอบ {i}").replace("[", "(").replace("]", ")").replace("\n", " ")
            out.append(f"![{alt}]({pic.get('local_path') or 'picture/' + pic['filename']})")
    out += ["", "---", ""]
    return out


def write_report(path: Path, title: str, meta: list, posts: list, keywords=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""] + meta + ["", "---", ""]
    if not posts:
        lines.append("> ⚠️ ไม่พบโพสต์\n")
    for i, p in enumerate(posts, 1):
        lines += render_post(i, p, keywords)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash mid-write never leaves a half report


def merge_into_report(path: Path, new_posts: list, title: str, meta_fn, keywords=None, drop=None):
    store = PostStore(parse_markdown_report(path))
    before = len(store.posts)
    for p in new_posts:
        store.add(dict(p, pictures=[dict(x) for x in p.get("pictures") or []]))
    posts = store.posts
    if drop is not None:
        posts = [p for p in posts if drop.find(p) is None]
    write_report(path, title, meta_fn(len(posts)), posts, keywords)
    return len(posts), len(posts) - before, store


def find_stock_tags(text: str, stocks=None) -> list:
    stocks = stocks or []
    return [s.upper() for s in stocks
            if re.search(rf"#{re.escape(s)}(?![\w-])|/hashtag/{re.escape(s.lower())}\b", text, re.IGNORECASE)]


def find_custom_keyword_matches(text: str, keywords: list) -> list:
    matched = []
    for kw in keywords:
        ticker = kw.strip().strip("#").strip()
        if not ticker:
            continue
        pats = [re.escape(kw), rf"#{re.escape(ticker)}(?![\w-])", rf"(?<![\w#]){re.escape(ticker)}#",
                rf"(?<![\w-]){re.escape(ticker)}(?![\w-])"]
        if any(re.search(p, text, re.IGNORECASE) for p in pats):
            matched.append(kw)
    return matched


def save_all_reports(posts: list, args, output_path: Path, target_url: str, keywords: list, quiet=False):
    out_dir = output_path.parent
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kept = [p for p in posts if p.get("pictures")] if args.photos_only else list(posts)
    excluded = [p for p in posts if not p.get("pictures")] if args.photos_only else []
    mode = "Photos only (posts with >=1 attached photo)" if args.photos_only else "All posts (unfiltered)"

    total, added, main_store = merge_into_report(
        output_path, kept, "Facebook Content Extraction Report — All Posts",
        lambda n: [f"- **Target URL:** [{target_url}]({target_url})", f"- **Last Updated:** {now}",
                   f"- **Mode:** {mode}", f"- **Total Posts Captured:** {n}"])
    if not quiet:
        print(f"[+] {output_path.name}: {total} posts ({added:+d})")

    if args.photos_only:
        ex_path = out_dir / f"{output_path.stem}_excluded_no_photo.md"
        # drop= removes entries that have since been found WITH a photo.
        t, a, _ = merge_into_report(
            ex_path, excluded, "Posts EXCLUDED by --photos-only (no attached photo found)",
            lambda n: [f"- **Target URL:** [{target_url}]({target_url})", f"- **Last Updated:** {now}",
                       "- **Purpose:** verification — check none of these actually had a photo",
                       f"- **Total Excluded Posts:** {n}"],
            drop=main_store)
        if not quiet:
            print(f"[+] {ex_path.name}: {t} posts ({a:+d})")

    tags = load_tags(args)
    if tags and not args.no_split_stocks:
        by_ticker = {}
        for p in kept:
            for t in find_stock_tags(p["text"], tags):
                by_ticker.setdefault(t, []).append(p)
        for ticker, plist in sorted(by_ticker.items()):
            path = out_dir / f"{ticker}_{args.author_suffix}.md"
            t, a, _ = merge_into_report(
                path, plist, f"Facebook Content Extraction Report — #{ticker}",
                lambda n, tk=ticker: [f"- **Tag:** `#{tk}`",
                                      f"- **Target URL:** [{target_url}]({target_url})",
                                      f"- **Last Updated:** {now}", f"- **Total Posts for #{tk}:** {n}"])
            if not quiet and a:
                print(f"[+] {path.name}: {t} posts ({a:+d})")

    if keywords:
        matched = [p for p in kept if find_custom_keyword_matches(p["text"], keywords)]
        path = out_dir / "keyword_matches.md"
        t, a, _ = merge_into_report(
            path, matched, "Facebook Content Extraction Report — Keyword Matches",
            lambda n: [f"- **Target URL:** [{target_url}]({target_url})", f"- **Last Updated:** {now}",
                       f"- **Keywords:** `{', '.join(keywords)}`", f"- **Total Matched Posts:** {n}"],
            keywords=keywords)
        if not quiet:
            print(f"[+] {path.name}: {t} posts ({a:+d})")
    return kept


def repair_reports(out_dir: Path):
    files = sorted(f for f in out_dir.glob("*.md") if POST_HEADER in f.read_text(encoding="utf-8"))
    if not files:
        print(f"[!] No reports found in {out_dir}")
        return
    for f in files:
        raw = f.read_text(encoding="utf-8")
        before = raw.count(POST_HEADER)
        head = raw.split(POST_HEADER, 1)[0]
        title_m = re.search(r"^# (.+)$", head, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else f.stem
        meta = [l for l in head.splitlines() if l.startswith("- **")]
        store = PostStore(parse_markdown_report(f))
        n = len(store.posts)
        meta = [re.sub(r"(Total[^:]*:\*\*\s*)\d+", rf"\g<1>{n}", l) for l in meta]
        kw_m = re.search(r"- \*\*Keywords:\*\* `([^`]*)`", head)
        keywords = [k.strip() for k in kw_m.group(1).split(",")] if kw_m else None
        f.with_suffix(f.suffix + ".bak").write_text(raw, encoding="utf-8")
        write_report(f, title, meta, store.posts, keywords)
        dated = sum(1 for p in store.posts if p["date"] != NO_DATE)
        print(f"[+] {f.name}: {before} -> {n} posts  (with valid date: {dated})")


# =============================================================================
# Page helpers
# =============================================================================
EXPAND_JS = r"""
() => {
  const scope = Array.from(document.querySelectorAll('div[aria-posinset]:not([data-fbx-done])'));
  const roots = scope.length ? scope : [document];
  let clicked = 0;
  for (const root of roots) {
    let btns = [];
    try { btns = Array.from(root.querySelectorAll('div[role="button"]')).slice(0, 300); } catch (e) { continue; }
    for (const b of btns) {
      if (clicked >= 40) return clicked;
      try {
        const art = b.closest('[role="article"]');
        if (art && art !== root && (root === document || root.contains(art))) continue;  // comment
        const raw = (b.innerText || '').trim();
        if (!raw || raw.length > 20) continue;
        const t = raw.replace(/^(…|\.\.\.)\s*/, '').toLowerCase();
        if (t !== 'see more' && t !== 'ดูเพิ่มเติม') continue;
        const a = b.closest('a[href]');
        if (a && !(a.getAttribute('href') || '').startsWith('#')) continue;  // would navigate
        b.click(); clicked++;
      } catch (e) {}
    }
  }
  return clicked;
}
"""


def expand_all_see_more(page) -> int:
    try:
        n = page.evaluate(EXPAND_JS)
        if n:
            time.sleep(1.0)
        return n or 0
    except Exception:
        return 0


def close_dialogs_and_banners(page):
    for sel in ['div[role="button"]:has-text("ไม่ใช่ตอนนี้")', 'div[role="button"]:has-text("Not Now")',
                'button:has-text("Allow all cookies")', 'button:has-text("Decline optional cookies")',
                'div[aria-label="Decline optional cookies"]']:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=800)
                time.sleep(0.2)
        except Exception:
            pass


def apply_year_filter(page, year: int) -> bool:
    """Profile 'Filters' -> 'Go to: Year' -> Done. Verified live (1 Oct 2026): the dialog
    has a combobox aria-label "Edit ending date  year. Current selection is none" whose
    [role=option]s are years; after Done the feed restarts at Dec 31 of that year
    (aria-posinset from 1 again). The URL does not change, so this must be clicked."""
    btn = page.locator('div[role="button"][aria-label="Filters"], div[role="button"][aria-label="ตัวกรอง"]').first
    for _ in range(12):  # the button sits above the feed; it may need a few wheels to mount
        try:
            if btn.count():
                break
        except Exception:
            pass
        wheel_scroll(page, 500)
        time.sleep(1)
    try:
        btn.click(timeout=8000)
        combo = page.locator('div[role="dialog"] [role="combobox"][aria-label*="year" i], '
                             'div[role="dialog"] [role="combobox"][aria-label*="ปี"]').first
        combo.click(timeout=8000)
        time.sleep(1)
        page.locator('[role="option"]', has_text=re.compile(rf"^\s*{year}\s*$")).first.click(timeout=8000)
        time.sleep(1)
        label = combo.get_attribute("aria-label") or ""
        if str(year) not in label:
            print(f"[!] Year filter: combobox says {label!r}")
            return False
        page.locator('div[role="dialog"] div[role="button"]',
                     has_text=re.compile(r"^\s*(Done|เสร็จสิ้น)\s*$")).first.click(timeout=8000)
    except Exception as e:
        print(f"[!] Year filter failed: {str(e)[:160]}")
        return False
    time.sleep(5)
    wheel_scroll(page, -6000)  # back to the top of the filtered feed (real wheel, rule 13)
    time.sleep(2)
    return True


def _page_key(url: str) -> str:
    u = urlparse(url)
    q = parse_qs(u.query)
    return u.path.rstrip("/").lower() + (f"?id={q['id'][0]}" if "id" in q else "")


def ensure_on_target(page, home_key: str):
    """A stray click (See more on some layouts, a photo) can open a viewer or
    navigate away. Escape, then go back, so the scroll loop stays on the feed.
    home_key is taken from the URL Facebook actually landed on (it may redirect
    /name -> /profile.php?id=...), not from --url."""
    try:
        if _page_key(page.url) == home_key:
            return
        page.keyboard.press("Escape")
        time.sleep(0.8)
        if _page_key(page.url) != home_key:
            print(f"\n      [i] Navigated away to {page.url[:80]} - going back")
            page.go_back(wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
    except Exception:
        pass


def is_single_post_view(url: str) -> bool:
    return any(p in url.lower() for p in ["/share/p/", "/posts/", "/permalink", "story_fbid=", "/photo", "/share/"])


# =============================================================================
# Extraction
# =============================================================================
TAG_JS = r"""
(selectors) => {
  window.__fbxId = window.__fbxId || 0;
  for (const sel of selectors) {
    let nodes = [];
    try { nodes = Array.from(document.querySelectorAll(sel)); } catch (e) { continue; }
    if (!nodes.length) continue;
    const ids = [];
    for (const el of nodes) {
      if (el.hasAttribute('data-fbx-done')) continue;
      if (!el.dataset.fbxId) el.dataset.fbxId = String(++window.__fbxId);
      ids.push(el.dataset.fbxId);
    }
    return {selector: sel, total: nodes.length, ids};
  }
  return {selector: null, total: 0, ids: []};
}
"""

CONTAINER_SELECTORS = ['div[aria-posinset]', 'div[role="feed"] > div', 'div[data-pagelet^="FeedUnit"]']

# One synchronous DOM walk per post. Every loop is capped and every item is in
# its own try/catch; the Python side adds a per-call timeout.
EXTRACT_JS = r"""
(el, opts) => {
  const MAX_LINKS = 80, MAX_IMGS = 40, MAX_DIRS = 60, MAX_MSG = 10;
  const MIN_PHOTO = opts.minPhoto || 100;
  const out = {msg: [], dirs: [], author: '', links: [], pics: [], hasSeeMore: false,
               tsIndex: -1, top: 0, bottom: 0, pendingImgs: 0, errors: 0};
  const isComment = (n) => {
    try { const a = n.closest('[role="article"]'); return !!(a && a !== el && el.contains(a)); }
    catch (e) { return false; }
  };
  try { const r = el.getBoundingClientRect(); out.top = r.top; out.bottom = r.bottom; } catch (e) {}

  // 1. Post body (outermost message containers, never inside a comment)
  let msgNodes = [];
  try {
    msgNodes = Array.from(el.querySelectorAll(
      'div[data-ad-preview="message"], div[data-ad-rendering-role="story_message"], div[data-ad-comet-preview="message"]'
    )).filter(n => !isComment(n)).slice(0, MAX_MSG);
    msgNodes = msgNodes.filter(n => !msgNodes.some(o => o !== n && o.contains(n)));
  } catch (e) { out.errors++; }
  for (const m of msgNodes) {
    try { const t = (m.innerText || '').trim(); if (t && !out.msg.includes(t)) out.msg.push(t); }
    catch (e) { out.errors++; }
  }

  // 2. Fallback text: div[dir=auto] blocks >= 20 chars, outermost only, not comments
  if (!out.msg.length) {
    let nodes = [];
    try { nodes = Array.from(el.querySelectorAll('div[dir="auto"]')).slice(0, 400); } catch (e) {}
    const picked = []; let acc = 0;
    const junk = new Set(['like','comment','share','see more','write a comment...','ถูกใจ','แสดงความคิดเห็น','แชร์','ดูเพิ่มเติม']);
    for (const d of nodes) {
      if (picked.length >= MAX_DIRS || acc > 6000) break;
      try {
        if (isComment(d) || picked.some(p => p.contains(d))) continue;
        const t = (d.innerText || '').trim();
        if (t.length < 20 || junk.has(t.toLowerCase()) || out.dirs.includes(t)) continue;
        picked.push(d); out.dirs.push(t); acc += t.length;
      } catch (e) { out.errors++; }
    }
  }

  // 3. Is a "See more" still collapsed?
  try {
    for (const b of Array.from(el.querySelectorAll('div[role="button"]')).slice(0, 200)) {
      if (isComment(b)) continue;
      const t = (b.innerText || '').trim().replace(/^(…|\.\.\.)\s*/, '').toLowerCase();
      if (t === 'see more' || t === 'ดูเพิ่มเติม') { out.hasSeeMore = true; break; }
    }
  } catch (e) {}

  // 4. Author
  try {
    for (const h of Array.from(el.querySelectorAll('h2, h3, h4, strong')).slice(0, 10)) {
      if (isComment(h)) continue;
      const t = (h.innerText || '').trim().split('\n')[0];
      if (t && t.length < 80) { out.author = t; break; }
    }
  } catch (e) {}

  // 5. Links (+ pick the header timestamp link and tag it for hovering)
  let links = [];
  try { links = Array.from(el.querySelectorAll('a[href], a[role="link"]')).filter(a => !isComment(a)).slice(0, MAX_LINKS); }
  catch (e) {}
  try { el.querySelectorAll('[data-fbx-ts]').forEach(n => n.removeAttribute('data-fbx-ts')); } catch (e) {}
  const firstMsg = msgNodes[0] || null;
  const PERMA = /\/posts\/|\/permalink|story_fbid=|pfbid|\/videos\/|\/photo/;
  for (const a of links) {
    const item = {href: '', raw: '', aria: '', txt: '', lab: ''};
    try {
      item.raw = a.getAttribute('href') || '';
      item.href = a.href || '';
      item.aria = a.getAttribute('aria-label') || '';
      item.txt = (a.innerText || '').trim().slice(0, 120);
      // Facebook puts the readable date in the element aria-labelledby points to
      // (e.g. "2 hours ago", "10 November 2025") - no hover needed when present.
      const lb = a.getAttribute('aria-labelledby');
      if (lb) {
        item.lab = lb.split(/\s+/).map(id => {
          const n = document.getElementById(id);
          return n ? (n.innerText || n.textContent || '').trim() : '';
        }).join(' ').trim().slice(0, 80);
      }
    } catch (e) { out.errors++; continue; }
    out.links.push(item);
    if (out.tsIndex >= 0) continue;
    try {
      if (firstMsg && (firstMsg.contains(a) || !(a.compareDocumentPosition(firstMsg) & Node.DOCUMENT_POSITION_FOLLOWING))) continue;
      if (a.querySelector('img, svg image, image')) continue;       // avatar / photo link
      if (a.closest('h2, h3, h4, strong')) continue;                // author name link
      if (item.txt.length > 80) continue;
      // Logged-in timeline (verified Sep 2026): the timestamp is <a role="link"
      // href="?__cft__[0]=..."> - a bare query string, no text, no aria-label.
      // Hovering it swaps in the real /posts/pfbid... href and shows a tooltip
      // with the full date. v2 only accepted ''/'#'/permalinks and never found it.
      if (item.raw === '' || item.raw.startsWith('?') || item.raw.startsWith('#') ||
          PERMA.test(item.href) || a.hasAttribute('aria-labelledby')) {
        a.setAttribute('data-fbx-ts', '1');
        out.tsIndex = out.links.length - 1;
      }
    } catch (e) {}
  }

  // 6. Photos: rendered size via getBoundingClientRect (NOT naturalWidth)
  let imgs = [];
  try { imgs = Array.from(el.querySelectorAll('img')).slice(0, 200); } catch (e) {}
  for (const img of imgs) {
    if (out.pics.length >= MAX_IMGS) break;
    try {
      if (isComment(img)) continue;
      const src = img.currentSrc || img.src || '';
      if (!src.startsWith('http')) continue;
      if (src.includes('/images/emoji.php') || src.includes('/rsrc.php/') || src.includes('/emoji/')) continue;
      const al = (((img.closest('a') || {}).getAttribute && img.closest('a').getAttribute('aria-label')) || '').toLowerCase();
      if (al.includes('profile picture') || al.includes('รูปโปรไฟล์')) continue;
      const r = img.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) { out.pendingImgs++; continue; }  // not laid out yet; revisit later
      if (r.width < MIN_PHOTO || r.height < MIN_PHOTO) continue;
      if (!out.pics.some(p => p.src === src)) out.pics.push({src, alt: img.alt || ''});
    } catch (e) { out.errors++; }
  }
  return out;
}
"""


def _pictures_from(raw_pics: list) -> list:
    pics = []
    for pic in raw_pics:
        # key on the path only: the same photo gets different signed query strings
        key = pic["src"].split("?")[0]
        fn = f"fb_{hashlib.md5(key.encode('utf-8')).hexdigest()[:12]}.jpg"
        if any(p["filename"] == fn for p in pics):
            continue
        pics.append({"src": pic["src"], "alt": pic.get("alt") or "ภาพประกอบ", "filename": fn,
                     "local_path": f"picture/{fn}"})
    return pics


def resolve_via_hover(page, container):
    """Hovering the header timestamp makes Facebook fill in the real permalink
    href and show the full date in a tooltip. Returns (url, date) - either may be ''."""
    url = date = ""
    try:
        ts = container.locator('[data-fbx-ts="1"]').first
        if not ts.count():
            return url, date
        # Snapshot tooltips BEFORE hovering: a tooltip left over from the previous
        # post must never be read as this post's date.
        stale = set(page.evaluate(
            "() => Array.from(document.querySelectorAll('[role=\"tooltip\"]')).map(t => (t.innerText || '').trim())"))
        ts.hover(timeout=2500)
        deadline = time.time() + 2.5   # deep in history Facebook answers slower
        time.sleep(0.4)
        while True:
            info = ts.evaluate(
                "a => ({href: a.href || '', aria: a.getAttribute('aria-label') || '',"
                " tips: Array.from(document.querySelectorAll('[role=\"tooltip\"]')).map(t => (t.innerText || '').trim())})",
                timeout=1500)
            url = canonical_post_url(info.get("href", ""))
            if looks_like_date(info.get("aria", "")):
                date = info["aria"].strip()
            if not date:
                fresh = [t for t in info.get("tips", []) if t not in stale and looks_like_date(t)]
                if fresh:
                    date = fresh[-1]
            if (url and date) or time.time() > deadline:
                break
            time.sleep(0.25)
    except Exception:
        pass
    finally:
        try:
            page.mouse.move(2, 300)
        except Exception:
            pass
    return url, date


HOLLOW = "no content captured (hollow container or text < 15 chars)"


def build_post(data: dict, ctx: dict):
    """Turn one EXTRACT_JS result into a post dict. Returns (post, None) or (None, skip_reason)."""
    text = clean_text("\n\n".join(data["msg"] or data["dirs"]))
    pictures = _pictures_from(data["pics"])
    links = data["links"]
    if len(text) < 15:
        if pictures and data["tsIndex"] >= 0:
            # Photo post with no/short caption: give it a distinct body so it
            # does not hash-collide with every other caption-less photo post.
            text = (text + "\n" if text else "") + f"(โพสต์รูปภาพ: {pictures[0]['filename']})"
        else:
            return None, HOLLOW
    if any("/reel/" in (l.get("href") or "") for l in links) and not ctx["include_reels"]:
        return None, "Reels suggestion (use --include-reels to keep)"

    # Header timestamp link first, then everything else in DOM order.
    order = ([links[data["tsIndex"]]] if 0 <= data["tsIndex"] < len(links) else []) + links
    post_url = photo_url = post_date = ""
    for l in order:
        c = canonical_post_url(l.get("href", ""))
        if c and "/photo" not in c and not post_url:
            post_url = c
        elif c and "/photo" in c and not photo_url:
            photo_url = c
        for cand in (l.get("aria", ""), l.get("lab", ""), l.get("txt", "")):
            if date_quality(cand) > date_quality(post_date):
                post_date = cand.strip()
    return {
        "author": data["author"] or ctx["author_fallback"],
        "date": post_date or NO_DATE,
        "url": post_url or photo_url or ctx["profile_url"],
        "_photo_url": photo_url,
        "text": text,
        "pictures": pictures,
    }, None


def fill_from_known(post: dict, ctx: dict):
    """Reruns start from the top again. Posts already saved with a good date and
    permalink don't need another ~2 s hover each - reuse the saved values."""
    known = ctx.get("known")
    if not known or not known.posts:
        return
    try:
        i = known.find(finalize_post(dict(post, pictures=[])))
    except Exception:
        return
    if i is None:
        return
    e = known.posts[i]
    if date_quality(e["date"]) > date_quality(post["date"]):
        post["date"] = e["date"]
    if url_quality(e["url"]) > url_quality(post["url"]):
        post["url"] = e["url"]


def needs_hover(post: dict, data: dict, ctx: dict) -> bool:
    return (ctx["hover"] and data["tsIndex"] >= 0 and
            (url_quality(post["url"]) < 3 or date_quality(post["date"]) < 3))


def apply_hover(post: dict, result):
    u2, d2 = result
    if u2 and "/photo" not in u2 and url_quality(post["url"]) < 3:
        post["url"] = u2
    elif u2 and url_quality(post["url"]) < 2:
        post["url"] = u2
    if date_quality(d2) > date_quality(post["date"]):
        post["date"] = d2


# ---------------------------------------------------------------------------
# In-page collector.
# Facebook unmounts posts that scroll out of view. Extracting only between
# scroll bursts let short-lived posts slip through unseen (the reason posts
# like the 10 Nov 2025 #RPH post were missing). This collector runs INSIDE the
# page on a timer, snapshots every mounted div[aria-posinset] the moment it
# changes, and keeps the best snapshot per feed position. Python drains it.
# aria-posinset is sequential, so never-seen positions = provable gaps.
# ---------------------------------------------------------------------------
COLLECTOR_JS = r"""
(opts) => {
  if (window.__fbx && window.__fbx.running) return 'already';
  const EXTRACT = __EXTRACT__;
  const S = window.__fbx = {recs: {}, dirty: new Set(), running: true, ticks: 0, feedSeq: 0};
  const score = (d) => {
    const t = (d.msg.length ? d.msg : d.dirs).join('\n\n');
    return t.length * 2 + d.pics.length * 50 + (d.hasSeeMore ? 0 : 100) + d.links.length;
  };
  S.tick = () => {
    S.ticks++;
    let nodes = [];
    try { nodes = Array.from(document.querySelectorAll('div[aria-posinset]')); } catch (e) { return; }
    const vh = window.innerHeight || 900;
    for (const el of nodes) {
      try {
        // Facebook keeps every container mounted but only fills the ~4-7 nearest
        // the viewport; far-away ones are hollow, so skip them cheaply.
        const r = el.getBoundingClientRect();
        if (r.bottom < -3 * vh || r.top > 4 * vh) continue;
        if (el.parentElement && el.parentElement.closest('div[aria-posinset]')) continue;
        const sig = el.textContent.length + '|' + el.getElementsByTagName('img').length + '|' +
                    el.getElementsByTagName('a').length;
        if (el.dataset.fbxSig === sig) continue;          // unchanged since last snapshot
        const feed = el.closest('[role="feed"]');
        let fid = 0;
        if (feed) { if (!feed.dataset.fbxFeed) feed.dataset.fbxFeed = String(++S.feedSeq); fid = +feed.dataset.fbxFeed; }
        const key = fid + ':' + el.getAttribute('aria-posinset');
        el.dataset.fbxKey = key;
        const d = EXTRACT(el, opts);
        el.dataset.fbxSig = sig;
        d.key = key; d.feed = fid; d.pos = +el.getAttribute('aria-posinset') || 0;
        const old = S.recs[key];
        if (old) for (const p of old.pics) if (!d.pics.some(q => q.src === p.src)) d.pics.push(p);
        d.sc = score(d);
        if (!old || d.sc >= old.sc) { S.recs[key] = d; S.dirty.add(key); }
      } catch (e) {}
    }
  };
  // After a record is handed to Python keep only what later comparisons need
  // (score + photo list); full copies of 1000+ posts would bloat the page.
  S.drain = () => { S.tick(); const out = [];
    for (const k of S.dirty) { const d = S.recs[k]; out.push(d); S.recs[k] = {sc: d.sc, pics: d.pics}; }
    S.dirty.clear(); return out; };
  S.timer = setInterval(S.tick, opts.interval || 350);
  S.tick();
  return 'installed';
}
"""


def wheel_scroll(page, dy: int):
    """Scroll with REAL (trusted) mouse-wheel events over the feed column.
    Verified on the live logged-in timeline (Sep 2026): Facebook hollows out
    posts away from the viewport and only refills them on genuine wheel input.
    window.scrollBy()/scrollIntoView() move the page but leave those posts empty
    forever - that is how v2 silently skipped posts such as the 10 Nov 2025 #RPH."""
    try:
        vp = page.viewport_size or {"width": 1280, "height": 900}
        page.mouse.move(vp["width"] * 0.5 + random.randint(-40, 40), vp["height"] * 0.55)
        step = 120 if dy > 0 else -120
        remaining = abs(dy)
        while remaining > 0:
            d = min(abs(step), remaining)
            page.mouse.wheel(0, d if dy > 0 else -d)
            remaining -= d
            time.sleep(random.uniform(0.015, 0.04))
    except Exception:
        page.evaluate(f"window.scrollBy(0, {dy})")


def wheel_nudge(page):
    """Tiny real-wheel jiggle: makes Facebook re-render the posts around the viewport."""
    wheel_scroll(page, 120)
    time.sleep(0.15)
    wheel_scroll(page, -120)


def install_collector(page, ctx) -> bool:
    try:
        js = COLLECTOR_JS.replace("__EXTRACT__", EXTRACT_JS.strip())
        page.evaluate(js, {"minPhoto": ctx["min_photo"], "interval": 350})
        return True
    except Exception as e:
        print(f"[!] could not install in-page collector: {e}")
        return False


def drain_collector(page, ctx, by_key: dict, skipped: dict) -> tuple:
    """Pull changed snapshots, build posts, hover where needed. Returns (new_keys, upgraded)."""
    try:
        recs = page.evaluate("() => window.__fbx ? window.__fbx.drain() : null")
    except Exception as e:
        print(f"[!] drain failed: {str(e)[:80]}")
        return [], 0
    if recs is None:  # page reloaded / navigated -> collector gone
        install_collector(page, ctx)
        return [], 0
    new_keys, upgraded, hovered_any = [], 0, False
    try:
        scroll_y = page.evaluate("() => window.scrollY")
    except Exception:
        scroll_y = None
    for rec in recs:
        key = rec["key"]
        post, reason = build_post(rec, ctx)
        if reason:
            if key not in by_key:
                skipped[key] = reason
            continue
        skipped.pop(key, None)
        old = by_key.get(key)
        if old is not None:
            # keep hover results already obtained for this position
            if url_quality(old["url"]) > url_quality(post["url"]):
                post["url"] = old["url"]
            if date_quality(old["date"]) > date_quality(post["date"]):
                post["date"] = old["date"]
            if len(normalize_for_hash(old["text"])) > len(normalize_for_hash(post["text"])):
                post["text"] = old["text"]
            have = {p["filename"] for p in post["pictures"]}
            post["pictures"] += [p for p in old["pictures"] if p["filename"] not in have]
        fill_from_known(post, ctx)
        tries = ctx["hover_tries"].get(key, 0)
        if needs_hover(post, rec, ctx) and tries < 2:      # up to 2 attempts per position
            ctx["hover_tries"][key] = tries + 1
            loc = page.locator(f'div[data-fbx-key="{key}"]')
            try:
                if loc.count():
                    hovered_any = True
                    apply_hover(post, resolve_via_hover(page, loc.first))
            except Exception as e:
                if "crash" in str(e).lower() or "closed" in str(e).lower():
                    raise
        post["_key"], post["_feed"], post["_pos"] = key, rec["feed"], rec["pos"]
        if old is None:
            new_keys.append(key)
        else:
            upgraded += 1
        by_key[key] = post
    # (No programmatic scroll-restore here: the hovered post is already next to
    # the viewport, and a scrollTo() jump would land on hollow posts.)
    return new_keys, upgraded


def repair_pass(page, ctx, by_key: dict, skipped: dict, limit: int = 400, only_before: int = None) -> int:
    """Scroll back to every position that was only seen hollow, or that still
    lacks a date/permalink, let Facebook fill it in, and capture it again.
    Returns how many positions were visited (0 = page not moved)."""
    todo = [k for k, r in skipped.items() if r == HOLLOW]
    if ctx["hover"]:
        todo += [k for k, p in by_key.items()
                 if date_quality(p["date"]) < 2 or url_quality(p["url"]) < 3]
    if only_before is not None:
        todo = [k for k in todo if int(k.split(":")[1] or 0) < only_before]
    done = ctx.setdefault("repaired", {})
    todo = [k for k in set(todo) if done.get(k, 0) < 2]          # max 2 repair visits each
    todo = sorted(todo, key=lambda k: (int(k.split(":")[0]), int(k.split(":")[1] or 0)))[:limit]
    if not todo:
        return 0
    for k in todo:
        done[k] = done.get(k, 0) + 1
    print(f"\n[+] Repair pass: revisiting {len(todo)} position(s) (hollow, or missing date/link)...")
    fixed = 0
    for k in todo:
        loc = page.locator(f'div[data-fbx-key="{k}"]')
        try:
            if not loc.count():
                continue
            before = by_key.get(k)
            b_state = (before["date"], before["url"], len(before["text"])) if before else None
            loc.first.evaluate("e => e.scrollIntoView({block: 'center'})", timeout=3000)
            time.sleep(0.3)
            wheel_nudge(page)        # scrollIntoView alone leaves hollow posts empty
            time.sleep(random.uniform(1.0, 1.6))
            expand_all_see_more(page)
            ctx["hover_tries"][k] = min(ctx["hover_tries"].get(k, 0), 1)   # allow one more hover
            page.evaluate("() => window.__fbx && window.__fbx.running && "
                          "document.querySelectorAll('div[data-fbx-key]').forEach(e => { delete e.dataset.fbxSig; })")
            drain_collector(page, ctx, by_key, skipped)
            after = by_key.get(k)
            if after and (b_state is None or (after["date"], after["url"], len(after["text"])) != b_state):
                fixed += 1
        except KeyboardInterrupt:
            raise
        except Exception:
            continue
    print(f"[+] Repair pass improved {fixed}/{len(todo)} position(s)")
    return len(todo)


def return_to_bottom(page, deepest_key: str = None):
    """After a mid-run repair pass, go back to the deepest CAPTURED post and resume.
    Jumping to the last *loaded* container skipped whatever batch Facebook had
    loaded meanwhile (runs of 5-9 never-seen positions in the audit)."""
    try:
        page.evaluate("(k) => { let el = k ? document.querySelector(`div[data-fbx-key=\"${k}\"]`) : null;"
                      " if (!el) { const e = document.querySelectorAll('div[aria-posinset]'); el = e[e.length - 1]; }"
                      " if (el) el.scrollIntoView({block: 'start'}); }", deepest_key)
        time.sleep(0.4)
        wheel_nudge(page)
        wheel_scroll(page, 600)
        time.sleep(1.0)
    except Exception:
        pass


def write_audit(out_dir: Path, by_key: dict, skipped: dict, target_url: str, extra: list = None):
    """Prove completeness: aria-posinset is sequential per feed, so any position
    between 1 and the highest one seen that is neither collected nor skipped
    was never rendered while we watched."""
    feeds = {}
    for k in list(by_key) + list(skipped):
        f, _, p = k.partition(":")
        if p.isdigit():
            feeds.setdefault(f, set()).add(int(p))
    lines = [f"Scrape audit - {datetime.now():%Y-%m-%d %H:%M:%S}", f"Target: {target_url}", ""]
    total_missing = 0
    for f, seen in sorted(feeds.items()):
        hi = max(seen)
        missing = [i for i in range(1, hi + 1) if i not in seen]
        total_missing += len(missing)
        got = sum(1 for k in by_key if k.startswith(f + ":"))
        skp = sum(1 for k in skipped if k.startswith(f + ":"))
        lines.append(f"Feed {f}: positions 1..{hi}  collected={got}  skipped={skp}  never-seen={len(missing)}")
        if missing:
            lines.append("  never-seen positions: " + ", ".join(map(str, missing[:300])))
    reasons = {}
    for k, r in skipped.items():
        reasons.setdefault(r, []).append(k)
    if reasons:
        lines += ["", "Skipped (by reason):"]
        for r, ks in sorted(reasons.items(), key=lambda x: -len(x[1])):
            lines.append(f"  {len(ks):4d}  {r}   e.g. {', '.join(sorted(ks)[:10])}")
    dated = sum(1 for p in by_key.values() if p["date"] != NO_DATE)
    linked = sum(1 for p in by_key.values() if url_quality(p["url"]) == 3)
    lines += ["", f"Collected posts: {len(by_key)}   with date: {dated}   with post permalink: {linked}"]
    if extra:
        lines += [""] + extra
    (out_dir / "scrape_audit.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines[3:]))
    return total_missing


def extract_posts_from_page(page, ctx: dict) -> list:
    """Extract every not-yet-finished post container currently in the DOM."""
    posts, skips = [], []
    try:
        tagged = page.evaluate(TAG_JS, CONTAINER_SELECTORS)
    except Exception as e:
        print(f"[!] container scan failed: {e}")
        return posts
    try:
        scroll_y = page.evaluate("() => window.scrollY")
    except Exception:
        scroll_y = None
    hovered_any = False
    done_ids = []

    for cid in tagged["ids"]:
        loc = page.locator(f'[data-fbx-id="{cid}"]')
        try:
            data = loc.evaluate(EXTRACT_JS, {"minPhoto": ctx["min_photo"]}, timeout=5000)
        except Exception as e:
            skips.append(f"#{cid}: evaluate failed ({str(e)[:60]})")
            continue

        scrolled_past = data["bottom"] < 0
        post, reason = build_post(data, ctx)
        if reason:
            skips.append(f"#{cid}: {reason}")
            if scrolled_past and "Reels" in reason:
                done_ids.append(cid)
            continue
        h = content_hash(post["text"])
        if needs_hover(post, data, ctx) and h not in ctx["hovered"]:
            ctx["hovered"].add(h)
            hovered_any = True
            apply_hover(post, resolve_via_hover(page, loc))
        posts.append(post)
        if scrolled_past and not data["hasSeeMore"] and not data["pendingImgs"]:
            done_ids.append(cid)

    if done_ids:
        try:
            page.evaluate("(ids) => ids.forEach(i => { const e = document.querySelector(`[data-fbx-id=\"${i}\"]`);"
                          " if (e) e.setAttribute('data-fbx-done', '1'); })", done_ids)
        except Exception:
            pass
    if hovered_any and scroll_y is not None:
        try:
            page.evaluate("(y) => window.scrollTo(0, y)", scroll_y)
        except Exception:
            pass

    if skips and (ctx["debug"] or (tagged["ids"] and not posts)):
        print(f"\n      [trace] {len(tagged['ids'])} container(s) via {tagged['selector']}, {len(posts)} extracted:")
        for r in skips[:8]:
            print(f"      [trace]   {r}")
        if len(skips) > 8:
            print(f"      [trace]   ...and {len(skips) - 8} more")
    return posts


def extract_single_post(page, ctx: dict) -> list:
    print("[+] Single post / share URL - waiting for the post view...")
    time.sleep(4)
    close_dialogs_and_banners(page)
    expand_all_see_more(page)
    for sel in ['div[role="dialog"] div[aria-posinset]', 'div[role="main"] div[aria-posinset]',
                'div[role="dialog"]', 'div[role="main"]']:
        roots = page.locator(sel)
        for k in range(min(roots.count(), 5) - 1, -1, -1):
            root = roots.nth(k)
            try:
                data = root.evaluate(EXTRACT_JS, {"minPhoto": ctx["min_photo"]}, timeout=8000)
            except Exception:
                continue
            text = clean_text("\n\n".join(data["msg"] or data["dirs"]))
            if len(text) < 15:
                continue
            # A share link redirects to the real /posts/pfbid... permalink.
            url = canonical_post_url(page.url)
            if "/photo" in url:
                url = ""
            date = ""
            for l in data["links"]:
                c = canonical_post_url(l.get("href", ""))
                if c and "/photo" not in c and not url:
                    url = c
                if not date:
                    for cand in (l.get("aria", ""), l.get("txt", "")):
                        if looks_like_date(cand):
                            date = cand.strip()
                            break
            if ctx["hover"] and data["tsIndex"] >= 0 and date_quality(date) < 2:
                u2, d2 = resolve_via_hover(page, root)
                if u2 and "/photo" not in u2:
                    url = url or u2
                if date_quality(d2) > date_quality(date):
                    date = d2
            return [{"author": data["author"] or ctx["author_fallback"], "date": date or NO_DATE,
                     "url": url or canonical_post_url(page.url) or page.url, "text": text,
                     "pictures": _pictures_from(data["pics"])}]
    print("[!] Could not find post text on this page.")
    return []


# =============================================================================
# Images
# =============================================================================
def download_images(posts: list, page, out_dir: Path):
    pic_dir = out_dir / "picture"
    pic_dir.mkdir(parents=True, exist_ok=True)
    todo, seen = [], set()
    for p in posts:
        for pic in p.get("pictures", []):
            if pic["filename"] in seen:
                continue
            seen.add(pic["filename"])
            tgt = pic_dir / pic["filename"]
            if not (tgt.exists() and tgt.stat().st_size > 0) and pic.get("src"):
                todo.append((pic, tgt))
    if not todo:
        return
    print(f"\n[+] Downloading {len(todo)} new photo(s) -> {pic_dir}")
    ok = 0
    for pic, tgt in todo:
        body = None
        try:
            resp = page.request.get(pic["src"], timeout=20000)
            if resp.status == 200:
                body = resp.body()
        except Exception:
            pass
        if body is None:  # browser already gone (Ctrl+C) -> plain HTTP; fbcdn URLs are signed, no cookie needed
            try:
                import urllib.request
                req = urllib.request.Request(pic["src"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    body = r.read()
            except Exception as e:
                print(f"[!] photo failed {pic['filename']}: {str(e)[:60]}")
        if body:
            tgt.write_bytes(body)
            ok += 1
    print(f"[+] Photos: {ok}/{len(todo)} downloaded")


# =============================================================================
# Main
# =============================================================================
def main():
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []

    if args.repair_reports:
        repair_reports(output_path.parent)
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[❌] Playwright is not installed. Run:  pip install playwright psutil && "
              "python3 -m playwright install --with-deps chromium")
        sys.exit(1)

    install_signal_handlers()
    user_data_dir = None if args.cdp_url else determine_user_data_dir(args)
    handle = extract_username_from_url(args.url)
    existing = len(parse_markdown_report(output_path))

    if is_wsl_without_gui() and not args.headless:
        print("[⚠️] WSL without a display (no DISPLAY/WAYLAND_DISPLAY). A visible browser can't open.\n"
              "     Run `wsl --update` in Windows (WSLg), then `wsl --shutdown` and reopen Ubuntu,\n"
              "     or use --headless once you're logged in.\n")

    print("=" * 68)
    print(" Facebook Post Extractor v2")
    print(f" Target      : {args.url}")
    print(f" Output      : {output_path}  (already has {existing} posts)")
    print(f" Profile dir : {user_data_dir or args.cdp_url}")
    print(f" Filters     : photos-only={args.photos_only} include-reels={args.include_reels} "
          f"keywords={','.join(keywords) or '-'}")
    print(f" Scrolling   : max {args.scrolls} cycles, stop after {args.stagnant_limit} stagnant")
    print("=" * 68)

    with sync_playwright() as pw:
        if args.cdp_url:
            browser = pw.chromium.connect_over_cdp(args.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            cleanup_stale_profile_lock(user_data_dir)
            launch_kw = dict(
                user_data_dir=str(user_data_dir),
                headless=args.headless,
                viewport={"width": 1280, "height": 900},
                locale="th-TH",
                # Playwright adds --no-sandbox by default; keep Chrome's sandbox ON on Windows
                # (no "unsupported command-line flag" warning bar). Linux/WSL needs it off.
                chromium_sandbox=(sys.platform == "win32"),
                args=([] if sys.platform == "win32" else ["--no-sandbox"]) + [
                      "--disable-notifications", "--disable-infobars",
                      # stability on long runs (the page crashed near post ~1000):
                      "--disable-dev-shm-usage", f"--js-flags=--max-old-space-size={args.js_heap_mb}",
                      "--autoplay-policy=user-gesture-required"] + (["--disable-gpu"] if is_wsl() else []),
            )
            try:
                if args.browser == "chrome":
                    try:
                        context = pw.chromium.launch_persistent_context(channel="chrome", **launch_kw)
                        print("[+] Browser: Google Chrome")
                    except Exception as e:
                        msg = str(e)
                        if "SingletonLock" in msg or "existing browser session" in msg or "already in use" in msg:
                            raise
                        print("[!] Google Chrome not found - using bundled Chromium. Install Chrome with:\n"
                              "      python3 -m playwright install chrome")
                        context = pw.chromium.launch_persistent_context(**launch_kw)
                else:
                    context = pw.chromium.launch_persistent_context(**launch_kw)
                    print("[+] Browser: bundled Chromium")
            except Exception as e:
                if "existing browser session" in str(e) or "already in use" in str(e) or "SingletonLock" in str(e):
                    print(f"\n[❌] Profile is locked. Close any browser from a previous run, then delete\n"
                          f"     {user_data_dir / 'SingletonLock'} and retry.")
                    sys.exit(1)
                raise

        if not args.load_media:
            # Photos/videos are what exhaust the page's memory on a 1000+ post scroll.
            # Blocking them keeps each <img> element, its src and its layout size
            # (verified live), so photo detection still works; files are fetched at
            # the end via page.request, which is not affected by routing.
            def _block(route):
                try:
                    route.abort()
                except Exception:
                    pass
            context.route(re.compile(r"^https://(?:scontent|video|external)[^/]*\.fbcdn\.net/"), _block)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(args.timeout)

        if args.login:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            print("\n[!] Log in to Facebook in the browser window (including 2FA).")
            print("[!] When you can see your News Feed, press ENTER here to save the session...")
            try:
                input()
            except EOFError:
                pass
            context.close()
            print(f"[+] Session saved in {user_data_dir}")
            return

        print(f"\n[+] Opening {args.url}")
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout)
        except Exception as e:
            print(f"[!] Load warning (continuing): {e}")
        time.sleep(3)
        close_dialogs_and_banners(page)
        title = page.title()
        if any(k in page.url.lower() for k in ("login", "checkpoint")) or "เข้าสู่ระบบ" in title or "Log in" in title:
            print("\n[!] Facebook wants a login. Run once with:  python3 extract_posts.py --login")
            if args.headless:
                context.close()
                sys.exit(3)  # 3 = login needed (2 is argparse errors)
            print("[!] Or log in now in the open window - waiting up to 120 s...")
            for _ in range(120):
                time.sleep(1)
                if not any(k in page.url.lower() for k in ("login", "checkpoint")):
                    break
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout)
            time.sleep(3)
            title = page.title()

        ctx = {
            "author_fallback": re.split(r"\s[-|]\s", title)[0].strip() or DEFAULT_AUTHOR,
            "profile_url": f"https://www.facebook.com/{handle}" if handle else "",
            "include_reels": args.include_reels, "hover": not args.no_hover, "hovered": set(),
            "min_photo": args.min_photo, "debug": args.debug, "hover_tries": {},
            "known": PostStore(parse_markdown_report(output_path)),
        }

        if args.urls:
            # Gap-filling mode: fetch specific posts (share links, /posts/ links)
            # and merge them into the same reports as a timeline scrape would.
            posts = []
            for i, u in enumerate(load_url_list(args.urls), 1):
                print(f"\n[+] ({i}) {u}")
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=args.timeout)
                    got = extract_single_post(page, ctx)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"[!] failed: {e}")
                    continue
                for p in got:
                    print(f"      + [{p['date']}] \"{p['text'][:60]}...\"  {p['url']}")
                posts += got
                time.sleep(random.uniform(2, 4))
            kept = save_all_reports(posts, args, output_path, args.url, keywords)
            if not args.no_download_images:
                download_images(kept, page, output_path.parent)
            context.close()
            return

        if is_single_post_view(args.url) or is_single_post_view(page.url):
            posts = extract_single_post(page, ctx)
            kept = save_all_reports(posts, args, output_path, args.url, keywords)
            if not args.no_download_images:
                download_images(kept, page, output_path.parent)
            context.close()
            return

        if args.year:
            print(f"[+] Jumping to year {args.year} (Filters -> Go to: Year)")
            if not apply_year_filter(page, args.year):
                print("[❌] Could not set the year filter - not scraping from the top instead.")
                context.close()
                sys.exit(4)  # 4 = year filter failed; run_until.py stops
            print(f"[+] Feed now starts at the end of {args.year}")

        home_key = _page_key(page.url)
        by_key, skipped = {}, {}          # collector results, keyed "feed:posinset"
        legacy = PostStore()              # fallback if Facebook stops using aria-posinset
        install_collector(page, ctx)

        def current_posts():
            ordered = [by_key[k] for k in sorted(by_key, key=lambda k: (by_key[k]["_feed"], by_key[k]["_pos"]))]
            return PostStore(ordered + [dict(p) for p in legacy.posts]).posts

        def show(p):
            prev = p["text"].replace("\n", " ")[:60]
            pic = f" 🖼️{len(p['pictures'])}" if p["pictures"] else ""
            print(f"\n      + #{p.get('_pos', '?')} [{p['date']}]{pic} \"{prev}...\"", end="")

        stagnant = since_ckpt = 0
        end_reason = f"reached --scrolls limit ({args.scrolls})"
        mem_hist = []

        def mem_probe(cycle):
            try:
                m = page.evaluate("() => ({heap: performance.memory ? performance.memory.usedJSHeapSize : 0,"
                                  " nodes: document.getElementsByTagName('*').length,"
                                  " posts: document.querySelectorAll('div[aria-posinset]').length})")
                line = (f"cycle {cycle}: posts-in-page {m['posts']}, JS heap {m['heap'] / 1e6:.0f} MB, "
                        f"DOM nodes {m['nodes']}")
                mem_hist.append(line)
                print(f"      [mem] {line}")
            except Exception:
                pass
        print(f"\n[+] Scrolling (max {args.scrolls} cycles, 4 steps each, in-page collector active)...")
        try:
            for cycle in range(1, args.scrolls + 1):
                print(f"    - Cycle {cycle}/{args.scrolls} ", end="", flush=True)
                new = upd = 0
                for step in range(4):
                    try:
                        expand_all_see_more(page)
                        ensure_on_target(page, home_key)
                        close_dialogs_and_banners(page)
                        keys, u = drain_collector(page, ctx, by_key, skipped)
                        upd += u
                        for k in keys:
                            show(by_key[k])
                        new += len(keys)
                        if not by_key and page.locator("div[aria-posinset]").count() == 0:
                            for p in extract_posts_from_page(page, ctx):
                                if legacy.add(p) == "added":
                                    new += 1
                                    show(p)
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        print(f"\n[!] extraction error (continuing): {str(e)[:120]}")
                    # Small real-wheel steps (< 1 viewport) so every post is on screen,
                    # rendered, at least once.
                    wheel_scroll(page, random.randint(420, 620))
                    time.sleep(random.uniform(0.35, 0.6))

                total = len(by_key) + len(legacy.posts)
                if new:
                    stagnant = 0
                    since_ckpt += new
                    print(f"\n      -> {total} collected this run (+{new}, {upd} refined, {len(skipped)} skipped)")
                else:
                    stagnant += 1
                    print(f"| 0 new (total {total}, stagnant {stagnant}/{args.stagnant_limit})")

                if args.repair_every and cycle % args.repair_every == 0 and by_key:
                    deep_post = max(by_key.values(), key=lambda p: p["_pos"])
                    deepest = deep_post["_pos"]
                    if repair_pass(page, ctx, by_key, skipped, limit=60, only_before=deepest - 10):
                        return_to_bottom(page, deep_post["_key"])

                if args.checkpoint_every and since_ckpt >= args.checkpoint_every:
                    save_all_reports(current_posts(), args, output_path, args.url, keywords, quiet=True)
                    print(f"      [checkpoint] saved {total} posts")
                    since_ckpt = 0

                if cycle % 20 == 0:
                    mem_probe(cycle)

                if args.max_posts and total >= args.max_posts:
                    end_reason = f"reached --max-posts limit ({args.max_posts})"
                    print(f"\n[i] {end_reason} - stopping.")
                    break

                if stagnant >= args.stagnant_limit and total:
                    end_reason = (f"stagnation: no new posts for {args.stagnant_limit} cycles "
                                  f"(Facebook stopped serving older posts)")
                    print(f"\n[i] No new posts for {args.stagnant_limit} cycles - stopping. If more history "
                          f"should exist, re-run (or use run_until.py) with a higher --stagnant-limit.")
                    break

                if stagnant == 0:
                    time.sleep(random.uniform(0.8, 1.6))
                else:
                    # Progressive backoff + an up/down jiggle, which is what actually
                    # re-triggers Facebook's "load older posts" request.
                    backoff = min(3.0 * stagnant, args.max_backoff)
                    print(f"      [i] waiting {backoff:.0f}s (backoff) ...")
                    wheel_scroll(page, -1200)
                    time.sleep(backoff / 2)
                    wheel_scroll(page, 1500)
                    time.sleep(backoff / 2)
            save_all_reports(current_posts(), args, output_path, args.url, keywords, quiet=True)
            repair_pass(page, ctx, by_key, skipped)
        except KeyboardInterrupt:
            end_reason = "interrupted (Ctrl+C / terminal closed)"
            print("\n[!] Interrupted - saving what was collected...")
        except Exception as e:
            end_reason = f"error: {str(e)[:200]}"
            print(f"\n[❌] Unexpected error (saving partial results): {e}")
            if "crash" in str(e).lower():
                print("    The browser page ran out of memory. Everything collected is saved; the next\n"
                      "    run (run_until.py) skips hovering known posts, so it reaches this depth faster.")
        finally:
            try:
                drain_collector(page, ctx, by_key, skipped)
            except BaseException:
                pass
            posts = current_posts()
            print(f"\n[+] Collected {len(posts)} unique posts this run.")
            # Reports first (fast, pure Python), then the audit, photos last (slow, may fail).
            kept = save_all_reports(posts, args, output_path, args.url, keywords)
            try:
                mem_probe("end")
                write_audit(output_path.parent, by_key, skipped, args.url,
                            extra=[f"Run ended because: {end_reason}"] + ["Memory: " + l for l in mem_hist[-8:]])
                print(f"[i] Run ended because: {end_reason}")
            except Exception as e:
                print(f"[!] audit failed: {e}")
            if not args.no_download_images:
                try:
                    download_images(kept, page, output_path.parent)
                except BaseException as e:
                    print(f"[!] photo download aborted: {e}")
            try:
                context.close()
            except Exception:
                pass
    print("[+] Done.")


if __name__ == "__main__":
    main()
