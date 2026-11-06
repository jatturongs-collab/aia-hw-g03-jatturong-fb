# fb-post-extractor

Collect the posts of a **public Facebook Page** into Markdown files, on **Windows 11 + PowerShell**.

> 🎓 **For academic study only.** No intention to violate anyone's privacy. Use it only on public Pages you are entitled to read, with your own account, slowly, and keep the data private. Read [DISCLAIMER.md](DISCLAIMER.md) first. This repository contains **no scraped data and no login session**.
>
> 🎓 **ใช้เพื่อการศึกษาเท่านั้น** ไม่มีเจตนาละเมิดความเป็นส่วนตัว ใช้กับเพจสาธารณะที่คุณมีสิทธิ์อ่าน ด้วยบัญชีของคุณเอง เก็บข้อมูลเป็นส่วนตัว ดู [DISCLAIMER.md](DISCLAIMER.md)

Facebook's terms restrict automated collection. Your account can be limited or banned. You use this at your own risk.

## Quick start (3 commands)
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1     # once
.\run.ps1 login                                            # once: log in yourself in the Chrome window, press ENTER
.\run.ps1 scrape -Url https://www.facebook.com/WriterTable -Max 20
```
New to this? Follow **[INSTALL-th-en.md](INSTALL-th-en.md)** (Thai + English, step by step).

## What you get
| File | Content |
|---|---|
| `report\All_Post.md` | every collected post (date, permalink, full text after "See more", photos) |
| `report\picture\` | downloaded post photos |
| `report\<TAG>_By_Author.md` | posts with a `#tag` you list in `tags.txt` (optional) |
| `report\keyword_matches.md` | posts matching `-Keywords "a,b"` (optional) |
| `report\scrape_audit.txt` | completeness check: `never-seen=0` means nothing was missed |

Re-running merges by content hash, so posts are never duplicated.

## Commands
`.\run.ps1 login | scrape | scrape-until | test` with options `-Url -Max -Target -Year -Keywords -TagsFile -Headless -PhotosOnly -NoImages -Output`. Full flag list: `.\.venv\Scripts\python.exe extract_posts.py --help`.

## How it works (for study)
Playwright persistent Chrome profile (stored in `%LOCALAPPDATA%\fb-post-extractor`, outside this folder) → real mouse-wheel scrolling (Facebook only fills posts near the viewport for trusted wheel events) → an in-page collector reads `div[aria-posinset]` containers → timestamp hover gives real date and permalink → de-duplication by normalised-text hash → Markdown + audit file. The bug-derived rules are listed in [prompts/create-this-tool.md](prompts/create-this-tool.md).

## For AI assistants
- Skill / command: [.AGENTS/commands/facebook_scrape.md](.AGENTS/commands/facebook_scrape.md)
- Prompt to rebuild the whole tool from scratch: [prompts/create-this-tool.md](prompts/create-this-tool.md)

## Self-test (no Facebook needed)
`.\run.ps1 test` runs the real extractor against a fake timeline (`test\mock_fb.py`). Photo downloads show `403` in the mock because the fake image URLs are not real; that is expected.

## License
MIT, see [LICENSE](LICENSE).
