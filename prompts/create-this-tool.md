# Prompt: recreate this tool with any AI coding assistant

Copy everything inside the box into Claude Code / Codex / Gemini CLI, in an empty folder.

> For academic study only. No intention to violate anyone's privacy. Use on public Pages with your own account.

```text
You are building a Windows 11 + PowerShell tool, "fb-post-extractor", for ACADEMIC STUDY of public
Facebook Pages (learning browser automation, DOM analysis, de-duplication).

GOAL
Collect the posts of a public Facebook Page timeline into Markdown reports.

SAFETY RULES (non-negotiable)
- Never ask for, read, store or print a password, cookie or token. Login is manual: open a visible
  Chrome window, the user logs in (incl. 2FA) and presses ENTER. The session lives only in a
  persistent browser profile at %LOCALAPPDATA%\fb-post-extractor\profile (never inside the repo).
- No default target that is a private person. Default = a public Page; the user passes --url.
- Be slow and polite: human-like wheel scrolling, random delays, growing back-off when no new posts,
  cool-downs between runs, stop on any checkpoint/security page. No proxies, no evasion tricks.
- Ship no scraped data, photos or profiles. .gitignore: profile dirs, report*/, logs, .venv.
- README, INSTALL and the skill file start with the academic-use / privacy notice.

STACK
Python 3.10+, Playwright (sync API) with launch_persistent_context(channel="chrome", fallback bundled
Chromium), psutil. One venv (.venv). PowerShell: install.ps1 (no admin) and run.ps1 (login, scrape,
scrape-until, test). Set UTF-8 in PowerShell and Python (Thai text).

CLI (extract_posts.py)
--url, --output report/All_Post.md, --scrolls, --max-posts, --stagnant-limit, --max-backoff,
--checkpoint-every, --keywords, --tags / --tags-file (per-#tag files), --photos-only,
--include-reels, --no-hover, --no-download-images, --load-media, --year, --login, --user-data-dir,
--browser chrome|chromium, --cdp-url, --headless, --repair-every, --js-heap-mb, --debug.
Exit codes: 3 = login needed, 4 = --year filter failed. Also run_until.py (loop with cool-downs,
--by-year) and merge_reports.py (merge report folders, newest first).

OUTPUT
report/All_Post.md (every post, merged incrementally, never duplicated), report/<TAG>_By_Author.md,
report/keyword_matches.md, report/picture/fb_<hash>.jpg, report/scrape_audit.txt
(lists feed positions 1..N collected/skipped/never-seen; never-seen=0 means nothing missed).

HARD-WON RULES (each was a real bug - implement them from the start)
1. Post containers are div[aria-posinset]. role="article" is only comments/placeholders; ignore
   everything inside a nested role="article".
2. Never gate on is_visible(); virtualized rows can have zero size. Decide by extracted text length.
3. Dates: strict regex only (<digits><unit> as the WHOLE string, or month name next to a day number).
   Real date + permalink come from hovering the header timestamp link (tooltip + filled href);
   snapshot tooltips before hovering so a stale one is never read.
4. One evaluate() per post with a short timeout, per-element loops capped, each item in try/catch.
5. Photo size via getBoundingClientRect(), not naturalWidth. 0x0 = not laid out yet: revisit.
6. try/finally around the scroll loop, checkpoints every N posts, SIGTERM/Ctrl+C -> KeyboardInterrupt;
   write reports before downloading photos. (SIGHUP does not exist on Windows - guard it.)
7. Only ~4-7 posts nearest the viewport hold content; hollow posts refill ONLY with real wheel events
   (page.mouse.wheel). window.scrollBy/scrollIntoView leave them empty. Nudge with a wheel after
   any scrollIntoView.
8. Capture with an in-page collector (setInterval ~350 ms) keyed by feed:posinset; Python drains it.
   A repair pass revisits never-seen/hollow/undated positions every N cycles and at the end.
9. Dedup key = md5 of normalized text (collapse whitespace, strip trailing "See more/See less" and
   ellipsis); a truncated copy that is a prefix (>=40 chars) of a longer text merges into it.
10. Keep ?fbid= on /photo/ links. Exclude /reel/ unless --include-reels.
11. Block *.fbcdn.net media while scrolling (memory: tabs crashed near post ~1000); download files at
    the end with page.request. Raise JS heap via --js-flags=--max-old-space-size.
12. --year Y: open Filters -> "Edit ending date year" combobox -> pick year -> Done; failure = exit 4,
    never silently scrape from the top.
13. On Windows never call os.kill(pid, 0) (it terminates the process); use psutil.pid_exists.

TESTS
test/mock_fb.py serves a fake timeline through Playwright routing (hollowing + wheel-only refill,
"See more", comments, Reels, lazy photos, infinite scroll) and runs the real main(). It must force
--output/--user-data-dir to test folders. Add a negative control that uses programmatic scrolling
and must do worse.

SKILL FILE
.AGENTS/commands/facebook_scrape.md (frontmatter: description, argument-hint) with ordered steps:
check permission/target, install, login (user does it), scrape small first, read scrape_audit.txt,
report counts and paths, never invent posts, never commit report/ or the profile.

DELIVERABLES
README.md (EN+TH), INSTALL-th-en.md for non-technical users, DISCLAIMER.md, LICENSE (MIT),
install.ps1, run.ps1, requirements.txt, .gitignore, the skill file. Work step by step, run the mock
tests on Windows, and show me the test output before saying it is done.
```
