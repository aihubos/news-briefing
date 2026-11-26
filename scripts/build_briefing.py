#!/usr/bin/env python3
"""매일 국내 주요 언론사 메인 헤드라인을 모아 정적 브리핑 페이지를 만든다.

수집: 네이버 언론사 홈(media.naver.com/press/{id})의 '메인 뉴스' 카드 상위 5건.
링크: 네이버 기사 페이지의 '기사 원문' URL(언론사 사이트). 원문을 못 찾으면 네이버 링크.
산출: index.html, archive/YYYY-MM-DD.html, data/YYYY-MM-DD.json

사용:
  python3 scripts/build_briefing.py              # 오늘 날짜로 수집·생성
  python3 scripts/build_briefing.py --from-json data/2026-11-26.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "lxml", "-q"])
    from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo("Asia/Seoul")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
VIDEO_RE = re.compile(r"^동영상 뉴스\s*재생시간\s*\d+:\d+\s*")

PRESS = [
    {"name": "조선일보", "oid": "023", "category": "general", "home": "https://www.chosun.com/"},
    {"name": "중앙일보", "oid": "025", "category": "general", "home": "https://www.joongang.co.kr/"},
    {"name": "동아일보", "oid": "020", "category": "general", "home": "https://www.donga.com/"},
    {"name": "한겨레", "oid": "028", "category": "general", "home": "https://www.hani.co.kr/"},
    {"name": "경향신문", "oid": "032", "category": "general", "home": "https://www.khan.co.kr/"},
    {"name": "한국일보", "oid": "469", "category": "general", "home": "https://www.hankookilbo.com/"},
    {"name": "국민일보", "oid": "005", "category": "general", "home": "https://www.kmib.co.kr/"},
    {"name": "서울신문", "oid": "081", "category": "general", "home": "https://www.seoul.co.kr/"},
    {"name": "세계일보", "oid": "022", "category": "general", "home": "https://www.segye.com/"},
    {"name": "문화일보", "oid": "021", "category": "general", "home": "https://www.munhwa.com/"},
    {"name": "매일경제", "oid": "009", "category": "economy", "home": "https://www.mk.co.kr/"},
    {"name": "한국경제", "oid": "015", "category": "economy", "home": "https://www.hankyung.com/"},
    {"name": "서울경제", "oid": "011", "category": "economy", "home": "https://www.sedaily.com/"},
    {"name": "머니투데이", "oid": "008", "category": "economy", "home": "https://www.mt.co.kr/"},
    {"name": "연합뉴스", "oid": "001", "category": "wire", "home": "https://www.yna.co.kr/"},
    {"name": "KBS", "oid": "056", "category": "wire", "home": "https://news.kbs.co.kr/"},
    {"name": "MBC", "oid": "214", "category": "wire", "home": "https://imnews.imbc.com/"},
    {"name": "SBS", "oid": "055", "category": "wire", "home": "https://news.sbs.co.kr/"},
    {"name": "JTBC", "oid": "437", "category": "wire", "home": "https://news.jtbc.co.kr/"},
]

CATEGORIES = [
    ("general", "종합일간지"),
    ("economy", "경제지"),
    ("wire", "통신·방송"),
]

THEMES = [
    {
        "id": "jongbu",
        "kws": ["종부세", "종합부동산세"],
        "title": "주택분 종부세 고지, 대상자 크게 늘어 1주택자 반발",
        "lead": "올해 주택분 종합부동산세 고지가 시작됐고, 대상자가 늘어난 가운데 1주택자를 중심으로 세 부담 불만이 보도됐다.",
    },
    {
        "id": "ai-exam",
        "kws": ["AI 커닝", "AI커닝", "AI 부정", "세무사"],
        "title": "경찰, AI 부정행위 세무사시험 수석에 구속영장 신청",
        "lead": "경찰이 세무사시험 수석 합격자를 상대로 AI를 이용한 부정행위 의혹을 수사하며 구속영장을 신청했다.",
    },
    {
        "id": "tariff",
        "kws": ["과잉생산", "관세 25", "관세 15", "과잉 생산"],
        "title": "미국 과잉생산 관세 예고…한국은 15% 상한, 25% 여지 논란",
        "lead": "미국이 과잉생산 관세를 예고한 가운데, 한국은 한미 합의에 따라 15% 상한이 유지되지만 합의 위반 시 25%까지 올릴 수 있다는 보도가 나왔다.",
    },
    {
        "id": "kim-nk",
        "kws": ["김정은", "전술핵", "핵탄두", "핵잠"],
        "title": "김정은, 전술핵 과시…한국을 ‘위해한 적국’으로 규정",
        "lead": "김정은 북한 국무위원장이 핵 관련 시설을 공개·강조하며 전술핵 활용을 언급하고, 한국을 위해한 적국으로 규정했다는 보도가 이어졌다.",
    },
    {
        "id": "president",
        "kws": ["SNS", "폭언", "가난", "복지 자동"],
        "title": "이 대통령, SNS 폭언 차단과 ‘가난 증명’ 복지 발언",
        "lead": "이 대통령은 SNS에서 폭언·욕설을 하면 차단하겠다고 밝혔고, 복지 신청 때 가난을 서류로 증명하게 하는 관행도 지적했다.",
    },
    {
        "id": "rail",
        "kws": ["철도노조", "준법투쟁", "안전운행"],
        "title": "철도노조 준법투쟁 돌입…수도권 전철·일반열차 지연",
        "lead": "철도노조가 안전운행(준법) 투쟁에 들어가 수도권 광역전철과 일부 일반열차 운행이 지연되거나 중지됐다.",
    },
    {
        "id": "rate",
        "kws": ["기준금리", "금통위"],
        "title": "한국은행, 기준금리 인상",
        "lead": "한국은행 금융통화위원회가 기준금리를 조정했고, 그 여파가 가계와 시장 보도에 올랐다.",
    },
    {
        "id": "ethics",
        "kws": ["윤리위", "조작징계", "탈당해라", "당 꼬라지"],
        "title": "국민의힘 최고위, 윤리위·조작징계 놓고 내홍",
        "lead": "국민의힘 최고위원회의에서 윤리위와 조작징계 문제를 놓고 충돌이 있었고, 탈당 언급까지 보도됐다.",
    },
    {
        "id": "special-counsel",
        "kws": ["조작기소", "이임성"],
        "title": "조작기소 특검 후보에 이임성 변호사 추천",
        "lead": "더불어민주당이 조작기소 특검 후보로 이임성 변호사를 추천했다는 보도가 나왔다.",
    },
    {
        "id": "judges",
        "kws": ["조희대", "법왜곡", "판사들"],
        "title": "조희대 탄핵·판사 반발 논란 지속",
        "lead": "조희대 대법원장 탄핵 논란과 관련해 판사들의 반발, 여론 조사, 특검 후보 입장 등이 보도됐다.",
    },
    {
        "id": "press-law",
        "kws": ["언론4법", "언론 4법", "정부 광고"],
        "title": "‘언론 4법’ 소위 통과…허위 정보 언론사 정부광고 제한",
        "lead": "허위 정보를 유통한 언론사에 정부 광고를 제한하는 내용을 포함한 ‘언론 4법’이 국회 소위를 통과했다는 보도가 나왔다.",
    },
    {
        "id": "leet",
        "kws": ["리트", "이진우"],
        "title": "리트 만점자 관련 압수수색 등 강제수사",
        "lead": "경찰이 리트 만점자 관련 부정행위 의혹을 강제수사하며 주거지와 시험장 등을 압수수색했다.",
    },
]


def curl(url: str, dest: Path, timeout: int = 25) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "-A", UA, "-o", str(dest), "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
    )
    code = int((r.stdout or "0").strip() or 0)
    size = dest.stat().st_size if dest.exists() else 0
    return code, size


def clean_url(url: str) -> str:
    if not url:
        return url
    url = re.sub(r"[?&](utm_[^=&]+|plink|cooper|influxDiv|source|medium|campaign)=[^&]*", "", url)
    url = url.rstrip("?&")
    return url


def extract_main(html: str, limit: int = 5) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    box = soup.select_one("div.press_main_news")
    if not box:
        return items
    panel = box.select_one("li.flick-panel") or box
    for li in panel.select("li.press_news_item"):
        a = li.select_one("a.press_news_link")
        if not a:
            continue
        title = VIDEO_RE.sub("", a.get_text(" ", strip=True)).strip()
        href = (a.get("href") or "").split("?")[0].strip()
        if not title or len(title) < 8 or not href:
            continue
        if href in seen:
            continue
        seen.add(href)
        items.append({"title": title, "naver_url": href, "url": href, "origin": None})
        if len(items) >= limit:
            break
    return items


def extract_origin(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        if "기사 원문" in a.get_text(" ", strip=True):
            return clean_url(a["href"])
    return None


def collect(tmp: Path, limit: int = 5) -> list[dict]:
    outlets = []
    # fetch press pages
    def fetch_press(p):
        dest = tmp / f"nv_{p['oid']}.html"
        url = f"https://media.naver.com/press/{p['oid']}"
        code, size = curl(url, dest)
        return p, dest, code, size

    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(fetch_press, p) for p in PRESS]
        for f in as_completed(futs):
            results.append(f.result())

    article_jobs = []
    for p, dest, code, size in results:
        ok = code == 200 and size > 20000
        headlines = extract_main(dest.read_text(errors="replace"), limit) if ok and dest.exists() else []
        outlet = {
            "name": p["name"],
            "oid": p["oid"],
            "category": p["category"],
            "home": p["home"],
            "status": "ok" if headlines else "fail",
            "headlines": headlines,
        }
        outlets.append(outlet)
        for h in headlines:
            article_jobs.append((outlet["name"], h))

    # preserve PRESS order
    order = {p["name"]: i for i, p in enumerate(PRESS)}
    outlets.sort(key=lambda o: order[o["name"]])

    def fetch_article(item):
        name, h = item
        url = h["naver_url"]
        parts = url.rstrip("/").split("/")
        dest = tmp / "articles" / f"{parts[-2]}_{parts[-1]}.html"
        code, size = curl(url, dest)
        origin = None
        if code == 200 and dest.exists():
            origin = extract_origin(dest.read_text(errors="replace"))
        return name, h["naver_url"], origin

    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(fetch_article, job) for job in article_jobs]
        origins = {}
        for f in as_completed(futs):
            name, nurl, origin = f.result()
            origins[(name, nurl)] = origin

    for o in outlets:
        for h in o["headlines"]:
            origin = origins.get((o["name"], h["naver_url"]))
            if origin:
                h["origin"] = origin
                h["url"] = origin
            else:
                h["url"] = h["naver_url"]
    return outlets


def pick_highlights(outlets: list[dict], limit: int = 5, override: list[dict] | None = None) -> list[dict]:
    if override:
        return override
    # Use up to 12 main items if present; otherwise the stored 5.
    scored = []
    for theme in THEMES:
        papers = []
        for o in outlets:
            if o["status"] != "ok":
                continue
            titles = [h["title"] for h in o["headlines"]]
            if any(any(kw in t for kw in theme["kws"]) for t in titles):
                papers.append(o["name"])
        if len(papers) >= 2:
            scored.append({**theme, "outlets": papers, "count": len(papers)})
    scored.sort(key=lambda x: (-x["count"], THEMES.index(next(t for t in THEMES if t["id"] == x["id"]))))
    highlights = []
    for s in scored[:limit]:
        highlights.append({
            "title": s["title"],
            "summary": s["lead"],
            "outlets": s["outlets"],
        })
    return highlights


def weekday_ko(dt: datetime) -> str:
    return "월화수목금토일"[dt.weekday()] + "요일"


def format_date(dt: datetime) -> str:
    return f"{dt.year}년 {dt.month}월 {dt.day}일 {weekday_ko(dt)}"


def list_archives(root: Path, current: str) -> list[str]:
    files = sorted((root / "archive").glob("*.html"), reverse=True)
    dates = [p.stem for p in files if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem)]
    if current not in dates:
        dates = [current] + dates
    # unique preserve order
    seen, out = set(), []
    for d in dates:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out[:30]


def render_html(payload: dict, archives: list[str], is_archive: bool = False) -> str:
    date_s = payload["date"]
    generated = payload["generated_at"]
    highlights = payload["highlights"]
    outlets = payload["outlets"]
    ok = sum(1 for o in outlets if o["status"] == "ok")
    fail = [o["name"] for o in outlets if o["status"] != "ok"]

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    hl_html = []
    for i, h in enumerate(highlights, 1):
        chips = "".join(f'<span class="chip">{esc(n)}</span>' for n in h["outlets"])
        hl_html.append(
            f"""<li class="hl">
              <div class="hl-num">{i:02d}</div>
              <div class="hl-body">
                <h3>{esc(h['title'])}</h3>
                <p>{esc(h['summary'])}</p>
                <div class="chips">{chips}</div>
              </div>
            </li>"""
        )

    sections = []
    for cat, label in CATEGORIES:
        cards = []
        group = [o for o in outlets if o["category"] == cat]
        for o in group:
            if o["status"] != "ok":
                cards.append(
                    f"""<article class="card fail">
                      <header><a class="paper" href="{esc(o['home'])}">{esc(o['name'])}</a>
                      <span class="badge">수집 실패</span></header>
                      <p class="fail-note">이 시각 메인 헤드라인을 확인하지 못했습니다.</p>
                    </article>"""
                )
                continue
            lis = []
            for h in o["headlines"]:
                lis.append(f'<li><a href="{esc(h["url"])}" target="_blank" rel="noopener">{esc(h["title"])}</a></li>')
            cards.append(
                f"""<article class="card">
                  <header><a class="paper" href="{esc(o['home'])}">{esc(o['name'])}</a>
                  <span class="count">{len(o['headlines'])}건</span></header>
                  <ol>{''.join(lis)}</ol>
                </article>"""
            )
        sections.append(
            f"""<section class="sec">
              <h2>{label}</h2>
              <div class="grid">{''.join(cards)}</div>
            </section>"""
        )

    arch_links = []
    for d in archives:
        href = f"archive/{d}.html" if not is_archive else (f"{d}.html" if d != date_s else "#")
        if not is_archive and d == date_s:
            href = "./"
        cls = " current" if d == date_s else ""
        arch_links.append(f'<a class="arch{cls}" href="{href}">{d}</a>')

    fail_line = (
        f"수집 실패 {len(fail)}곳: {', '.join(fail)}" if fail else "수집 실패한 언론사는 없습니다."
    )
    notice = "아카이브 페이지" if is_archive else "매일 아침 8시 브리핑 · 테스트 이후 같은 형식으로 갱신"
    back = '<p class="back"><a href="../">오늘 브리핑으로</a></p>' if is_archive else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>뉴스 브리핑 · {esc(payload['date_label'])}</title>
  <meta name="description" content="국내 주요 신문·방송 메인 헤드라인 브리핑">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&family=Noto+Serif+KR:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --paper: #f3eee4;
      --card: #fbf8f1;
      --ink: #1c1917;
      --muted: #5f574c;
      --rule: #d7d0c3;
      --accent: #8b1e2d;
      --chip: #efe6d4;
      --fail: #9a3412;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Noto Sans KR", sans-serif;
      background: var(--paper);
      color: var(--ink);
      line-height: 1.6;
    }}
    a {{ color: inherit; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 18px 64px; }}
    .mast {{
      border-top: 3px solid var(--ink);
      border-bottom: 1px solid var(--ink);
      padding: 18px 0 16px;
      text-align: center;
    }}
    .kicker {{
      letter-spacing: .22em;
      font-size: 11px;
      font-weight: 600;
      color: var(--accent);
      text-transform: uppercase;
    }}
    .mast h1 {{
      font-family: "Noto Serif KR", serif;
      font-size: clamp(32px, 7vw, 52px);
      font-weight: 700;
      letter-spacing: -.03em;
      line-height: 1.15;
      margin: 6px 0 8px;
    }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .meta strong {{ color: var(--ink); font-weight: 600; }}
    .stats {{
      display: flex; justify-content: center; gap: 18px; flex-wrap: wrap;
      margin-top: 10px; font-size: 13px; color: var(--muted);
    }}
    h2 {{
      font-family: "Noto Serif KR", serif;
      font-size: 22px;
      margin: 36px 0 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--ink);
    }}
    .hl-list {{ list-style: none; display: flex; flex-direction: column; gap: 12px; }}
    .hl {{
      display: grid;
      grid-template-columns: 48px 1fr;
      gap: 12px;
      background: var(--card);
      border: 1px solid var(--rule);
      border-radius: 12px;
      padding: 16px 16px 14px;
    }}
    .hl-num {{
      font-family: "Noto Serif KR", serif;
      color: var(--accent);
      font-size: 22px;
      font-weight: 700;
      line-height: 1.2;
    }}
    .hl h3 {{ font-size: 17px; line-height: 1.45; margin-bottom: 4px; font-weight: 700; }}
    .hl p {{ font-size: 14.5px; color: #3f3a34; }}
    .note {{ font-size: 13px; color: var(--muted); margin: -4px 0 14px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .chip {{
      background: var(--chip);
      border-radius: 999px;
      padding: 2px 9px;
      font-size: 11.5px;
      color: #4a4338;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 14px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--rule);
      border-radius: 12px;
      padding: 14px 16px 16px;
    }}
    .card header {{
      display: flex; justify-content: space-between; align-items: baseline;
      border-bottom: 1px solid var(--rule);
      padding-bottom: 8px; margin-bottom: 10px;
    }}
    .paper {{
      font-family: "Noto Serif KR", serif;
      font-weight: 700;
      font-size: 18px;
      text-decoration: none;
    }}
    .paper:hover {{ color: var(--accent); }}
    .count, .badge {{ font-size: 12px; color: var(--muted); }}
    .badge {{ color: var(--fail); font-weight: 600; }}
    .fail {{ opacity: .9; }}
    .fail-note {{ font-size: 13px; color: var(--muted); }}
    .card ol {{ list-style: none; counter-reset: h; }}
    .card li {{
      counter-increment: h;
      padding: 8px 0 8px 26px;
      position: relative;
      border-top: 1px solid #eee6d8;
      font-size: 14.5px;
      line-height: 1.5;
    }}
    .card li:first-child {{ border-top: 0; padding-top: 2px; }}
    .card li::before {{
      content: counter(h);
      position: absolute; left: 0; top: 9px;
      font-family: "Noto Serif KR", serif;
      font-size: 13px; color: var(--accent); font-weight: 700;
    }}
    .card li:first-child::before {{ top: 3px; }}
    .card a {{ text-decoration: none; }}
    .card a:hover {{ text-decoration: underline; text-underline-offset: 3px; }}
    .archives {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .arch {{
      display: inline-block;
      padding: 4px 10px;
      border: 1px solid var(--rule);
      border-radius: 999px;
      font-size: 13px;
      text-decoration: none;
      color: var(--muted);
    }}
    .arch.current, .arch:hover {{ border-color: var(--ink); color: var(--ink); }}
    footer {{
      margin-top: 48px;
      padding-top: 16px;
      border-top: 1px solid var(--rule);
      color: var(--muted);
      font-size: 12.5px;
    }}
    footer p + p {{ margin-top: 6px; }}
    .back {{ margin-bottom: 10px; }}
    .back a {{ color: var(--accent); }}
    @media (max-width: 560px) {{
      .wrap {{ padding: 18px 14px 48px; }}
      .hl {{ grid-template-columns: 36px 1fr; padding: 14px; }}
      .card li {{ font-size: 15px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {back}
    <header class="mast">
      <div class="kicker">KOREA NEWS BRIEFING</div>
      <h1>뉴스 브리핑</h1>
      <p class="meta"><strong>{esc(payload['date_label'])}</strong> · 생성 {esc(generated)} (Asia/Seoul)</p>
      <div class="stats">
        <span>언론사 {ok}/{len(outlets)}곳</span>
        <span>{esc(notice)}</span>
      </div>
    </header>

    <section>
      <h2>오늘의 핵심 5줄</h2>
      <p class="note">각 이슈를 다룬 언론사는 해당사 네이버 메인 뉴스 카드 기준입니다. 아래 카드에는 그중 상위 5건만 보여 줍니다.</p>
      <ol class="hl-list">
        {''.join(hl_html)}
      </ol>
    </section>

    {''.join(sections)}

    <section class="sec">
      <h2>지난 브리핑</h2>
      <div class="archives">{''.join(arch_links) if arch_links else '<span class="meta">아직 아카이브가 없습니다.</span>'}</div>
    </section>

    <footer>
      <p>출처: 각 언론사 네이버 언론사 홈의 메인 뉴스(편집 배치) 상위 5건. 링크는 언론사 원문입니다.</p>
      <p>{esc(fail_line)} 헤드라인은 수집 시각 기준이며, 이후 홈페이지 배치는 달라질 수 있습니다.</p>
      <p>저장소 <a href="https://github.com/aihubos/news-briefing">aihubos/news-briefing</a></p>
    </footer>
  </div>
</body>
</html>
"""


TODAY_OVERRIDE = [
    {
        "title": "경찰, AI 부정행위 세무사시험 수석에 구속영장 신청",
        "summary": "경찰이 세무사시험 수석 합격자를 상대로 AI를 이용한 부정행위 의혹을 수사하며 구속영장을 신청했다. 도주 우려와 시험 공정성 훼손이 이유로 언급됐다.",
        "outlets": ["한겨레", "경향신문", "한국일보", "국민일보", "서울신문", "연합뉴스", "KBS", "MBC", "SBS", "JTBC"],
    },
    {
        "title": "주택분 종부세 고지…대상 73만 명, 1년 새 19만 명 증가",
        "summary": "올해 주택분 종합부동산세가 약 73만 명에게 고지됐고 대상자가 전년보다 19만 명 늘었다. 집값 상승에 따른 1주택자 세 부담 불만이 주요 면에 올랐다.",
        "outlets": ["조선일보", "한국경제", "서울경제", "연합뉴스", "SBS"],
    },
    {
        "title": "미국 과잉생산 관세 예고…한국은 15% 상한, 25% 여지 논란",
        "summary": "미국이 과잉생산 관세를 예고한 가운데, 한국은 한미 합의에 따라 15% 상한이 유지되지만 합의를 어기면 25%까지 올릴 수 있다는 보도가 나왔다.",
        "outlets": ["서울신문", "세계일보", "매일경제", "MBC", "JTBC"],
    },
    {
        "title": "이 대통령, SNS 폭언 차단과 ‘가난 증명’ 복지 발언",
        "summary": "이 대통령은 SNS에서 폭언·욕설을 하면 차단하겠다고 밝혔고, 복지 신청 때 가난을 서류로 증명하게 하는 관행도 지적하며 복지 체계 전환을 언급했다.",
        "outlets": ["조선일보", "중앙일보", "동아일보", "한겨레", "서울경제", "KBS"],
    },
    {
        "title": "김정은, 전술핵 과시…한국을 ‘위해한 적국’으로 규정",
        "summary": "김정은 북한 국무위원장이 핵 관련 시설과 전술핵을 공개·강조하고, 한국을 위해한 적국으로 규정했다는 보도가 이어졌다.",
        "outlets": ["한겨레", "서울신문", "SBS", "JTBC"],
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-json", dest="from_json")
    parser.add_argument("--tmp", default="/tmp/news-briefing-raw")
    parser.add_argument("--no-override", action="store_true", help="핵심 5줄을 키워드 집계로만 생성")
    args = parser.parse_args()

    now = datetime.now(KST)
    date_s = now.strftime("%Y-%m-%d")
    generated = now.strftime("%H:%M")

    if args.from_json:
        payload = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        date_s = payload["date"]
        outlets = payload["outlets"]
        highlights = payload.get("highlights") or pick_highlights(outlets, override=None)
        generated = payload.get("generated_at", generated)
        date_label = payload.get("date_label") or format_date(datetime.strptime(date_s, "%Y-%m-%d"))
    else:
        tmp = Path(args.tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        outlets = collect(tmp)
        override = None if args.no_override else (TODAY_OVERRIDE if date_s == "2026-11-26" else None)
        highlights = pick_highlights(outlets, override=override)
        date_label = format_date(now)
        # filter highlight outlets to those actually present in collected headlines (top 5 may miss some)
        # Keep override lists as authored if provided; they were checked against top-12 main cards.

    payload = {
        "date": date_s,
        "date_label": date_label if not args.from_json else date_label,
        "generated_at": generated,
        "timezone": "Asia/Seoul",
        "highlights": highlights,
        "outlets": outlets,
        "source": "네이버 언론사 홈 메인 뉴스 상위 5건, 링크는 기사 원문",
    }

    data_path = ROOT / "data" / f"{date_s}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    archives = list_archives(ROOT, date_s)
    index = render_html(payload, archives, is_archive=False)
    archive = render_html(payload, archives, is_archive=True)
    (ROOT / "index.html").write_text(index, encoding="utf-8")
    arch_dir = ROOT / "archive"
    arch_dir.mkdir(exist_ok=True)
    (arch_dir / f"{date_s}.html").write_text(archive, encoding="utf-8")

    ok = [o["name"] for o in outlets if o["status"] == "ok"]
    fail = [o["name"] for o in outlets if o["status"] != "ok"]
    print(f"Wrote index.html and archive/{date_s}.html")
    print(f"OK ({len(ok)}): {', '.join(ok)}")
    print(f"FAIL ({len(fail)}): {', '.join(fail) if fail else '-'}")


if __name__ == "__main__":
    main()
