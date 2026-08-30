# -*- coding: utf-8 -*-
"""
赔率反推 Elo 校准器
====================
从竞彩赔率（data/odds.json）反推球队市场隐含实力，校准 teams.json 中
Elo 为默认值(1500)的球队（未收录/升班马），使模型贴近市场认知。

原理（锚定法）:
  去水后的市场胜率 p_home（归一化到非平局） → 实力差
  Elo差 = 400 × log10(p_home/(1-p_home))  − 主场加成
  已知一方 Elo 即可解另一方；多场比赛取平均。

用法:
  python scripts/update_elo_from_odds.py [--min-matches 1]

先运行 scripts/fetch_odds.py 生成赔率数据，再运行本脚本。
"""

import json
import math
import os
import sys
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ELO_HOME_BONUS = 60


def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def de_vig(odds):
    """欧赔(h/d/a) -> 去水概率 {home, draw, away}"""
    impl = {'home': 1.0 / odds['h'], 'draw': 1.0 / odds['d'], 'away': 1.0 / odds['a']}
    s = sum(impl.values())
    if s <= 0:
        return None
    return {k: v / s for k, v in impl.items()}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    ap.add_argument('--min-matches', type=int, default=1, help='单队最少匹配场次才更新')
    ap.add_argument('--rounds', type=int, default=2, help='迭代轮数（让校准结果传播）')
    args = ap.parse_args()

    data_dir = args.data_dir
    teams_path = os.path.join(data_dir, 'teams.json')
    odds_path = os.path.join(data_dir, 'odds.json')

    teams = load_json(teams_path, {})
    odds_data = load_json(odds_path, {"odds": []})
    odds_list = odds_data.get('odds', [])
    if not odds_list:
        print("❌ data/odds.json 为空，请先运行 scripts/fetch_odds.py")
        sys.exit(1)

    updated_total = 0
    for rnd in range(args.rounds):
        # 统计每队（联赛, 队名）-> [elo 估计]
        estimates = defaultdict(list)
        updated = 0

        for o in odds_list:
            league, home, away = o['league'], o['home'], o['away']
            if league not in teams or home not in teams[league] or away not in teams[league]:
                continue
            had = o.get('had')
            if not had:
                continue
            probs = de_vig(had)
            if not probs:
                continue
            # 归一化到非平局胜率
            ph = probs['home'] / (probs['home'] + probs['away'])
            elo_h = teams[league][home]['elo']
            elo_a = teams[league][away]['elo']

            if elo_a != 1500 and elo_h == 1500:
                est = elo_a + ELO_HOME_BONUS + 400 * math.log10(ph / (1 - ph)) if 0 < ph < 1 else None
                if est:
                    estimates[(league, home)].append(est)
            elif elo_h != 1500 and elo_a == 1500:
                est = elo_h - ELO_HOME_BONUS - 400 * math.log10(ph / (1 - ph)) if 0 < ph < 1 else None
                if est:
                    estimates[(league, away)].append(est)
            elif elo_h == 1500 and elo_a == 1500 and 0 < ph < 1:
                # 双方都无信息：用市场概率对称拉开（围绕 1500）
                diff = 400 * math.log10(ph / (1 - ph))
                estimates[(league, home)].append(1500 + diff * 0.5 + ELO_HOME_BONUS * 0.5)
                estimates[(league, away)].append(1500 - diff * 0.5 - ELO_HOME_BONUS * 0.5)

        for (league, team), elos in estimates.items():
            if len(elos) < args.min_matches:
                continue
            if teams[league][team]['elo'] != 1500:
                continue
            new_elo = int(round(sum(elos) / len(elos)))
            new_elo = max(1350, min(1750, new_elo))
            teams[league][team]['elo'] = new_elo
            print(f"  校准: {league} {team} Elo 1500 → {new_elo}（{len(elos)} 场赔率反推）")
            updated += 1

        if updated:
            updated_total += updated
        if updated == 0 and rnd > 0:
            break

    if updated_total:
        save_json(teams_path, teams)
        print(f"\n✅ 已校准 {updated_total} 支球队 → {os.path.abspath(teams_path)}")
    else:
        print("\nℹ️ 无需校准（所有有赔率的球队已有精细 Elo）")


if __name__ == '__main__':
    main()
