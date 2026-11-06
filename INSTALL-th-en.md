# วิธีติดตั้ง สำหรับมือใหม่ / Install guide for beginners (Windows 11)

> ⚠️ ใช้เพื่อการศึกษาเท่านั้น ไม่มีเจตนาละเมิดความเป็นส่วนตัว อ่าน [DISCLAIMER.md](DISCLAIMER.md) ก่อน
> ⚠️ For academic study only. No intention to violate privacy. Read [DISCLAIMER.md](DISCLAIMER.md) first.

ใช้เวลาประมาณ 10 นาที / Takes about 10 minutes. คุณต้องมี **Google Chrome** และบัญชี Facebook ของตัวเอง
You need **Google Chrome** and your own Facebook account.

## ภาษาไทย

### ขั้นที่ 1 — ติดตั้ง Python (ครั้งเดียว)
1. กดปุ่ม **Start** พิมพ์ `PowerShell` แล้วกด Enter
2. คัดลอกคำสั่งนี้ไปวาง แล้วกด Enter
   ```powershell
   winget install Python.Python.3.12
   ```
3. ปิดหน้าต่าง PowerShell แล้วเปิดใหม่ (สำคัญ)

### ขั้นที่ 2 — ดาวน์โหลดโปรแกรม
**วิธีง่าย (ไม่ต้องใช้ git):** เปิดหน้า GitHub ของโปรเจกต์ กดปุ่มสีเขียว **Code** → **Download ZIP** → คลิกขวาไฟล์ ZIP → **Extract All** (แตกไฟล์)

**วิธี git:**
```powershell
git clone https://github.com/jatturongs-collab/aia-hw-g03-jatturong-fb.git
```

### ขั้นที่ 3 — เปิด PowerShell ในโฟลเดอร์โปรแกรม
เปิดโฟลเดอร์ที่แตกไฟล์ → คลิกขวาที่ว่าง ๆ → **Open in Terminal** (เปิดใน Terminal)

### ขั้นที่ 4 — ติดตั้งโปรแกรม (ครั้งเดียว)
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
รอจนเห็น `== 4/4 Done ==`

### ขั้นที่ 5 — ทดสอบแบบไม่ต้องใช้ Facebook (ไม่บังคับ)
```powershell
.\run.ps1 test
```
ถ้าขึ้น `never-seen=0` แปลว่าระบบทำงานปกติ

### ขั้นที่ 6 — ล็อกอิน Facebook (ครั้งเดียว)
```powershell
.\run.ps1 login
```
หน้าต่าง Chrome จะเปิดขึ้น ให้ **ล็อกอินเอง** (รวมการยืนยันตัวตน 2 ชั้นถ้ามี) เมื่อเห็นหน้าแรก Facebook ให้กลับมากด **Enter** ใน PowerShell
> โปรแกรมไม่เคยเห็นรหัสผ่านของคุณ ระบบจำการล็อกอินไว้ในเครื่องคุณเท่านั้น

### ขั้นที่ 7 — ดึงโพสต์ (ลองเล็ก ๆ ก่อน)
```powershell
.\run.ps1 scrape -Url https://www.facebook.com/WriterTable -Max 20
```
อย่าปิดหน้าต่าง Chrome ที่เปิดขึ้นมาระหว่างทำงาน เมื่อเสร็จ ผลอยู่ที่โฟลเดอร์ `report`:
- `report\All_Post.md` — โพสต์ทั้งหมด
- `report\picture\` — รูปภาพ
- `report\scrape_audit.txt` — ถ้ามี `never-seen=0` แปลว่าไม่ตกหล่น

### แก้ปัญหา
| อาการ | วิธีแก้ |
|---|---|
| `running scripts is disabled` | ใช้คำสั่งที่มี `-ExecutionPolicy Bypass` ตามขั้นที่ 4 และรัน `.\run.ps1` ด้วย `powershell -ExecutionPolicy Bypass -File .\run.ps1 scrape ...` |
| `Python 3.10+ not found` | ทำขั้นที่ 1 ใหม่ แล้วปิด-เปิด PowerShell |
| ขึ้นว่าต้องล็อกอิน (exit code 3) | รัน `.\run.ps1 login` ใหม่ |
| ภาษาไทยเป็นสี่เหลี่ยม/อักษรเพี้ยน | เปิดไฟล์ `.md` ด้วย VS Code, Notepad หรือ Obsidian (UTF-8) |
| `Profile is locked` | ปิด Chrome ที่โปรแกรมเปิดไว้ทั้งหมด แล้วรันใหม่ |
| Facebook ขึ้นหน้าตรวจสอบความปลอดภัย | หยุดใช้ 1 วัน แล้วลดจำนวนโพสต์ต่อรอบ อย่ารันถี่ |
| Windows SmartScreen เตือน | เป็นสคริปต์ที่ไม่ได้ลงนาม ตรวจโค้ดเองก่อนรัน หรือเลือก **Run anyway** ถ้าคุณเชื่อถือ |

---

## English

1. **Install Python (once):** open PowerShell, run `winget install Python.Python.3.12`, then close and reopen PowerShell.
2. **Get the program:** on the GitHub page click green **Code → Download ZIP** and extract it, or `git clone https://github.com/jatturongs-collab/aia-hw-g03-jatturong-fb.git`.
3. **Open PowerShell in that folder:** right-click empty space → **Open in Terminal**.
4. **Install (once):** `powershell -ExecutionPolicy Bypass -File .\install.ps1`
5. **Optional self-test (no Facebook):** `.\run.ps1 test`
6. **Log in (once):** `.\run.ps1 login` — a Chrome window opens, log in yourself, then press ENTER in PowerShell. The tool never sees your password.
7. **Collect posts (start small):** `.\run.ps1 scrape -Url https://www.facebook.com/WriterTable -Max 20`

Results: `report\All_Post.md`, `report\picture\`, `report\scrape_audit.txt` (`never-seen=0` = nothing missed).

If PowerShell blocks scripts, prefix with `powershell -ExecutionPolicy Bypass -File .\run.ps1 <command>`.

## ถอนการติดตั้ง / Uninstall
ลบโฟลเดอร์โปรแกรม และลบโฟลเดอร์ล็อกอิน `%LOCALAPPDATA%\fb-post-extractor` (พิมพ์ในช่อง Address ของ File Explorer)
Delete the program folder and `%LOCALAPPDATA%\fb-post-extractor` (type it in the File Explorer address bar). Also log out of unused sessions in Facebook → Settings → Security.
