"""Public RSS titles only. Never turn a headline into a verified fact or analysis."""
import concurrent.futures
import html
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from common import KST, ROOT, read, report_status, slot_context, write

FEEDS = {
    'stocks': '한국 증시 코스피 코스닥 when:1d',
    'economy': '한국 경제 금리 물가 환율 when:1d',
    'politics': '한국 정치 외교 안보 when:1d',
    'global': '국제 경제 정치 when:1d',
}
LABELS = {'stocks': '증시', 'economy': '경제·민생', 'politics': '정치·안보', 'global': '국제'}


def parse_feed(body, category, now):
    result = []
    for item in ET.fromstring(body).findall('./channel/item'):
        title = html.unescape(re.sub('<[^>]+>', '', item.findtext('title') or '')).strip()
        url = (item.findtext('link') or '').strip()
        try:
            date = parsedate_to_datetime(item.findtext('pubDate')).astimezone(KST)
        except (TypeError, ValueError, AttributeError):
            continue
        if not title or urllib.parse.urlparse(url).scheme != 'https':
            continue
        if date < now - timedelta(hours=36) or date > now + timedelta(minutes=5):
            continue
        result.append({'title': title, 'url': url, 'category': LABELS[category],
                       'category_id': category, 'source': item.findtext('source') or 'Google News RSS',
                       'published_at': date.isoformat(), 'verification': 'headline_only'})
    return result


def fetch_feed(category, query, now):
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
        {'q': query, 'hl': 'ko', 'gl': 'KR', 'ceid': 'KR:ko'})
    request = urllib.request.Request(url, headers={'User-Agent': 'SIGNAL-dashboard/1.0 public-RSS'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return parse_feed(response.read(2_000_000), category, now)


def main():
    ctx = slot_context()
    now = datetime.now(KST)
    file = f"data/headline-archive/{ctx['date']}/{ctx['slot']}.json"
    if (ROOT / file).exists():
        # An already successful slot is immutable; retry must not erase it.
        saved = read(ROOT / file)
        report_status('collection', 'collected', '기존 회차 보존 · 중복 수집 생략',
                      count=len(saved['articles']), file=file, scheduled_at=ctx['scheduled_at'])
        return
    gathered, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_feed, k, q, now): k for k, q in FEEDS.items()}
        for job in concurrent.futures.as_completed(jobs):
            category = jobs[job]
            try:
                gathered[category] = job.result()
                if not gathered[category]:
                    errors[category] = 'No recent valid items'
            except Exception as error:
                errors[category] = type(error).__name__
    if errors:
        report_status('collection', 'failed', '일부 분야 수집 실패 · 마지막 정상 기록 유지', errors=errors)
        return 1
    articles, seen = [], set()
    for category in FEEDS:
        count = 0
        for item in gathered[category]:
            signature = re.sub(r'\s+', '', item['title']).lower()
            if item['url'] in seen or signature in seen:
                continue
            seen.update([item['url'], signature])
            articles.append(item)
            count += 1
            if count == 12:
                break
        if not count:
            report_status('collection', 'failed', '분야별 중복 제거 후 기사 부족 · 기존 기록 유지')
            return 1
    doc = {'version': 1, **ctx, 'verification': 'headline_only', 'articles': articles}
    write(ROOT / file, doc)
    write(ROOT / 'data/live-headlines.json', doc)
    index = read(ROOT / 'data/headline-index.json', {'version': 1, 'snapshots': []})
    index['snapshots'].append({**ctx, 'file': file, 'count': len(articles)})
    index['snapshots'].sort(key=lambda x: x['scheduled_at'], reverse=True)
    write(ROOT / 'data/headline-index.json', index)
    report_status('collection', 'collected', '공개 RSS 제목·링크 수집 성공 · 심층 분석과 별도',
                  count=len(articles), file=file, scheduled_at=ctx['scheduled_at'])
    print(f"Collected {len(articles)} RSS headlines across four categories; {file}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
