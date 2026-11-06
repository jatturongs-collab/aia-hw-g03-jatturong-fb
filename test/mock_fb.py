# Test harness: runs the REAL extract_posts.main() against a mock Facebook
# timeline served through Playwright routing.
import base64, json, sys, os, struct, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


def png(w=8, h=8):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


LONG = ("บทวิเคราะห์หุ้นโรงพยาบาล ไตรมาส 3 " * 12).strip()
POSTS = [
    # kind, text, extras
    {"id": 1, "text": LONG + " #VIH ปิดท้าย", "trunc": True, "photos": 2, "ts": "hover",
     "date": "Tuesday, September 15, 2026 at 11:15 AM", "perma": "/WriterTable/posts/pfbid0AAA111"},
    {"id": 2, "text": "RJH# งบออกแล้วครับ กำไรโต 20% ดีกว่าคาด", "photos": 1, "ts": "text2d",
     "photo_link": "/photo/?fbid=999111&set=a.1", "alt_aria": "May be an image of text"},
    {"id": 3, "text": "Reel ของคนอื่นที่ Facebook แทรกเข้ามา สนุกมาก", "reel": True, "ts": "hover",
     "date": "Monday, September 14, 2026 at 3:17 PM", "perma": "/reel/555"},
    {"id": 4, "text": "วันนี้ไปฟังสัมมนากับ October Chris เรื่องการลงทุนระยะยาว", "ts": "hover",
     "date": "Sunday, September 13, 2026 at 1:22 PM", "perma": "/WriterTable/posts/pfbid0DDD444",
     "name_link": "October Chris"},
    {"id": 5, "text": "", "photos": 1, "ts": "hover", "date": "Saturday, September 12, 2026 at 5:03 PM",
     "perma": "/WriterTable/posts/pfbid0EEE555"},
]
for i in range(6, 31):
    POSTS.append({"lab": ("10 November 2025" if i == 9 else (f"{i} hours ago" if i % 2 else "")),"id": i, "text": f"โพสต์ทดสอบลำดับที่ {i} พูดถึง #PR9 และ #KLINIQ อย่างละเอียด" if i % 3 == 0
                  else f"โพสต์ทดสอบลำดับที่ {i} เนื้อหาทั่วไปเกี่ยวกับตลาดหุ้นไทย",
                  "ts": "hover", "date": f"Friday, September {i}, 2026 at 9:0{i % 10} AM",
                  "perma": f"/WriterTable/posts/pfbid0X{i:03d}", "photos": 1 if i % 2 == 0 else 0})
# Older years, for the "Filters -> Go to: Year" path (--year / run_until.py --by-year).
for i, (day, yr) in enumerate([("December 30", 2025), ("November 2", 2025), ("March 3", 2025),
                               ("December 24", 2024), ("June 5", 2024)], 31):
    POSTS.append({"id": i, "text": f"โพสต์เก่าปี {yr} ลำดับ {i} ทบทวนพอร์ตการลงทุนประจำปี",
                  "ts": "hover", "date": f"Monday, {day}, {yr} at 8:00 AM",
                  "perma": f"/WriterTable/posts/pfbid0Y{i:03d}"})
POSTS[8]["text"] = "#RPH ไตรมาส 3/2568 ตัดรายได้อื่นๆ ออก เพื่อวิเคราะห์ธุรกิจหลัก รายได้ 310 ล้านบาท"

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Mock Author | Facebook</title>
<style>body{font-family:sans-serif;width:700px;margin:auto} .post{border:1px solid #ccc;margin:30px 0;padding:10px;min-height:300px}
.ph{width:400px;height:300px;display:block;background:#ddd} .av{width:40px;height:40px}
[role=tooltip]{position:fixed;top:5px;left:5px;background:#000;color:#fff}</style></head>
<body><div role="main"><div role="button" aria-label="Filters" id="filters">Filters</div><div role="feed" id="feed"></div><div id="loading" role="article" aria-busy="true">Loading...</div></div>
<script>
const ALL = __POSTS__;
let POSTS = ALL;
let rendered = 0;
function render(p){
  const d = document.createElement('div'); d.setAttribute('aria-posinset', p.id); d.className='post';
  let h = `<div><a href="/WriterTable" aria-label="profile picture"><svg><image href="x"></image></svg></a>
           <h2><strong><a href="/WriterTable">Mock Author</a></strong></h2>`;
  if (p.ts === 'hover') h += `<span id="lbl${p.id}" style="position:absolute;left:-9999px">${p.lab || ''}</span><span><a class="ts" role="link" tabindex="0" href="?__cft__[0]=AZg${p.id}&__tn__=%2CO%2CP-R#?fgf" ${p.lab ? 'aria-labelledby="lbl'+p.id+'"' : ''}><span style="display:inline-block;width:70px;height:17px"></span></a></span>`;
  else h += `<span><a class="ts2" role="link" href="/WriterTable/posts/pfbid0BBB222?__cft__=zz">2d</a></span>`;
  h += `</div>`;
  if (p.text) {
    const shown = p.trunc ? p.text.slice(0, 80) + '… ' : p.text;
    h += `<div data-ad-rendering-role="story_message"><div data-ad-preview="message"><div dir="auto" class="msg">${shown}`
       + (p.trunc ? `<div role="button" class="more">See more</div>` : '') + `</div></div></div>`;
  }
  if (p.name_link) h += `<a href="/october.chris" aria-label="October Chris">${p.name_link}</a>`;
  for (let k = 0; k < (p.photos||0); k++) {
    const link = p.photo_link || `/photo/?fbid=${p.id}00${k}&set=a.9`;
    h += `<a href="${link}" aria-label="${p.alt_aria || 'photo'}"><img class="ph" loading="lazy" alt="May be an image of text" src="https://scontent.fbkk5-1.fna.fbcdn.net/v/t39/${p.id}_${k}.jpg?oh=abc&oe=1"></a>`;
  }
  if (p.reel) h += `<a href="/reel/555">Reel</a>`;
  h += `<img class="av" src="https://scontent.fbkk5-1.fna.fbcdn.net/v/t1/avatar_${p.id}.jpg">`;
  h += `<img src="https://static.xx.fbcdn.net/images/emoji.php/v9/t51/1/16/1f600.png" style="width:16px">`;
  h += `<div role="button">Like</div><div role="button">Comment</div>`;
  h += `<div role="article" aria-label="Comment by Someone"><div dir="auto">นี่คือคอมเมนต์ของคนอื่นยาวเกินยี่สิบตัวอักษรแน่นอน #VIH</div>
        <a href="/WriterTable/posts/pfbid0COMMENT?comment_id=1" aria-label="3d">3d</a>
        <img src="https://scontent.fbkk5-1.fna.fbcdn.net/v/t39/comment_sticker.jpg" style="width:200px;height:200px"></div>`;
  d.innerHTML = h;
  const more = d.querySelector('.more');
  if (more) more.addEventListener('click', () => { d.querySelector('.msg').innerHTML = p.text + '<div role="button">See less</div>'; });
  const ts = d.querySelector('.ts');
  if (ts) ts.addEventListener('mouseenter', () => {
    ts.href = p.perma + '?__cft__[0]=AZZ&__tn__=%2CO';
    let tip = document.querySelector('[role=tooltip]');
    if (!tip) { tip = document.createElement('div'); tip.setAttribute('role','tooltip'); document.body.appendChild(tip); }
    tip.textContent = p.date;
  });
  document.getElementById('feed').appendChild(d);
}
const store = {};
function virtualize(){
  const vh = window.innerHeight;
  for (const el of Array.from(document.querySelectorAll('#feed > div[aria-posinset]'))) {
    const r = el.getBoundingClientRect();
    const far = r.bottom < -0.8 * vh || r.top > 1.8 * vh;
    const id = el.getAttribute('aria-posinset');
    if (far && !el.dataset.hollow) {
      store[id] = Array.from(el.childNodes); el.style.height = r.height + 'px';
      el.innerHTML = '<span>Facebook</span><span>Facebook</span>'; el.dataset.hollow = '1';
    } else if (!far && el.dataset.hollow && window.__trustedWheel) {  // real FB: refill only on real wheel input
      el.innerHTML = ''; store[id].forEach(n => el.appendChild(n)); el.style.height = ''; delete el.dataset.hollow;
    }
  }
}
window.addEventListener('scroll', virtualize);
window.addEventListener('wheel', e => { if (!e.isTrusted) return; window.__trustedWheel = true;
  setTimeout(() => { virtualize(); window.__trustedWheel = false; }, 60); }, {passive: true});
function more(n){ for (let i=0;i<n && rendered<POSTS.length;i++) render(POSTS[rendered++]); }
more(4);
// "Filters -> Go to: Year" dialog, shaped like the live one (1 Oct 2026). The URL does not change.
document.getElementById('filters').addEventListener('click', () => {
  const dlg = document.createElement('div'); dlg.setAttribute('role', 'dialog');
  dlg.innerHTML = `<div>Post filters</div><div>Go to:</div>
    <div role="combobox" tabindex="0" aria-label="Edit ending date  year. Current selection is none">Year</div>
    <div role="button" class="done">Done</div><div role="button">Clear</div>`;
  document.body.appendChild(dlg);
  let picked = null;
  const combo = dlg.querySelector('[role=combobox]');
  combo.addEventListener('click', () => {
    const lb = document.createElement('div'); lb.setAttribute('role', 'listbox');
    for (const y of ['Year', 2026, 2025, 2024, 2023]) {
      const o = document.createElement('div'); o.setAttribute('role', 'option'); o.textContent = y;
      o.addEventListener('click', () => { picked = y === 'Year' ? null : y; lb.remove();
        combo.setAttribute('aria-label', 'Edit ending date  year. Current selection is ' + (picked || 'none')); });
      lb.appendChild(o);
    }
    document.body.appendChild(lb);
  });
  dlg.querySelector('.done').addEventListener('click', () => {
    dlg.remove();
    const yearOf = p => { const m = /\b(20\d\d)\b/.exec(p.date || ''); return m ? +m[1] : 2026; };
    POSTS = picked ? ALL.filter(p => yearOf(p) <= picked) : ALL;
    POSTS = POSTS.map((p, i) => Object.assign({}, p, {id: i + 1}));  // aria-posinset restarts at 1
    document.getElementById('feed').innerHTML = ''; rendered = 0; more(4);
  });
});
let busy=false;
window.addEventListener('scroll', () => {
  if (busy || rendered >= POSTS.length) return;
  if (window.innerHeight + window.scrollY > document.body.scrollHeight - 1500) {
    busy = true; setTimeout(() => { more(3); busy = false; }, 700);
  }
});
</script></body></html>"""


def install_routes(ctx):
    img = png()
    def handle(route):
        u = route.request.url
        if "scontent" in u or "fbcdn" in u:
            return route.fulfill(status=200, body=img, content_type="image/png")
        if "/WriterTable" in u and "/posts/" not in u:
            return route.fulfill(status=200, body=PAGE.replace("__POSTS__", json.dumps(POSTS, ensure_ascii=False)),
                                 content_type="text/html; charset=utf-8")
        return route.fulfill(status=200, body="<html><title>other</title><body>other page</body></html>",
                             content_type="text/html")
    ctx.route("**/*", handle)


if __name__ == "__main__":
    from playwright.sync_api import BrowserType
    orig = BrowserType.launch_persistent_context

    def patched(self, *a, **kw):
        ctx = orig(self, *a, **kw)
        install_routes(ctx)
        return ctx
    BrowserType.launch_persistent_context = patched

    import extract_posts
    args = sys.argv[1:]
    # Never let a bare run fall back to the real profile / report/All_Post.md: the mock's
    # posts would be merged into the real report.
    if not any(a == "--output" or a.startswith("--output=") for a in args):
        args += ["--output", str(HERE / "out" / "All_Post.md")]
    if not any(a == "--user-data-dir" or a.startswith("--user-data-dir=") for a in args):
        args += ["--user-data-dir", str(HERE / "profile")]
    if "--headless" not in args:
        args.append("--headless")
    sys.argv = ["extract_posts.py"] + args
    extract_posts.main()
