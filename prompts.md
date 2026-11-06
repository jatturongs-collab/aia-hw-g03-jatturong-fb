# บันทึกขั้นตอน (process log)

> เพิ่ม 1 entry ทุกครั้งก่อน commit ต่อท้ายไฟล์ ห้ามลบของเก่า
> ผู้สอนอ่านไฟล์นี้เพื่อดูวิธีคิดของคุณ ไม่ใช่แค่ผลงานสุดท้าย
> ถ้าใช้ AI ช่วยทำงาน AI จะเขียน entry ให้ตาม AGENTS.md ถ้า commit เอง ให้เขียนเองตามแบบด้านล่าง

---

## รอบ 1 · 2026-11-06

- **ทำอะไร:** ให้ AI อ่านเครื่องมือ Facebook scraper ส่วนตัว (WSL) ที่เคยทำไว้ แล้ววางแผนทำใหม่ให้รันบน Windows 11 + PowerShell และแชร์ได้ (ยังไม่เขียนโค้ด)
- **เครื่องมือ / model:** Claude Desktop (Code) · Sonnet 5.5 · Plan mode
- **Prompt ที่ใช้:**

```text
I have python script for fetch facebook in this folder D:\AI_Training\Project\fetch_fb .
There is readme and claude md file that you could learn and benefit.

Target of this objective:
I would like you do reverse engineer as following .

1. I need python script run on power shell + win11
2. skill create and description it this folder สร้างไฟล์ .AGENTS/commands/facebook_scrape.md
3. the prompt instruction that people to do create
4. push and share into GitHub that everyone could clone and install in there machine.
5. Instruction how to install  no.4  for none technical people.

Put some note that this is for academy study . no intention to violate privacy,

where do you think you will output file.
```

- **ผลที่ได้:** AI อ่าน README/CLAUDE.md/สคริปต์เดิม พบว่าเครื่องมือเดิมผูกกับ WSL, ตั้งค่าเริ่มต้นเป็นไทม์ไลน์ของบุคคลหนึ่ง และมีโพสต์/รูป/Chrome profile ที่ล็อกอินแล้วในโฟลเดอร์ จึงเสนอแผนใหม่ที่ไม่เอาข้อมูลเหล่านั้นไปด้วย แผนอยู่ที่ output โฟลเดอร์ใหม่ `fb-post-extractor`
- **ตัดสินใจอะไร และเพราะอะไร:** เลือกตามตัวเลือกที่ AI เสนอ — ไม่มีเป้าหมายเริ่มต้นเป็นบุคคล แต่ใช้เพจสาธารณะ `WriterTable` (เหตุผลที่ AI เสนอ: repo เป็น Public ไม่ควรมีชื่อบุคคลจริงเป็นค่าเริ่มต้น) · ติดตั้งแบบ Windows ตรง ๆ ด้วย `install.ps1` ไม่ใช้ WSL (เหตุผลที่ AI เสนอ: มือใหม่ติดตั้ง WSL ยาก) · ขอบเขต "Everything" คือพอร์ตทุกสคริปต์ [เหตุผลของผู้เรียน: รอผู้เรียนเติม]
- **ขั้นต่อไป:** ลงมือสร้างเครื่องมือ ทดสอบ แล้วเก็บไว้ในเครื่องก่อน

---

## รอบ 2 · 2026-11-06

- **ทำอะไร:** สร้างและทดสอบเครื่องมือ: พอร์ต `extract_posts.py`/`run_until.py`/`merge_reports.py`, เขียน `install.ps1`, `run.ps1`, skill `.AGENTS/commands/facebook_scrape.md`, prompt สร้างใหม่, README, DISCLAIMER, คู่มือติดตั้ง ไทย/English
- **เครื่องมือ / model:** Claude Desktop (Code) · Sonnet 5.5
- **Prompt ที่ใช้:**

```text
(ตอบแผนรอบ 1) approve — เลือก: ไม่มี default บุคคลโดยใช้ https://www.facebook.com/WriterTable ·
repo ชื่อ fb-post-extractor แบบ public · Native Windows + install.ps1 · พอร์ต Everything
```

```text
Keep it local
```

- **ผลที่ได้:** `install.ps1` ติดตั้งสำเร็จ และ `run.ps1 test` ผ่านบนหน้า Facebook จำลอง (ตัวกรองปี 2025 คืนเฉพาะปี 2025/2024, `--max-posts`, `--tags` ใช้ได้) เพิ่ม `--max-posts` และ `--tags/--tags-file` ยังไม่ได้ทดสอบ login/ดึงจริง commit ในเครื่อง `d07d6eb`
- **ตัดสินใจอะไร และเพราะอะไร:** เก็บไว้ในเครื่องก่อน ไม่ push (ผู้เรียนสั่ง "Keep it local" [เหตุผล: รอผู้เรียนเติม])
- **ขั้นต่อไป:** ผู้เรียนสร้าง repo การบ้านจาก template แล้วรวมงานเข้าไป

---

## รอบ 3 · 2026-11-06

- **ทำอะไร:** ตรวจ template การบ้านใน GitHub, เปลี่ยนชื่อ repo เป็น `aia-hw-g03-jatturong-fb`, รวมประวัติ git ของเครื่องมือกับ template, ผสม README และ .gitignore, กรอก spec/prompts/PROJECT_MEMORY/help/output
- **เครื่องมือ / model:** Claude Desktop (Code) · Sonnet 5.5 · Plan mode แล้วลงมือหลังอนุมัติแผน
- **Prompt ที่ใช้:**

```text
I have create the github  https://github.com/jatturongs-collab/fb-post-extractor-  , could you check the template and try to fill in or may be we can discuss first.
```

```text
proceed  approve the plan
```

- **ผลที่ได้:** repo เปลี่ยนชื่อสำเร็จ รวมประวัติได้ มี conflict เฉพาะ `README.md` กับ `.gitignore` ซึ่งแก้โดยรวมเนื้อหาสองฝั่ง และเพิ่มข้อห้าม "ห้ามขึ้น repo: โพสต์/รูป/profile ที่ดึงมา"
- **ตัดสินใจอะไร และเพราะอะไร:** เปลี่ยนชื่อ repo ให้ตรงรูปแบบ `aia-hw-<กลุ่ม>-<ชื่อเล่น>` เพราะ AGENTS.md ของ template ตรวจชื่อโฟลเดอร์ขึ้นต้นด้วย `aia-hw-` · วางเครื่องมือที่ root และคงไฟล์ template ไว้ครบ [เหตุผลของผู้เรียน: รอผู้เรียนเติม]
- **ขั้นต่อไป:** ผู้เรียนทดสอบ `login` และ `scrape -Max 5` จริง, ยืนยัน/แก้ `help.md` ทั้ง 3 ข้อ, ตัดสินใจ push (repo เป็น Public) และเติมรอบที่ 4 เมื่อมีงานเพิ่ม (เกณฑ์ขั้นต่ำของ template คือ 3 รอบ)
