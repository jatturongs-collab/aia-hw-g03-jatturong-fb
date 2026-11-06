# fb-post-extractor · เครื่องมือรวบรวมโพสต์เพจสาธารณะบน Windows

> การบ้าน AI Investor Alpha · Day 1 → Day 2

| | |
|---|---|
| **ชื่อเล่น** | jatturong |
| **กลุ่ม** | g03 · เครื่องมือรวบรวมโพสต์นักลงทุน |
| **โจทย์ 1 บรรทัด** | ใช้ AI สร้างเครื่องมือบน Windows 11 + PowerShell ที่รวบรวมโพสต์ของเพจ Facebook สาธารณะลงไฟล์ Markdown อย่างปลอดภัย ตรวจความครบถ้วนได้ เพื่อใช้ศึกษาเท่านั้น |
| **ลิงก์ผลงาน** | ดูใน `output/` |
| **สถานะ** | ร่างแรก |

> 🎓 **For academic study only.** No intention to violate anyone's privacy. Use it only on public Pages you are entitled to read, with your own account, slowly, and keep the data private. Read [DISCLAIMER.md](DISCLAIMER.md) first. This repository contains **no scraped data and no login session**.
>
> 🎓 **ใช้เพื่อการศึกษาเท่านั้น** ไม่มีเจตนาละเมิดความเป็นส่วนตัว ใช้กับเพจสาธารณะที่คุณมีสิทธิ์อ่าน ด้วยบัญชีของคุณเอง เก็บข้อมูลเป็นส่วนตัว ห้ามนำข้อมูลที่ดึงมาขึ้น repo นี้ ดู [DISCLAIMER.md](DISCLAIMER.md)
>
> Facebook's terms restrict automated collection. Your account can be limited or banned. Use at your own risk. / ข้อกำหนดของ Facebook จำกัดการเก็บข้อมูลอัตโนมัติ บัญชีอาจถูกจำกัดหรือระงับ

---

## เครื่องมือนี้ทำอะไร (Quick start)

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1     # ครั้งเดียว (ปลดล็อกไฟล์ที่ดาวน์โหลดมาด้วย)
.\run.ps1 login                                            # ครั้งเดียว: ล็อกอินเองในหน้าต่าง Chrome แล้วกด ENTER
.\run.ps1 scrape -Url https://www.facebook.com/WriterTable -Max 20
```
มือใหม่ ดู **[INSTALL-th-en.md](INSTALL-th-en.md)** (ไทย + English ทีละขั้น) ทดสอบโดยไม่ใช้ Facebook: `.\run.ps1 test`

| ผลลัพธ์ (อยู่ในเครื่องคุณ ไม่ขึ้น repo) | ความหมาย |
|---|---|
| `report\All_Post.md` | โพสต์ทั้งหมด (วันที่ ลิงก์ ข้อความเต็ม รูป) |
| `report\scrape_audit.txt` | ตรวจความครบ: `never-seen=0` = ไม่ตกหล่น |
| `report\<TAG>_By_Author.md` | แยกตาม #tag (ถ้าใส่ `-TagsFile`) |

วิธีทำงาน: Playwright + Chrome profile ในเครื่อง (`%LOCALAPPDATA%\fb-post-extractor`) → เลื่อนด้วย mouse wheel จริง → อ่านโพสต์จาก `div[aria-posinset]` → hover เวลาเพื่อได้วันที่/ลิงก์จริง → กันซ้ำด้วย hash ข้อความ

สำหรับ AI: skill [.AGENTS/commands/facebook_scrape.md](.AGENTS/commands/facebook_scrape.md) · prompt สร้างเครื่องมือใหม่ทั้งชุด [prompts/create-this-tool.md](prompts/create-this-tool.md)

---

## ไฟล์ใน repo นี้

| ไฟล์ | ใส่อะไร |
|---|---|
| `spec.md` | โจทย์ของคุณ 5 หัวข้อ (หัวใจของการบ้าน) |
| `prompts.md` | บันทึกขั้นตอนทุกรอบ: ทำอะไร, prompt, ผลที่ได้, ตัดสินใจเพราะอะไร |
| `PROJECT_MEMORY.md` | ปัญหาที่เจอ, วิธีแก้, และกฎที่ได้จากบทเรียน |
| `output/` | ผลทดสอบ (ข้อมูลจำลองเท่านั้น) และลิงก์ผลงาน |
| `help.md` | ติดตรงไหน 3 ข้อ ให้ผู้สอนเตรียมคำตอบ |
| `AGENTS.md` | คำสั่งให้ AI ทุกค่ายทำงานใน repo นี้ (`CLAUDE.md` และ `GEMINI.md` ชี้มาที่ไฟล์นี้) |
| `.claude/commands/save.md` | ขั้นตอนของคำสั่ง `/save` |
| `extract_posts.py` `run_until.py` `merge_reports.py` | ตัวเครื่องมือ (Python) |
| `install.ps1` `run.ps1` | ติดตั้งและสั่งงานผ่าน PowerShell |
| `test/` | ชุดทดสอบกับหน้า Facebook จำลอง |
| `DISCLAIMER.md` `INSTALL-th-en.md` `LICENSE` | ข้อสงวนสิทธิ์ · วิธีติดตั้งสำหรับมือใหม่ · MIT |

## ก่อนเริ่มทำการบ้านทุกครั้ง

- [ ] เปิดโฟลเดอร์ `homework/aia-hw-…` ของคุณเป็นที่ทำงานใน Claude
- [ ] ถามว่า "ตอนนี้ทำถึงไหน" Claude ต้องตอบจาก `prompts.md` ได้ (ถ้าตอบไม่ได้ = เปิดผิดโฟลเดอร์)
- [ ] เช็ก model · effort · permission
- [ ] ดูคอมเมนต์ผู้สอนในแท็บ Issues ของ repo บน GitHub

ระหว่างทำ: เปิด Plan mode ก่อนงานใหม่ · ทำทีละรอบ · ทุกตัวเลขต้องมี source · ติดตรงไหนจดลง `help.md`

## บันทึกงานทุกรอบ: พิมพ์ `/save`

ทำงานเสร็จแต่ละรอบ ให้พิมพ์ `/save` ใน Claude (ใส่สรุปสั้น ๆ ต่อท้ายได้ เช่น `/save ร่าง spec รอบแรก`) AI จะทำให้ครบ:

1. ตรวจว่าไม่มี key หรือข้อมูลส่วนตัว
2. เพิ่มบันทึกขั้นตอนใน `prompts.md`
3. บันทึกปัญหาและบทเรียนใน `PROJECT_MEMORY.md` ถ้ามี
4. commit ด้วยข้อความ `รอบ N: ทำอะไร` แล้ว push ขึ้น GitHub

ใช้ Codex หรือ Gemini: พิมพ์ว่า `save` ได้เหมือนกัน (ขั้นตอนเดียวกัน อยู่ใน `.claude/commands/save.md`)

ถ้า commit เองหรืออัปโหลดผ่านหน้าเว็บ GitHub ให้เขียน entry ใน `prompts.md` เองตามแบบฟอร์มในไฟล์

## ไทม์ไลน์

| วัน | ทำอะไร |
|---|---|
| เสาร์ 31 ต.ค. · 17:45 | repo + spec ร่างแรก |
| **พุธ 4 พ.ย. · 21:00** | **Deadline: ส่งฉบับพร้อมตรวจ** |
| พฤ–ศ 5–6 พ.ย. | ผู้สอนคอมเมนต์ใน Issues ของ repo นี้ |
| เสาร์ 7 พ.ย. · 13:30 | Repair Clinic ในห้อง |

ส่งลิงก์ repo ครั้งเดียวในวันเรียน ผ่าน **Google Form ที่ผู้สอนแจกในห้อง (สแกน QR บนจอ)** งานที่ `/save` เพิ่มภายหลังจะอัปเดตใน repo เอง ไม่ต้องส่งซ้ำ

## ห้ามขึ้น Public

repo นี้ใครก็เปิดดูได้ ห้ามใส่สิ่งเหล่านี้เด็ดขาด

- API key · password · token · ไฟล์ `.env`
- พอร์ตจริง · จำนวนหุ้น · เลขบัญชี · ข้อมูลส่วนตัว
- ข้อมูล SETSMART ที่ซื้อมา (ไฟล์ดิบ)
- บทวิเคราะห์โบรกเกอร์ (ติดลิขสิทธิ์)
- **โพสต์ รูป หรือ Chrome profile ที่ดึงมาจาก Facebook** (ข้อมูลส่วนบุคคล/ลิขสิทธิ์ของผู้อื่น และ profile มี session ล็อกอิน)

ถ้าเผลอ push key ขึ้นไปแล้ว: **เปลี่ยน key ใหม่ทันที** การลบไฟล์ทิ้งอย่างเดียวไม่พอ เพราะประวัติใน git ยังเก็บไว้

## เช็กก่อนส่ง

- [ ] repo เป็น Public และเปิดได้จากหน้าต่าง incognito
- [ ] `spec.md` ครบ 5 หัวข้อ
- [ ] `prompts.md` มีบันทึกอย่างน้อย 3 รอบ และทุก commit มี entry คู่กัน
- [ ] `PROJECT_MEMORY.md` มีปัญหาหรือบทเรียนอย่างน้อย 1 ข้อ
- [ ] `output/` มีภาพหรือลิงก์อย่างน้อย 1 ชิ้น
- [ ] `help.md` เขียนครบ 3 ข้อ
- [ ] ไม่มี key, password หรือข้อมูลพอร์ตจริงในทุกไฟล์
- [ ] ส่งลิงก์แล้ว

## License
MIT, see [LICENSE](LICENSE).
