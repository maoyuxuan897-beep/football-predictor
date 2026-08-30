# -*- coding: utf-8 -*-
"""
TheSportsDB 数据接入器（零门槛备选，无需注册）
==============================================
TheSportsDB 提供公开测试接口（免费，无需 key），可拉取五大联赛真实赛程。

⚠ 限制: 免费测试接口每个请求仅返回前 5 条数据，覆盖不全，仅用于体验
       "真实数据自动更新"的完整流程。生产建议使用 football-data.org（见
       fetch_footballdata.py，免费注册 key 后覆盖完整五大联赛）。

用法:
  python scripts/fetch_thesportsdb.py --days 7
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

# 强制 UTF-8 输出（管道/计划任务场景）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "https://www.thesportsdb.com/api/v1/json/3"
# TheSportsDB 联赛 ID
LEAGUE_IDS = {"英超": 4328, "西甲": 4335, "意甲": 4332, "德甲": 4331, "法甲": 4334}
SEASON = "2026-2027"


def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def api_get(path):
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def load_name_maps(data_dir):
    teams = load_json(os.path.join(data_dir, 'teams.json'), {})
    aliases = load_json(os.path.join(data_dir, 'team_aliases.json'), {})
    zh_by_tla = {}
    for league, tmap in teams.items():
        for zh, info in tmap.items():
            if info.get('abbr'):
                zh_by_tla[info['abbr'].upper()] = zh
    zh_by_en = dict(aliases.get('english', {}))
    # TheSportsDB 常用短名/变体补充
    zh_by_en.update({
        "Bournemouth": "伯恩茅斯", "Everton": "埃弗顿", "Nottingham Forest": "诺丁汉森林",
        "Crystal Palace": "水晶宫", "Brighton": "布莱顿", "Brighton and Hove Albion": "布莱顿",
        "West Ham": "西汉姆联", "Wolves": "狼队", "Leicester": "莱斯特城", "Southampton": "南安普顿",
        "Manchester City": "曼城", "Manchester United": "曼联", "Newcastle": "纽卡斯尔",
        "Tottenham": "热刺", "Fulham": "富勒姆", "Aston Villa": "阿斯顿维拉",
        "Inter": "国际米兰", "Inter Milan": "国际米兰", "Milan": "AC米兰", "Bologna": "博洛尼亚",
        "Stuttgart": "斯图加特", "Mainz": "美因茨", "Leverkusen": "勒沃库森",
        "Bayer Leverkusen": "勒沃库森", "Bayern Munich": "拜仁慕尼黑", "Dortmund": "多特蒙德",
        "Frankfurt": "法兰克福", "Union Berlin": "柏林联合", "Hamburg": "汉堡",
        "Hoffenheim": "霍芬海姆", "Paderborn": "帕德博恩", "Elversberg": "埃尔沃斯贝格",
        "Lyon": "里昂", "Marseille": "马赛", "Paris Saint-Germain": "巴黎圣日耳曼",
        "Lens": "朗斯", "Rennes": "雷恩", "Lille": "里尔", "Monaco": "摩纳哥", "Nice": "尼斯",
        "Strasbourg": "斯特拉斯堡", "Toulouse": "图卢兹", "Brest": "布雷斯特",
        "Le Havre": "勒阿弗尔", "Lorient": "洛里昂", "Auxerre": "欧塞尔", "Le Mans": "勒芒",
        "Troyes": "特鲁瓦",
        "Real Madrid": "皇家马德里", "Barcelona": "巴塞罗那", "Atletico Madrid": "马德里竞技",
        "Athletic Bilbao": "毕尔巴鄂竞技", "Real Betis": "皇家贝蒂斯", "Villarreal": "比利亚雷亚尔",
        "Valencia": "瓦伦西亚", "Sevilla": "塞维利亚", "Levante": "莱万特", "Celta Vigo": "塞尔塔",
        "Espanyol": "西班牙人", "Deportivo de A Coruña": "拉科鲁尼亚", "Racing de Santander": "桑坦德竞技",
        "Como": "科莫", "Monza": "蒙扎", "Sassuolo": "萨索洛", "Torino": "都灵",
        "Frosinone": "弗罗西诺内", "Leeds United": "利兹联", "Ipswich Town": "伊普斯维奇",
        "Hull City": "赫尔城", "Coventry City": "考文垂"
    })
    return zh_by_tla, zh_by_en


def resolve(en, zh_by_tla, zh_by_en):
    if en in zh_by_en:
        return zh_by_en[en]
    # 加后缀再查（如 Liverpool -> Liverpool FC）
    for suffix in (" FC", " CF", " SC"):
        if en + suffix in zh_by_en:
            return zh_by_en[en + suffix]
    return en  # 兜底: 英文


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    ap.add_argument('--days', type=int, default=7)
    args = ap.parse_args()

    data_dir = args.data_dir
    fixtures_path = os.path.join(data_dir, 'fixtures.json')
    fixtures_data = load_json(fixtures_path, {"_meta": {}, "fixtures": []})
    zh_by_tla, zh_by_en = load_name_maps(data_dir)

    today = datetime.now()
    date_from = today.strftime('%Y-%m-%d')
    date_to = (today + timedelta(days=args.days)).strftime('%Y-%m-%d')

    print(f"⚽ 拉取 TheSportsDB 真实赛程 [{date_from} ~ {date_to}]")
    all_fixtures = []
    for league, lid in LEAGUE_IDS.items():
        found = 0
        for rnd in range(1, 6):
            try:
                d = api_get(f"/eventsround.php?id={lid}&r={rnd}&s={SEASON}")
            except Exception as e:
                print(f"  {league}: 轮次{rnd} 失败 {e}")
                continue
            events = d.get('events') or []
            for e in events:
                date = e.get('dateEvent', '')
                status = e.get('strStatus', '')
                if date < date_from or date > date_to:
                    continue
                if status not in ('NS', 'Not Started', ''):
                    continue  # 只保留未开始的
                home = resolve(e.get('strHomeTeam', ''), zh_by_tla, zh_by_en)
                away = resolve(e.get('strAwayTeam', ''), zh_by_tla, zh_by_en)
                t = (e.get('strTime') or '00:00')[:5]
                all_fixtures.append({
                    'date': date, 'time': t, 'league': league,
                    'home': home, 'away': away, 'round': int(e.get('intRound') or 0)
                })
                found += 1
            if found >= 5:
                break
        print(f"  {league}: {found} 场")
        if not found:
            print(f"    ⚠ 未拉到数据（免费接口可能返回空），可尝试 --days 更大范围")

    all_fixtures.sort(key=lambda x: (x['date'], x['time']))
    if all_fixtures:
        fixtures_data['fixtures'] = all_fixtures
        fixtures_data['_meta'] = {
            "season": "2026-27",
            "round": f"真实赛程（TheSportsDB 拉取 {date_from}~{date_to}，免费接口覆盖有限）",
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "source": "thesportsdb",
            "note": "✅ 真实数据（TheSportsDB 免费接口）。覆盖有限，建议注册 football-data.org 后使用 fetch_footballdata.py 获取完整赛程。"
        }
        save_json(fixtures_path, fixtures_data)

        # 自动扩展球队表：赛程中出现的新球队用联赛默认值加入 teams.json
        teams_path = os.path.join(data_dir, 'teams.json')
        teams = load_json(teams_path, {})
        leagues_cfg = load_json(os.path.join(data_dir, 'leagues.json'), {})
        added = 0
        for fx in all_fixtures:
            league = fx['league']
            if league not in teams:
                teams[league] = {}
            for side in ('home', 'away'):
                tname = fx[side]
                if tname and tname not in teams[league]:
                    avg = leagues_cfg.get(league, {}).get('avg_goals', 1.45)
                    teams[league][tname] = {
                        'elo': 1500, 'avg_goals': avg, 'avg_conceded': avg, 'abbr': ''
                    }
                    added += 1
        if added:
            save_json(teams_path, teams)
            print(f"🏟 球队表自动扩展 +{added} 支（默认实力值，可后续在 teams.json 中校准）")

        print(f"\n📅 已更新 {len(all_fixtures)} 场真实赛程 → {os.path.abspath(fixtures_path)}")
        print("   运行 python scripts/run_prediction.py 刷新看板")
    else:
        print("❌ 未拉到任何赛程，请稍后重试或换用 football-data.org")


if __name__ == '__main__':
    main()
