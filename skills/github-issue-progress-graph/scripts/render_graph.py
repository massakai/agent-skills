"""取得済みIssueデータから依存図と本文更新候補を生成する。通信は行わない。"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

START = '<!-- issue-progress-graph:start -->'
END = '<!-- issue-progress-graph:end -->'
COLORS = {
    'Todo': ('#f1f5f9', '#64748b'), 'Ready': ('#cffafe', '#0891b2'),
    'In Progress': ('#dbeafe', '#2563eb'), 'In Review': ('#f3e8ff', '#9333ea'),
    'Blocked': ('#ffedd5', '#ea580c'), 'Done': ('#dcfce7', '#15803d'),
}


def label(value):
    """外部文字列を一行のMermaidラベルへ変換する。"""
    text = ' '.join(value.split())
    return ''.join(f'#{ord(c)};' if c in '&"<>#`\\[]{}|;' else c for c in text)


def validate(data):
    """正規化データの欠落・重複・不正参照を拒否する。"""
    if data['complete'] is not True or data['scope'] != 'direct':
        raise ValueError('全ページ取得済みのdirect集合が必要')
    if not datetime.fromisoformat(data['captured_at']).tzinfo:
        raise ValueError('取得日時にはtimezoneが必要')
    nodes = data['nodes']
    urls = [n['url'] for n in nodes]
    if len(urls) != len(set(urls)) or data['root_url'] in urls:
        raise ValueError('重複またはrootの混入')
    host = urlsplit(data['root_url']).netloc
    for url in [data['root_url'], *urls, *data['omitted_closed']]:
        p = urlsplit(url)
        if p.scheme != 'https' or p.netloc != host or not re.fullmatch(r'/[^/]+/[^/]+/issues/[1-9][0-9]*', p.path) or p.query or p.fragment or p.username:
            raise ValueError('同じGitHub hostのIssue URLが必要')
    omitted = set(data['omitted_closed'])
    if omitted & set(urls):
        raise ValueError('表示対象と省略対象が重複')
    for n in nodes:
        if n['kind'] not in ('child', 'boundary') or n['state'] not in ('OPEN', 'CLOSED'):
            raise ValueError('kind/stateが不正')
        if not n['title'] or not n['status'] or not n['status_reason']:
            raise ValueError('title/statusと状態の取得根拠が必要')
        if not set(n['blocked_by']) <= set(urls) | omitted:
            raise ValueError('未取得の先行Issueがある')
    return sorted(nodes, key=lambda n: n['url'])


def render(data):
    """実線のnative依存と点線のStart/Goal補助線を生成する。"""
    nodes = validate(data)
    ids = {n['url']: f'n{i}' for i, n in enumerate(nodes)}
    edges = {(ids[s], ids[n['url']]) for n in nodes for s in n['blocked_by'] if s in ids}
    incoming = {t for s, t in edges}
    outgoing = {s for s, t in edges}
    pending = set(ids.values())
    while pending:
        roots = {n for n in pending if not any(t == n and s in pending for s, t in edges)}
        if not roots:
            raise ValueError('循環依存を解消してから図を公開する')
        pending -= roots
    count = Counter(n['status'] for n in nodes if n['kind'] == 'child')
    lines = [START, '### Sub-Issueの依存関係と進捗', '', f"取得日時: {data['captured_at']}",
             f"状態の正本: {label(data['status_source'])}",
             '直接のsub-issue: ' + '、'.join(f'{label(s)} {v}件' for s, v in sorted(count.items())),
             '実線は先行→後続のnative依存、点線はStart/Goalへの表示用補助線である。',
             '破線枠は集合外の先行Issueであり、完了済み集合外依存と深い子孫の内部は省略する。',
             '状態は取得時点の値であり、着手可否・受入条件の充足は別途照合する。',
             '灰=Todo、水色=Ready、青=In Progress、紫=In Review、橙=Blocked、緑=Done、白=その他・Unknown。',
             '', '```mermaid', 'flowchart TB', '  start(["Start"])', '  goal(["Goal：成果物の受入条件充足"])']
    for n in nodes:
        key = ids[n['url']]
        number = n['url'].rsplit('/', 1)[1]
        repo = '/'.join(urlsplit(n['url']).path.split('/')[1:3])
        lines += [f'  {key}["{label(repo)} #{number} {label(n["title"])}<br/>{label(n["status"])}"]']
        fill, stroke = COLORS.get(n['status'], ('#ffffff', '#334155'))
        lines += [f'  style {key} fill:{fill},stroke:{stroke},color:#0f172a' + (',stroke-dasharray:5 5' if n['kind'] == 'boundary' else '')]
    for s, t in sorted(edges):
        lines += [f'  {s} --> {t}']
    for n in nodes:
        key = ids[n['url']]
        if key not in incoming:
            lines += [f'  start -.-> {key}']
        if n['kind'] == 'child' and key not in outgoing:
            lines += [f'  {key} -.-> goal']
    if not nodes:
        lines += ['  start -. "対象なし・受入未判定" .-> goal']
    lines += ['```']
    for n in nodes:
        if n['status'] == 'Unknown':
            lines += [f"- 状態未設定: {n['url']} — {label(n['status_reason'])}"]
        if n['status'] in COLORS and (n['status'] == 'Done') != (n['state'] == 'CLOSED'):
            lines += [f"- 状態要照合: {n['url']} — Issue {n['state']} / Status {label(n['status'])}"]
    return '\n'.join([*lines, END])


def update_body(body, block):
    """一対の管理マーカー内だけを置換し、時刻だけの更新を避ける。"""
    if body.count(START) != 1 or body.count(END) != 1 or body.index(END) < body.index(START):
        raise ValueError('管理マーカーを一対だけ指定セクションへ配置すること')
    begin, end = body.index(START), body.index(END) + len(END)
    old = body[begin:end]
    without_time = lambda s: re.sub(r'^取得日時: .*$', '', s, flags=re.M)
    if without_time(old) == without_time(block):
        return body
    return body[:begin] + block + body[end:]


def main():
    """図または更新候補本文を出力し、送信前照合用に元本文hashを表示する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--body', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    block = render(json.loads(args.snapshot.read_text()))
    if args.body:
        body = args.body.read_text()
        block = update_body(body, block)
        print('body_sha256=' + hashlib.sha256(body.encode()).hexdigest())
    args.output.write_text(block)


if __name__ == '__main__':
    main()
