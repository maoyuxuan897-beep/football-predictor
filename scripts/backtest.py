# -*- coding: utf-8 -*-
"""
价值信号赛果回测
================
读取 prediction_log.json 中已结算记录，统计：
- 各信号级别（STRONG/VALUE/WATCH/NONE）命中率 vs 模型概率
- 模拟投注：100 本金按半 Kelly 比例分配，累计收益曲线
输出 data/backtest.json（供看板「回测」页签渲染）

用法:
  python scripts/backtest.py
  建议先运行 scripts/settle_results.py 结算赛果
"""

import json
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, 'data')


def main():
    log_path = os.path.join(DATA_DIR, 'prediction_log.json')
    if not os.path.exists(log_path):
        print("❌ 无 prediction_log.json，请先运行 run_prediction.py")
        sys.exit(1)
    with open(log_path, 'r', encoding='utf-8') as f:
        plog = json.load(f)
    records = list(plog.get('records', {}).values())
    settled = [r for r in records if r.get('settled') and r.get('hit') is not None]
    if not settled:
        print("ℹ️ 暂无已结算记录（比赛开赛后运行 scripts/settle_results.py 结算）")
        _empty_out()
        return

    # ---- 1. 按信号级别统计 ----
    sig_order = ['strong', 'value', 'watch', 'none']
    stats = []
    for sig in sig_order:
        g = [r for r in settled if r.get('signal') == sig]
        if not g:
            continue
        hits = sum(1 for r in g if r.get('hit'))
        rate = hits / len(g) * 100
        avg_prob = sum(r['model_prob'].get(r['direction'], 0) for r in g) / len(g)
        avg_edge = sum(r.get('edge') or 0 for r in g) / len(g)
        avg_ev = sum(r.get('ev') or 0 for r in g) / len(g)
        stats.append({
            'signal': sig, 'n': len(g), 'hits': hits,
            'hit_rate': round(rate, 1),
            'avg_model_prob': round(avg_prob, 1),
            'avg_edge': round(avg_edge, 1),
            'avg_ev': round(avg_ev, 1)
        })

    # ---- 2. 模拟投注（100 本金，半Kelly比例，仅 STRONG/VALUE） ----
    bets = [r for r in settled if r.get('signal') in ('strong', 'value') and r.get('odds')]
    bets.sort(key=lambda r: r.get('date', ''))
    BANKROLL = 100.0
    balance = BANKROLL
    sim = []
    for i, r in enumerate(bets):
        kelly = max(0.0, float(r.get('kelly') or 0))
        amt = min(BANKROLL * kelly / 100.0 * 1.0, BANKROLL * 0.30)
        # 简化：单场按 kelly 占本金比例（kelly 已是半Kelly%，直接作比例）
        amt = min(BANKROLL * kelly / 100.0, BANKROLL * 0.30)
        if amt <= 0:
            continue
        odds = float(r['odds'])
        if r.get('hit'):
            pnl = amt * (odds - 1)
        else:
            pnl = -amt
        balance += pnl
        sim.append({
            'date': r['date'], 'league': r['league'],
            'home': r['home'], 'away': r['away'],
            'direction': r['direction'], 'odds': odds, 'kelly': kelly,
            'amt': round(amt, 1), 'hit': bool(r.get('hit')), 'pnl': round(pnl, 1),
            'balance': round(balance, 1)
        })

    summary = {
        'bankroll': BANKROLL,
        'bets': len(sim),
        'hits': sum(1 for s in sim if s['hit']),
        'final_balance': round(balance, 1),
        'roi': round((balance - BANKROLL) / BANKROLL * 100, 1),
        'settled_total': len(settled)
    }

    out = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stats': stats,
        'sim': summary,
        'sim_detail': sim
    }
    out_path = os.path.join(DATA_DIR, 'backtest.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # ---- 控制台报告 ----
    print("=== 价值信号回测报告 ===")
    print(f"{'信号':<8}{'场次':<5}{'命中':<5}{'命中率':<8}{'平均模型概率':<12}{'平均Edge':<10}{'平均EV':<8}")
    for s in stats:
        print(f"{s['signal']:<8}{s['n']:<5}{s['hits']:<5}{s['hit_rate']}%   "
              f"{s['avg_model_prob']}%   {s['avg_edge']}%   {s['avg_ev']}%")
    print(f"\n模拟投注（¥{summary['bankroll']} 本金，半Kelly，仅 STRONG/VALUE）:")
    print(f"  场次 {summary['bets']} | 命中 {summary['hits']} | 最终余额 ¥{summary['final_balance']} | 收益率 {summary['roi']}%")
    print(f"  → {os.path.abspath(out_path)}")


def _empty_out():
    out = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stats': [], 'sim': {'bets': 0, 'hits': 0, 'final_balance': 100.0, 'roi': 0.0, 'settled_total': 0},
        'sim_detail': []
    }
    with open(os.path.join(DATA_DIR, 'backtest.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
