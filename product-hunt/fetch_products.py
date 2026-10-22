#!/usr/bin/env python3
"""Product Hunt API example. Python 3.9+, standard library only."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENDPOINT = 'https://api.producthunt.com/v2/api/graphql'
QUERY = '''query RecentProducts($first: Int!, $after: DateTime!, $before: DateTime!) {
  posts(first: $first, order: VOTES, postedAfter: $after, postedBefore: $before) {
    edges { node {
      id name tagline description url website votesCount commentsCount createdAt
    } }
    pageInfo { hasNextPage endCursor }
  }
}'''


def request_products(payload, token):
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), headers={
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'User-Agent': 'ProductHuntDailyCollector/1.0',
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
            quota = {name: response.headers.get('X-Rate-Limit-' + name)
                     for name in ('Limit', 'Remaining', 'Reset')}
    except urllib.error.HTTPError as exc:
        hints = {401: 'Token 无效或已撤销', 403: '没有访问权限',
                 429: '请求额度耗尽，请稍后再试'}
        reset = exc.headers.get('X-Rate-Limit-Reset', '未知')
        # Do not dump response bodies or headers that could contain credentials.
        raise ValueError(f'HTTP {exc.code}: {hints.get(exc.code, "API 请求失败")}；重置秒数：{reset}') from None
    if result.get('errors'):
        messages = '; '.join(str(e.get('message', '未知错误')) for e in result['errors'])
        raise ValueError('GraphQL 错误：' + messages.replace(token, '[REDACTED]'))
    connection = (result.get('data') or {}).get('posts')
    if not isinstance(connection, dict) or not isinstance(connection.get('edges'), list):
        raise ValueError('API 响应缺少 posts.edges')
    return connection, quota


def main():
    parser = argparse.ArgumentParser(description='最近 N 小时发布的产品，按当前累计票数取前 N 个')
    parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--hours', type=int, default=24)
    parser.add_argument('--dry-run', action='store_true', help='只显示查询，不联网、不需要 Token')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'data')
    args = parser.parse_args()
    if not 1 <= args.top <= 20 or args.hours < 1:
        parser.error('--top 范围为 1–20，--hours 必须为正整数')
    now = datetime.now(timezone.utc)
    variables = {'first': args.top, 'after': (now - timedelta(hours=args.hours)).isoformat(),
                 'before': now.isoformat()}
    payload = {'query': QUERY, 'variables': variables}
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    token = os.environ.get('PRODUCT_HUNT_TOKEN', '').strip()
    if not token:
        print('缺少 PRODUCT_HUNT_TOKEN 环境变量。请在本机配置；不要把 Token 发到聊天中。', file=sys.stderr)
        return 2
    try:
        connection, quota = request_products(payload, token)
        products = [edge['node'] for edge in connection['edges']]
        report = {'fetched_at': now.isoformat(), 'window': variables,
                  'rate_limit': quota, 'products': products, 'pageInfo': connection.get('pageInfo')}
        args.output.mkdir(parents=True, exist_ok=True)
        prefix = args.output / now.strftime('products-%Y%m%dT%H%M%S%fZ')
        prefix.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# Product Hunt 新产品', '', f'抓取时间（UTC）：{now.isoformat()}',
                 f'发布窗口：{variables["after"]} 至 {variables["before"]}',
                 f'按当前累计票数排序，共 {len(products)} 个；不是官方日榜。', '']
        for index, product in enumerate(products, 1):
            lines.extend([f'## {index}. {product["name"]}', '', product['tagline'], '',
                          f'票数：{product["votesCount"]}；评论：{product["commentsCount"]}',
                          f'发布时间：{product["createdAt"]}',
                          f'[Product Hunt]({product["url"]}) · [产品网站]({product["website"]})',
                          '', product.get('description') or '', ''])
        prefix.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')
        print(f'成功获取 {len(products)} 个产品；报告：{prefix.with_suffix(".md")}')
        print('额度信息：' + json.dumps(quota, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(('调用失败：' + str(exc)).replace(token, '[REDACTED]'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
