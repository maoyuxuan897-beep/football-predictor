# -*- coding: utf-8 -*-
"""
赛果结算器
==========
从 football-data.org 拉取已完赛比赛比分，结算 prediction_log.json 中未结算的价值信号记录。

用法:
  python scripts/settle_results.py [--key TOKEN]
  自动读取环境变量/.env 中的 FOOTBALL_DATA_KEY
"""

import json
import os
import sys
from datetime import datetime, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'scripts'))
from fetch_footballdata import api_get, build_name_maps, resolve_team_name, COMPETITIONS


def load_key():
    key = os.environ.get('FOOTBALL_DATA_KEY', '')
    if key:
        return key
    env_path = os.path.join(BASE, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('FOOTBALL_DATA_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', default=load_key())
    ap.add_argument('--data-dir', default=os.path.join(BASE, 'data'))
    ap.add_argument('--lookback', type=int, default=6, help='回看过去几天完赛比赛')
    args = ap.parse_args()

    if not args.key:
        print("⚠ 缺少 FOOTBALL_DATA_KEY，跳过结算（可 --key 传入）")
        return

    log_path = os.path.join(args.data_dir, 'prediction_log.json')
    if not os.path.exists(log_path):
        print("ℹ️ 暂无预测日志，无需结算")
        return
    with open(log_path, 'r', encoding='utf-8') as f:
        plog = json.load(f)
    records = plog.setdefault('records', {})
    pending = [r for r in records.values() if not r.get('settled')]
    if not pending:
        print("ℹ️ 所有记录已结算")
        return

    zh_by_tla, zh_by_en = build_name_maps(args.data_dir)
    today = datetime.now()
    date_from = (today - timedelta(days=args.lookback)).strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')

    print(f"⚽ 结算 {len(pending)} 条待结算记录 [拉取 {date_from}~{date_to} 完赛比分]")
    settled = 0
    for code, league, days, need_standings in COMPETITIONS:
        try:
            matches = api_get(
                f"/competitions/{code}/matches?dateFrom={date_from}&dateTo={date_to}&status=FINISHED",
                args.key)
        except Exception as e:
            print(f"  ⚠ {league} 拉取失败: {e}")
            continue
        cnt = 0
        for m in matches.get('matches', []):
            if m.get('status') != 'FINISHED':
                continue
            home = resolve_team_name(m['homeTeam']['name'], m['homeTeam'].get('tla'), league, zh_by_tla, zh_by_en)
            away = resolve_team_name(m['awayTeam']['name'], m['awayTeam'].get('tla'), league, zh_by_tla, zh_by_en)
            score = m.get('score', {}).get('fullTime', {})
            hg, ag = score.get('home'), score.get('away')
            if hg is None or ag is None:
                continue
            try:
                utc = datetime.fromisoformat(m['utcDate'].replace('Z', '+00:00'))
                bj = utc + timedelta(hours=8)
                date = bj.strftime('%Y-%m-%d')
            except (ValueError, KeyError):
                continue
            key = f"{date}|{league}|{home}|{away}"
            if key in records and not records[key].get('settled'):
                rec = records[key]
                outcome = 'home' if hg > ag else 'draw' if hg == ag else 'away'
                rec['result'] = {'home': hg, 'away': ag, 'outcome': outcome}
                rec['hit'] = (outcome == rec.get('direction'))
                rec['settled'] = True
                rec['settled_date'] = date_to
                cnt += 1
                settled += 1
        if cnt:
            print(f"  {league}: 结算 {cnt} 场")
    if settled:
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(plog, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已结算 {settled} 条记录 → {os.path.abspath(log_path)}")
        print("   运行 python scripts/backtest.py 查看回测结果")
    else:
        print("\nℹ️ 本次无匹配记录（比赛可能尚未开赛或未在竞彩/赛程中）")


if __name__ == '__main__':
    main()
