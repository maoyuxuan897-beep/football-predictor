# -*- coding: utf-8 -*-
"""
juhe 聚合数据接入脚本（真实赛程自动更新）
用法:
  python fetch_juhe.py --key YOUR_APPKEY [--days 7] [--dry-run]

流程:
  1. 调用 juhe 足球 API 拉取各联赛赛程
  2. 按别名表 data/team_aliases.json 映射为系统内球队名
  3. 筛选未来 N 天未开赛比赛, 写回 data/fixtures.json
  4. 重跑 python run_prediction.py 即可刷新看板

注意:
  - juhe 免费版覆盖: 英超(yingchao) 意甲(yijia) 德甲(dejia) 法甲(fajia) 中超(zhongchao) 苏超(jiangsu) 西乙(xijia)
  - 西甲暂不在 juhe 免费列表, 建议用 LiveScore MCP 补充 (见 README)
  - 队名映射维护在 data/team_aliases.json (juhe 中文名 -> 系统内名)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

BASE = "http://apis.juhe.cn/fapig/football"

# juhe type -> 系统联赛名
JUHE_LEAGUES = {
    "yingchao": "英超",
    "yijia": "意甲",
    "dejia": "德甲",
    "fajia": "法甲",
}


def fetch(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def load_aliases(data_dir):
    path = os.path.join(data_dir, 'team_aliases.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def map_team(name, aliases, league):
    """juhe 队名 -> 系统内队名; 未收录则保留原名"""
    if name in aliases:
        return aliases[name]
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', default=os.environ.get('JUHE_FOOTBALL_KEY', ''))
    ap.add_argument('--days', type=int, default=7, help='拉取未来 N 天')
    ap.add_argument('--dry-run', action='store_true', help='只打印不写文件')
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    args = ap.parse_args()

    if not args.key:
        print("❌ 缺少 juhe AppKey")
        print("   1. 前往 https://www.juhe.cn/docs/api/id/90 免费申请")
        print("   2. 传入 --key YOUR_KEY 或设置环境变量 JUHE_FOOTBALL_KEY")
        sys.exit(1)

    aliases = load_aliases(args.data_dir)
    today = datetime.now().date()
    end = today + timedelta(days=args.days)
    fixtures = []
    meta_note = f"数据源: juhe 聚合数据 API (AppKey 已配置) · 拉取 {today} ~ {end} 未开赛比赛"

    for jtype, league in JUHE_LEAGUES.items():
        url = f"{BASE}/query?key={args.key}&type={jtype}"
        print(f"  拉取 {league} ({jtype}) ...")
        try:
            resp = fetch(url)
        except Exception as e:
            print(f"  ⚠ {league} 拉取失败: {e}")
            continue
        if resp.get('error_code') != 0:
            print(f"  ⚠ {league} 接口返回: {resp.get('reason')} (code={resp.get('error_code')})")
            continue
        matchs = resp.get('result', {}).get('matchs', [])
        for m in matchs:
            d = m.get('date', '')
            status = m.get('status_text', '')
            try:
                mdate = datetime.strptime(d, '%Y-%m-%d').date()
            except Exception:
                continue
            if today <= mdate <= end and '未开赛' in status:
                home = map_team(m.get('team1', ''), aliases, league)
                away = map_team(m.get('team2', ''), aliases, league)
                fixtures.append({
                    'date': d,
                    'time': m.get('time_start', '00:00'),
                    'league': league,
                    'home': home,
                    'away': away,
                    'round': m.get('round', '')
                })
        print(f"  ✓ 命中 {sum(1 for f in fixtures if f['league'] == league)} 场未开赛")

    fixtures.sort(key=lambda f: (f['date'], f['time']))
    print(f"\n共获取 {len(fixtures)} 场未来比赛")

    if args.dry_run:
        for f in fixtures:
            print(f"  {f['date']} {f['time']} [{f['league']}] {f['home']} vs {f['away']} 第{f['round']}轮")
        return

    out = {
        '_meta': {
            'season': '2026-27',
            'round': f'实时赛程 {today} ~ {end}',
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'source': 'live',
            'note': meta_note
        },
        'fixtures': fixtures
    }
    path = os.path.join(args.data_dir, 'fixtures.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✅ 已写入 {path}")
    print(f"   下一步: python scripts/run_prediction.py 刷新看板")


if __name__ == '__main__':
    main()
