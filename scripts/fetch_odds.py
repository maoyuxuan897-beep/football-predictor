# -*- coding: utf-8 -*-
"""
中国体育彩票 · 竞彩足球赔率接入器
=================================
拉取竞彩官方胜平负(had) + 让球胜平负(hhad)赔率，按赛事筛选（欧冠/英超/西甲/德甲），
队名映射后写入 data/odds.json 供价值投注模型使用。

数据源: 竞彩官方公开接口（免费，无需 key）
  https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=had,hhad&channel=c

用法:
  python scripts/fetch_odds.py [--days 7]

输出 data/odds.json:
  {
    "generated_at": "...",
    "odds": [{
      "date": "2026-08-29", "time": "21:30", "league": "德甲",
      "home": "埃尔沃斯堡", "away": "勒沃库森",
      "had": {"h": 4.85, "d": 4.30, "a": 1.45},
      "hhad": {"h": 2.35, "d": 3.95, "a": 2.22, "goal_line": "+1"},
      "jc_no": "周六009", "update_time": "..."
    }]
  }
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

API = ("https://webapi.sporttery.cn/gateway/jc/football/"
       "getMatchCalculatorV1.qry?poolCode=had,hhad&channel=c")

# 关注的赛事（竞彩 leagueAbbName）
WATCH_LEAGUES = {"欧冠", "英超", "西甲", "德甲"}

# 竞彩中文简称 -> 系统中文名（差异项；一致的无需列出）
JC_ALIAS = {
    "埃沃斯堡": "埃尔沃斯贝格",
    "莱比锡": "莱比锡红牛",
    "沃夫斯堡": "沃尔夫斯堡",
    "缅恩斯": "美因茨",
    "弗赖堡": "弗赖堡",
    "奥格斯堡": "奥格斯堡",
    "贺芬咸": "霍芬海姆",
    "圣保利": "圣保利",
    "哈化柏林": "柏林赫塔",
    "乌尼昂柏林": "柏林联合",
    "利华古逊": "勒沃库森",
    "慕逊加柏": "门兴格拉德巴赫",
    "多蒙特": "多特蒙德",
    "史特加": "斯图加特",
    "拜仁慕尼黑": "拜仁慕尼黑",
    "皇家马德里": "皇家马德里",
    "马德里体育会": "马德里竞技",
    "毕尔包": "毕尔巴鄂竞技",
    "皇家苏斯达": "皇家社会",
    "维拉利尔": "比利亚雷亚尔",
    "西维尔": "塞维利亚",
    "华伦西亚": "瓦伦西亚",
    "贝迪斯": "皇家贝蒂斯",
    "加泰": "赫塔菲",
    "切尔达": "塞尔塔",
    "奥沙辛拿": "奥萨苏纳",
    "杰罗纳": "赫罗纳",
    "巴列卡诺": "巴列卡诺",
    "艾拉维斯": "阿拉维斯",
    "爱斯宾奴": "西班牙人",
    "马略卡": "马略卡",
    "雷加利斯": "莱加内斯",
    "曼城": "曼城",
    "阿仙奴": "阿森纳",
    "利物浦": "利物浦",
    "车路士": "切尔西",
    "纽卡素": "纽卡斯尔",
    "阿士东维拉": "阿斯顿维拉",
    "曼联": "曼联",
    "热刺": "热刺",
    "白礼顿": "布莱顿",
    "宾福特": "布伦特福德",
    "爱华顿": "埃弗顿",
    "般尼茅夫": "伯恩茅斯",
    "水晶宫": "水晶宫",
    "富咸": "富勒姆",
    "狼队": "狼队",
    "李斯特城": "莱斯特城",
    "修咸顿": "南安普顿",
    "诺定咸森林": "诺丁汉森林",
    "叶士域治": "伊普斯维奇",
    "列斯联": "利兹联",
    "高云地利": "考文垂",
    "新特兰": "桑德兰",
    "侯城": "赫尔城",
    # 欧冠常见球队
    "巴黎圣日耳门": "巴黎圣日耳曼",
    "摩纳哥": "摩纳哥",
    "马赛": "马赛",
    "里尔": "里尔",
    "里昂": "里昂",
    "国际米兰": "国际米兰",
    "AC米兰": "AC米兰",
    "祖云达斯": "尤文图斯",
    "拿玻里": "那不勒斯",
    "阿特兰大": "亚特兰大",
    "博洛尼亚": "博洛尼亚",
    "罗马": "罗马",
    "拉素": "拉齐奥",
    "费伦天拿": "佛罗伦萨",
    "本菲卡": "本菲卡",
    "波图": "波尔图",
    "士砵亭": "里斯本竞技",
    "阿积士": "阿贾克斯",
    "PSV燕豪芬": "埃因霍温",
    "飞燕诺": "费耶诺德",
    "些路迪": "凯尔特人",
    "格拉斯哥流浪": "流浪者",
    "萨克达": "顿涅茨克矿工",
    "萨格勒布戴拿模": "萨格勒布迪纳摩",
    "贝尔格莱德红星": "贝尔格莱德红星",
    "年青人": "伯尔尼年轻人",
    "萨尔茨堡": "萨尔茨堡红牛",
    "布拉格斯巴达": "布拉格斯巴达",
    "布鲁日": "布鲁日",
    "皇家安特卫普": "皇家安特卫普",
    "勒沃库森": "勒沃库森",
    "多特蒙德": "多特蒙德"
}

# 竞彩英文码 -> 系统中文名（兜底，覆盖与 football-data tla 不一致的）
JC_CODE = {
    "LEV": "勒沃库森", "ELV": "埃尔沃斯贝格", "RBL": "莱比锡红牛",
    "PSG": "巴黎圣日耳曼", "BAY": "拜仁慕尼黑", "RMA": "皇家马德里",
    "MCI": "曼城", "ARS": "阿森纳", "LIV": "利物浦", "CHE": "切尔西",
    "INT": "国际米兰", "JUV": "尤文图斯", "MIL": "AC米兰",
    "B04": "勒沃库森", "BVB": "多特蒙德", "SGE": "法兰克福",
    "VFB": "斯图加特", "BMG": "门兴格拉德巴赫", "SCF": "弗赖堡",
    "M05": "美因茨", "FCA": "奥格斯堡", "TSG": "霍芬海姆",
    "HSV": "汉堡", "KOE": "科隆", "S04": "沙尔克04",
    "UNB": "柏林联合", "SVW": "云达不来梅", "WOB": "沃尔夫斯堡",
    "ATH": "毕尔巴鄂竞技", "RSO": "皇家社会", "VIL": "比利亚雷亚尔",
    "SEV": "塞维利亚", "VAL": "瓦伦西亚", "BET": "皇家贝蒂斯",
    "GET": "赫塔菲", "CEL": "塞尔塔", "OSA": "奥萨苏纳",
    "GIR": "赫罗纳", "RAY": "巴列卡诺", "ALA": "阿拉维斯",
    "ESP": "西班牙人", "MLL": "马略卡", "LEG": "莱加内斯",
    "NEW": "纽卡斯尔", "AVL": "阿斯顿维拉", "MUN": "曼联", "TOT": "热刺",
    "BHA": "布莱顿", "BRE": "布伦特福德", "EVE": "埃弗顿", "BOU": "伯恩茅斯",
    "CRY": "水晶宫", "FUL": "富勒姆", "WOL": "狼队", "LEI": "莱斯特城",
    "SOU": "南安普顿", "NOT": "诺丁汉森林", "IPS": "伊普斯维奇",
    "LEE": "利兹联", "COV": "考文垂", "SUN": "桑德兰", "HUL": "赫尔城"
}


def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch():
    req = urllib.request.Request(API, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.sporttery.cn/"
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def resolve(name, code):
    if name in JC_ALIAS:
        return JC_ALIAS[name]
    if code and code in JC_CODE:
        return JC_CODE[code]
    return name  # 兜底: 竞彩中文简称（多数与系统一致）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    args = ap.parse_args()

    data_dir = args.data_dir
    print("⚽ 拉取竞彩官方赔率（胜平负+让球胜平负）...")
    try:
        d = fetch()
    except Exception as e:
        print(f"❌ 竞彩接口请求失败: {e}")
        sys.exit(1)

    if not d.get('success'):
        print(f"❌ 接口返回异常: {d.get('errorMessage')}")
        sys.exit(1)

    match_list = d.get('value', {}).get('matchInfoList', [])
    odds_out = []
    seen = set()

    for info in match_list:
        for m in info.get('subMatchList', []):
            league = m.get('leagueAbbName', '')
            if league not in WATCH_LEAGUES:
                continue
            home = resolve(m.get('homeTeamAbbName', ''), m.get('homeTeamCode', ''))
            away = resolve(m.get('awayTeamAbbName', ''), m.get('awayTeamCode', ''))
            had = m.get('had') or {}
            hhad = m.get('hhad') or {}
            if not had:
                continue
            key = (m.get('matchDate', ''), home, away)
            if key in seen:
                continue
            seen.add(key)
            try:
                odds_out.append({
                    'date': m.get('matchDate', ''),
                    'time': (m.get('matchTime') or '')[:5],
                    'league': league,
                    'home': home,
                    'away': away,
                    'had': {'h': float(had['h']), 'd': float(had['d']), 'a': float(had['a'])},
                    'hhad': {
                        'h': float(hhad['h']), 'd': float(hhad['d']), 'a': float(hhad['a']),
                        'goal_line': hhad.get('goalLine', '')
                    } if hhad else None,
                    'jc_no': m.get('matchNumStr', ''),
                    'update_time': f"{had.get('updateDate','')} {had.get('updateTime','')}"
                })
            except (KeyError, ValueError, TypeError) as e:
                print(f"  ⚠ 赔率解析失败 {home} vs {away}: {e}")

    odds_out.sort(key=lambda x: (x['date'], x['time']))
    result = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': '中国体育彩票·竞彩足球（官方公开接口）',
        'odds': odds_out
    }
    path = os.path.join(data_dir, 'odds.json')
    save_json(path, result)
    print(f"✅ 竞彩赔率已更新: {len(odds_out)} 场 → {os.path.abspath(path)}")
    for o in odds_out[:6]:
        h = o['had']
        print(f"   {o['date']} {o['time']} {o['league']}: {o['home']} vs {o['away']} | "
              f"主{h['h']} 平{h['d']} 客{h['a']}")

    if len(odds_out) < 3:
        print("\n💡 当前竞彩在售场次较少（比赛日分布），可在临近比赛时重跑获取更多赔率。")


if __name__ == '__main__':
    main()
