# -*- coding: utf-8 -*-
"""
推送竞彩赔率到 GitHub 仓库（供云端价值分析使用）
==================================================
竞彩接口对海外 IP 屏蔽（云端拉取返回 HTTP 567），因此由本机每日拉取赔率后
推送到仓库 data/odds.json，云端 ci_run 自动读取仓库中的赔率做价值分析。

用法:
  python scripts/push_odds_to_github.py
  需要 GH_TOKEN（用户级 PAT，读取环境变量或 .env 中的 GH_TOKEN）
"""

import base64
import json
import os
import sys
import urllib.request
import urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_gh_token():
    t = os.environ.get('GH_TOKEN', '')
    if t:
        return t
    env_path = os.path.join(BASE, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('GH_TOKEN='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=os.environ.get('GH_REPO', 'maoyuxuan897-beep/football-predictor'))
    args = ap.parse_args()

    token = load_gh_token()
    if not token:
        print("⚠ 未配置 GH_TOKEN（环境变量或 .env），跳过推送")
        return 1

    odds_path = os.path.join(BASE, 'data', 'odds.json')
    if not os.path.exists(odds_path):
        print("⚠ data/odds.json 不存在（先运行 fetch_odds.py）")
        return 1

    with open(odds_path, 'rb') as f:
        content_b64 = base64.b64encode(f.read()).decode()

    path = '/contents/data/odds.json'
    url = f'https://api.github.com/repos/{args.repo}' + path
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github+json",
               "Content-Type": "application/json"}

    # 获取当前 sha（文件已存在则更新）
    sha = None
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            import json as j
            sha = j.load(r).get('sha')
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"⚠ 查询文件失败: HTTP {e.code}")
            return 1

    body = json.dumps({
        "message": "update odds.json (auto)",
        "content": content_b64,
        "sha": sha,
        "branch": "main"
    }).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
            print(f"✅ 竞彩赔率已推送到仓库: {d.get('content',{}).get('path','data/odds.json')} (sha={d.get('content',{}).get('sha','')[:7]})")
            return 0
    except urllib.error.HTTPError as e:
        print(f"❌ 推送失败: HTTP {e.code}: {e.read().decode('utf-8','ignore')[:200]}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
