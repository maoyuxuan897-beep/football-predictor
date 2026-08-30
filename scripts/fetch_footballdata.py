# -*- coding: utf-8 -*-
"""
football-data.org 数据接入器（主数据源）
========================================
拉取五大联赛（英超/西甲/意甲/德甲/法甲）真实赛程 + 积分榜，
自动更新 data/fixtures.json 与 data/teams.json（含新球队自动扩展与 Elo 校准）。

前置条件（免费）:
  1. 到 https://www.football-data.org/ 注册账号（免费）
  2. 在个人页面生成 API Token
  3. 配置 Token:
       export FOOTBALL_DATA_KEY=你的Token     # 或 --key 传入

用法:
  python scripts/fetch_footballdata.py --days 7
  python scripts/fetch_footballdata.py --days 7 --only fixtures   # 只更新赛程
  python scripts/fetch_footballdata.py --days 7 --only teams      # 只更新球队/积分榜

限流: 免费层 10 次/分钟。本脚本 5 联赛 × 2 接口 = 10 次，联赛间自动等待 6 秒。
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# 强制 UTF-8 输出（计划任务/管道场景下避免 GBK 编码崩溃）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE = "https://api.football-data.org/v4"
# 赛事 -> (竞赛代码, 系统内中文名, 赛程窗口天数, 是否拉积分榜)
COMPETITIONS = [
    ("PL", "英超", 7, True),
    ("PD", "西甲", 7, True),
    ("BL1", "德甲", 7, True),
    ("CL", "欧冠", 30, False),   # 欧冠为比赛日制，窗口放宽；杯赛无联赛积分榜
]


def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def api_get(path, key, retries=3):
    """GET 接口带重试，读取响应头自动节流（football-data.org 要求）"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + path, headers={"X-Auth-Token": key})
            with urllib.request.urlopen(req, timeout=25) as resp:
                # 节流信息: X-RequestCounter-All = 已用/上限, X-RequestCounter-Reset = 重置倒计时(秒)
                counter = resp.headers.get('X-RequestCounter-All', '')
                reset_in = resp.headers.get('X-RequestCounter-Reset', '')
                if counter:
                    print(f"  📊 配额: {counter} | 重置倒计时 {reset_in}s")
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'ignore')[:200]
            if e.code == 403:
                raise RuntimeError(f"鉴权失败(403): {body}。请检查 FOOTBALL_DATA_KEY 是否正确。")
            if e.code in (400, 429):
                # 400 常因请求过于密集触发临时保护（免费层 10 req/min），按指示等待后重试
                wait = 60 if e.code == 429 else 30
                try:
                    wait = int(e.headers.get('X-RequestCounter-Reset', str(wait))) + 2
                except (ValueError, TypeError):
                    pass
                wait = min(wait, 120)
                print(f"  ⚠ 限流保护(HTTP {e.code}: {body[:60]}...)，等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            if e.code == 404:
                raise RuntimeError(f"资源不存在(404): {path}")
            raise RuntimeError(f"HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < retries - 1:
                print(f"  ⚠ 网络错误({e}), 8 秒后重试...")
                time.sleep(8)
                continue
            raise RuntimeError(f"网络错误: {e}")
    raise RuntimeError("重试次数用尽")


# ---------- 队名映射 ----------
def build_name_maps(data_dir):
    """返回 (zh_by_tla, zh_by_en)。tla 按联赛隔离：(league, TLA) -> 中文；english 全名 -> 中文"""
    teams = load_json(os.path.join(data_dir, 'teams.json'), {})
    aliases = load_json(os.path.join(data_dir, 'team_aliases.json'), {})

    zh_by_tla = {}
    # teams.json 的 abbr
    for league, tmap in teams.items():
        for zh, info in tmap.items():
            if info.get('abbr'):
                zh_by_tla[(league, info['abbr'].upper())] = zh
    # team_aliases.json 的 tla 段（按联赛隔离，优先级更高）
    for league, tmap in aliases.get('tla', {}).items():
        for tla, zh in tmap.items():
            zh_by_tla[(league, tla.strip().upper())] = zh

    zh_by_en = {k: v for k, v in aliases.get('english', {}).items()}
    return zh_by_tla, zh_by_en


def resolve_team_name(en_name, tla, league, zh_by_tla, zh_by_en):
    """英文队名 -> 系统中文名。优先级: (联赛,tla) > english 全名 > 去后缀 > 英文兜底"""
    if tla:
        key = (league, tla.strip().upper())
        if key in zh_by_tla:
            return zh_by_tla[key]
    if en_name in zh_by_en:
        return zh_by_en[en_name]
    # 去常见后缀再查一次
    for suffix in (" FC", " CF", " SC", " AFC", " CFC", " UD", " CD", " RC"):
        if en_name.endswith(suffix):
            base = en_name[:-len(suffix)]
            if base in zh_by_en:
                return zh_by_en[base]
    return en_name  # 兜底: 保留英文


# ---------- 球队 Elo 校准 ----------
def elo_from_rank(rank):
    """积分榜排名 -> 基线 Elo（第1名1600，每降1名-10）"""
    return 1600 - (rank - 1) * 10


def stat_from_rank(rank, league_avg):
    """排名 -> 基线攻防数据（越高越强）"""
    factor = 1 + (10 - rank) * 0.02
    return {
        'avg_goals': round(league_avg * factor, 2),
        'avg_conceded': round(league_avg * (2 - factor), 2)
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', default=os.environ.get('FOOTBALL_DATA_KEY', ''))
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    ap.add_argument('--days', type=int, default=7, help='拉取未来几天赛程')
    ap.add_argument('--only', choices=['all', 'fixtures', 'teams'], default='all')
    args = ap.parse_args()

    if not args.key:
        print("❌ 缺少 football-data.org API Token")
        print("   1. 前往 https://www.football-data.org/ 免费注册")
        print("   2. 登录后在个人页生成 Token")
        print("   3. 传参 --key TOKEN 或设置环境变量 FOOTBALL_DATA_KEY")
        sys.exit(1)

    data_dir = args.data_dir
    teams_path = os.path.join(data_dir, 'teams.json')
    leagues_path = os.path.join(data_dir, 'leagues.json')
    fixtures_path = os.path.join(data_dir, 'fixtures.json')

    leagues_cfg = load_json(leagues_path, {})
    teams = load_json(teams_path, {})
    fixtures_data = load_json(fixtures_path, {"_meta": {}, "fixtures": []})
    zh_by_tla, zh_by_en = build_name_maps(data_dir)

    today = datetime.now()
    date_from = today.strftime('%Y-%m-%d')

    print(f"⚽ 开始拉取 football-data.org 真实数据（欧冠/英超/西甲/德甲）")
    new_fixtures = []
    updated_teams = 0
    new_teams = 0

    for code, league, days, need_standings in COMPETITIONS:
        date_to = (today + timedelta(days=days)).strftime('%Y-%m-%d')
        print(f"\n◆ {league} ({code}) [{date_from} ~ {date_to}]")
        try:
            # 1) 未来赛程
            if args.only in ('all', 'fixtures'):
                matches = api_get(
                    f"/competitions/{code}/matches?dateFrom={date_from}&dateTo={date_to}&status=SCHEDULED,TIMED",
                    args.key)
                cnt = 0
                for m in matches.get('matches', []):
                    home_en = m['homeTeam']['name']
                    away_en = m['awayTeam']['name']
                    home = resolve_team_name(home_en, m['homeTeam'].get('tla'), league, zh_by_tla, zh_by_en)
                    away = resolve_team_name(away_en, m['awayTeam'].get('tla'), league, zh_by_tla, zh_by_en)
                    # UTC -> 北京时间
                    utc = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00'))
                    bj = utc + timedelta(hours=8)
                    new_fixtures.append({
                        'date': bj.strftime('%Y-%m-%d'),
                        'time': bj.strftime('%H:%M'),
                        'league': league,
                        'home': home,
                        'away': away,
                        'round': m.get('matchday', 0)
                    })
                    cnt += 1
                print(f"  赛程: {cnt} 场")

            # 2) 积分榜 -> 球队数据（仅联赛，欧冠杯赛跳过）
            if args.only in ('all', 'teams') and need_standings:
                standings = api_get(f"/competitions/{code}/standings", args.key)
                table = None
                for s in standings.get('standings', []):
                    if s.get('type') == 'TOTAL':
                        table = s.get('table', [])
                        break
                league_avg = leagues_cfg.get(league, {}).get('avg_goals', 1.45)
                if league not in teams:
                    teams[league] = {}
                t_cnt = 0
                for row in (table or []):
                    tla = row['team'].get('tla')
                    en = row['team']['name']
                    zh = resolve_team_name(en, tla, league, zh_by_tla, zh_by_en)
                    rank = row.get('position', 10)
                    if zh in teams[league]:
                        continue  # 已有精细数据的球队保留
                    base = stat_from_rank(rank, league_avg)
                    teams[league][zh] = {
                        'elo': elo_from_rank(rank),
                        'avg_goals': base['avg_goals'],
                        'avg_conceded': base['avg_conceded'],
                        'abbr': tla or ''
                    }
                    t_cnt += 1
                    new_teams += 1
                updated_teams += len(table or [])
                print(f"  积分榜: {len(table or [])} 队（新增 {t_cnt} 支）")
        except RuntimeError as e:
            print(f"  ❌ {e}")
        time.sleep(9)  # 限流保护（免费层 10 req/min，留安全余量）

    # 写回赛程
    if args.only in ('all', 'fixtures') and new_fixtures:
        new_fixtures.sort(key=lambda x: (x['date'], x['time']))
        fixtures_data['fixtures'] = new_fixtures
        fixtures_data['_meta'] = {
            "season": "2026-27",
            "round": f"真实赛程（football-data.org 拉取 {date_from} 起 {len(new_fixtures)} 场）",
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "source": "football-data.org",
            "note": "✅ 真实数据：欧冠/英超/西甲/德甲，由 football-data.org 每日自动拉取更新。"
        }
        save_json(fixtures_path, fixtures_data)
        print(f"\n📅 赛程已更新: {len(new_fixtures)} 场 → {os.path.abspath(fixtures_path)}")

    # 写回球队（含英文残留清理：未翻译的官方名键删除，中文键已在上面建立）
    if args.only in ('all', 'teams'):
        import re
        removed = 0
        for league in teams:
            for tname in list(teams[league].keys()):
                if re.search(r'[a-zA-Z]{3,}', tname):
                    del teams[league][tname]
                    removed += 1
        if removed:
            print(f"🧹 清理未翻译队名 {removed} 条")
        if new_teams or removed:
            save_json(teams_path, teams)
        print(f"🏟 球队数据: 共 {sum(len(v) for v in teams.values())} 支 → {os.path.abspath(teams_path)}")

    print("\n✅ 拉取完成。运行以下命令刷新预测看板:")
    print("   python scripts/run_prediction.py")


if __name__ == '__main__':
    main()
