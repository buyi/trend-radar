#!/usr/bin/env python3
"""Fetch Google Trends RSS. Python 3.9+, standard library only."""
import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

NS = {'ht': 'https://trends.google.com/trending/rss'}


def parse_feed(data, geo):
    root = ET.fromstring(data)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('响应不是有效的 RSS feed')
    items = []
    for node in root.findall('./channel/item'):
        title = node.findtext('title', '').strip()
        published = node.findtext('pubDate', '').strip()
        if not title or not published:
            raise ValueError('RSS 条目缺少标题或发布时间')
        key = hashlib.sha256(f'{geo}\n{title}\n{published}'.encode()).hexdigest()
        items.append({
            'id': key, 'geo': geo, 'title': title, 'published': published,
            'approx_traffic': node.findtext('ht:approx_traffic', '', NS),
            'explore_url': 'https://trends.google.com/trends/explore?' +
                urllib.parse.urlencode({'geo': geo, 'q': title}),
            'news': [{
                'title': n.findtext('ht:news_item_title', '', NS),
                'url': n.findtext('ht:news_item_url', '', NS),
                'source': n.findtext('ht:news_item_source', '', NS),
            } for n in node.findall('ht:news_item', NS)],
        })
    return items


def fetch(geo):
    url = 'https://trends.google.com/trending/rss?' + urllib.parse.urlencode({'geo': geo})
    request = urllib.request.Request(url, headers={'User-Agent': 'TrendsRSSCollector/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def traffic_value(item):
    value = item['approx_traffic'].replace(',', '').replace('+', '').strip().upper()
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*([KMB]?)', value)
    return float(match[1]) * {'': 1, 'K': 1000, 'M': 1000000, 'B': 1000000000}[match[2]] if match else -1


def collect(geo, output, limit=20):
    data = fetch(geo)
    items = parse_feed(data, geo)
    top = sorted(items, key=traffic_value, reverse=True)[:limit]
    now = datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output / 'history.sqlite3', timeout=30) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS trends (
            id TEXT PRIMARY KEY, geo TEXT, first_seen TEXT, last_seen TEXT, payload TEXT)''')
        fresh = []
        for item in items:
            old = db.execute('SELECT 1 FROM trends WHERE id=?', (item['id'],)).fetchone()
            if old is None:
                fresh.append(item)
            db.execute('''INSERT INTO trends VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, payload=excluded.payload''',
                (item['id'], geo, now, now, json.dumps(item, ensure_ascii=False)))
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        report = {'fetched_at': now, 'geo': geo, 'total': len(items),
                  'new_count': len(fresh), 'items': items, 'new_items': fresh,
                  'top_items': top, 'requested_top': limit}
        # Write reports before committing: a failed write leaves items eligible next run.
        json_path = output / f'{geo}-{stamp}.json'
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = [f'# Google Trends · {geo}', '', f'抓取时间（UTC）：{now}',
                 f'本次 {len(items)} 条，新增 {len(fresh)} 条。', '',
                 '说明：新增指本地首次见到的标题与发布时间组合；首次运行全部计为新增。',
                 '热度为 RSS 原始近似值，不代表精确月搜索量。', '',
                 f'## 当前热点 Top {len(top)}（RSS 内按近似热度降序）', '',
                 f'目标取前 {limit} 条；RSS 本次提供 {len(items)} 条，不足时按实际数量展示。', '']
        for rank, item in enumerate(top, 1):
            lines.extend([f"### {rank}. {item['title']}", '',
                          f"热度：{item['approx_traffic']}；发布时间：{item['published']}",
                          f"[查看趋势]({item['explore_url']})", ''])
            for news in item['news']:
                lines.append(f"- {news['source']}：[{news['title']}]({news['url']})")
            lines.append('')
        lines.extend(['## 本次新增', ''])
        lines.extend([f"- {item['title']}" for item in fresh] or ['本次没有新增热点。'])
        md_path = output / f'{geo}-{stamp}.md'
        md_path.write_text('\n'.join(lines), encoding='utf-8')
        (output / f'{geo}-{stamp}.xml').write_bytes(data)
    print(f'{geo}: 共 {len(items)} 条，新增 {len(fresh)} 条；报告：{md_path}')


def main():
    parser = argparse.ArgumentParser(description='拉取 Google Trends RSS，去重并生成报告')
    parser.add_argument('--geo', nargs='+', default=['US'], help='地区代码，例如 US GB CA AU JP')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'data')
    parser.add_argument('--top', type=int, default=20, help='按 RSS 近似热度取前 N 条，默认 20')
    args = parser.parse_args()
    if args.top < 1:
        parser.error('--top 必须为正整数')
    geos = list(dict.fromkeys(g.upper() for g in args.geo))
    if any(not re.fullmatch('[A-Z]{2}', g) for g in geos):
        parser.error('地区代码必须为两个英文字母，例如 US')
    failed = False
    for geo in geos:
        try:
            collect(geo, args.output, args.top)
        except (OSError, ValueError, ET.ParseError, sqlite3.Error) as exc:
            print(f'{geo} 抓取失败：{exc}', file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
