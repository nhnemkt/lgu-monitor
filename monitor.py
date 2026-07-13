#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions용 LGU+ 네이버 순위 모니터링
- 노트북 없이 GitHub 서버에서 자동 실행
- rankings.json + index.html 업데이트
"""
import requests
from bs4 import BeautifulSoup
import json, time, os, re, random, urllib.parse
from datetime import datetime, timezone, timedelta

KST      = timezone(timedelta(hours=9))
now      = datetime.now(KST)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 설정 로드 ──────────────────────────────────
with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)

SETTINGS        = CONFIG["settings"]
PC_KEYWORDS     = CONFIG.get("pc_keywords", CONFIG["keywords"])
MOBILE_KEYWORDS = CONFIG.get("mobile_keywords", PC_KEYWORDS)
BRAND_DOMAINS   = SETTINGS["brand_identifiers"]["domains"]
BRAND_TITLES    = SETTINGS["brand_identifiers"]["title_keywords"]
AD_TYPE_HOME    = SETTINGS["ad_type_classification"]["홈"]
AD_TYPE_MOBILE  = SETTINGS["ad_type_classification"]["모바일"]
DELAY           = SETTINGS.get("delay_between_requests", 2.5)

JSON_FILE = os.path.join(BASE_DIR, "data", "rankings.json")
HTML_FILE = os.path.join(BASE_DIR, "index.html")

# ── HTTP 헤더 ──────────────────────────────────
PC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.naver.com/",
}
MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.naver.com/",
}


# ── 분류 ──────────────────────────────────────
def classify_ad(title, url):
    t = (title or "").lower()
    u = (url   or "").lower()
    is_lgu = any(d in u for d in BRAND_DOMAINS) or \
             any(kw.lower() in t for kw in BRAND_TITLES)
    if not is_lgu:
        return None
    for kw in AD_TYPE_HOME:
        if kw.lower() in t: return "홈"
    for kw in AD_TYPE_MOBILE:
        if kw.lower() in t: return "모바일"
    return "일반"

def format_rank(n, ad_type):
    if ad_type == "홈":     return f"(홈){n}위"
    if ad_type == "모바일": return f"(모바일){n}위"
    return f"{n}위"


# ── 파싱 ──────────────────────────────────────
def parse_rank(html):
    if not html:
        return "X"
    soup = BeautifulSoup(html, "html.parser")

    # 파워링크 섹션 → ul.lst_type → 직계 li
    ad_section = soup.find("div", class_=re.compile(r"\bad_section\b"))
    if not ad_section:
        ad_section = soup.find("div", class_=re.compile(r"pcPowerLink"))
    if not ad_section:
        return "X"

    lst_type = ad_section.find("ul", class_="lst_type")
    if not lst_type:
        return "X"

    items = lst_type.find_all("li", recursive=False) or lst_type.find_all("li")
    for rank, item in enumerate(items, 1):
        full_text = item.get_text(separator=" ", strip=True)
        lnk_a     = item.find("a", class_="lnk_head")
        url       = lnk_a.get("href", "") if lnk_a else ""
        ad_type   = classify_ad(full_text, url)
        if ad_type is not None:
            return format_rank(rank, ad_type)
    return "X"


# ── 요청 ──────────────────────────────────────
def fetch(url, headers, session):
    for _ in range(3):
        try:
            r = session.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  요청 실패: {e}")
            time.sleep(3)
    return None


# ── 메인 ──────────────────────────────────────
def run():
    session = requests.Session()
    results = {}

    print(f"[{now.strftime('%Y-%m-%d %H:%M KST')}] 모니터링 시작")
    print(f"  PC {len(PC_KEYWORDS)}개 / 모바일 {len(MOBILE_KEYWORDS)}개")

    # PC
    for i, kw in enumerate(PC_KEYWORDS, 1):
        print(f"  [PC {i}/{len(PC_KEYWORDS)}] {kw}", end=" → ")
        encoded = urllib.parse.quote(kw)
        html    = fetch(f"https://search.naver.com/search.naver?query={encoded}", PC_HEADERS, session)
        time.sleep(DELAY + random.uniform(0, 1))
        rank    = parse_rank(html)
        results.setdefault(kw, {})["PC"] = rank
        print(rank)

    # 모바일
    for i, kw in enumerate(MOBILE_KEYWORDS, 1):
        print(f"  [MOB {i}/{len(MOBILE_KEYWORDS)}] {kw}", end=" → ")
        encoded = urllib.parse.quote(kw)
        html    = fetch(f"https://search.naver.com/search.naver?query={encoded}", MOBILE_HEADERS, session)
        time.sleep(DELAY + random.uniform(0, 1))
        rank    = parse_rank(html)
        results.setdefault(kw, {})["모바일"] = rank
        print(rank)

    # rankings.json 업데이트
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    date_key = now.strftime("%Y-%m-%d")
    hour_key = str(now.hour)

    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"pc_keywords": PC_KEYWORDS, "mobile_keywords": MOBILE_KEYWORDS,
              "keywords": PC_KEYWORDS, "data": {}}

    db["last_updated"]    = now.strftime("%Y-%m-%d %H:%M")
    db["pc_keywords"]     = PC_KEYWORDS
    db["mobile_keywords"] = MOBILE_KEYWORDS
    db["keywords"]        = PC_KEYWORDS
    db["data"].setdefault(date_key, {})
    db["data"][date_key].setdefault(hour_key, {})
    for kw, ranks in results.items():
        db["data"][date_key][hour_key][kw] = ranks

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"  rankings.json 저장 완료")

    # index.html DB 데이터 업데이트
    if os.path.exists(HTML_FILE):
        with open(HTML_FILE, encoding="utf-8") as f:
            html_src = f.read()

        db_json = json.dumps(db, ensure_ascii=False)
        marker  = "const DB = "
        start   = html_src.find(marker)
        if start >= 0:
            pos   = start + len(marker)
            depth = 0
            end   = pos
            for i, c in enumerate(html_src[pos:]):
                if c == '{':   depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = pos + i + 1
                        break
            if html_src[end:end+1] == ';':
                end += 1
            html_new = html_src[:start] + f"const DB = {db_json};" + html_src[end:]
            with open(HTML_FILE, "w", encoding="utf-8") as f:
                f.write(html_new)
            print(f"  index.html 업데이트 완료")

    print("완료!")


if __name__ == "__main__":
    run()
