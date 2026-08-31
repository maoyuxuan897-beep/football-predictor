# -*- coding: utf-8 -*-
"""
五大联赛预测系统 · 主流程
用法: python run_prediction.py [--data-dir data] [--out dashboard/index.html]

流程:
1. 读取 data/ 下的联赛参数、球队数据、赛程
2. 调用预测引擎批量计算胜平负/xG/比分/进球分布
3. 渲染 dashboard/template.html 生成自包含可视化看板

接入真实数据后（juhe 赛程 / LiveScore），只需替换 data/fixtures.json 后重跑本脚本。
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 强制 UTF-8 输出（计划任务/管道场景下避免 GBK 编码崩溃）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from engine.prediction_engine import Top5PredictionEngine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dashboard', 'index.html'))
    ap.add_argument('--template', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dashboard', 'template.html'))
    args = ap.parse_args()

    # 1. 加载数据
    engine = Top5PredictionEngine(data_dir=args.data_dir)
    with open(os.path.join(args.data_dir, 'fixtures.json'), 'r', encoding='utf-8') as f:
        fixtures_data = json.load(f)

    meta = fixtures_data.get('_meta', {})
    fixtures = fixtures_data['fixtures']
    n_teams = sum(len(v) for v in engine.teams.values())

    # 2. 批量预测
    predictions = engine.batch_predict(fixtures)
    valid = [p for p in predictions if 'error' not in p]
    errors = [p for p in predictions if 'error' in p]

    # 2.5 加载竞彩赔率 → 价值投注分析（胜平负 + 让球盘）
    odds_path = os.path.join(args.data_dir, 'odds.json')
    odds_loaded = 0
    value_count = 0
    handicap_count = 0
    if os.path.exists(odds_path):
        with open(odds_path, 'r', encoding='utf-8') as f:
            odds_data = json.load(f)
        odds_map = {(o['date'], o['home'], o['away']): o for o in odds_data.get('odds', [])}
        # 竞彩常用简称 → 系统全名 的匹配辅助（如 维拉 ↔ 阿斯顿维拉）
        def name_match(a, b):
            if a == b:
                return True
            # 竞彩用简称：一方包含另一方且不引起歧义（长度≥2 的包含）
            return (len(a) >= 2 and len(b) >= 2) and (a in b or b in a)
        for p in predictions:
            if 'error' in p:
                continue
            o = odds_map.get((p['date'], p['home'], p['away']))
            if not o:
                # 尝试按队名+日期模糊匹配（时间可能有分钟差）
                o = None
                for (d, h, a), v in odds_map.items():
                    if d == p['date'] and name_match(h, p['home']) and name_match(a, p['away']):
                        o = v
                        break
            if o:
                p['odds'] = o['had']
                p['odds_hhad'] = o.get('hhad')
                p['odds_jc'] = o.get('jc_no', '')
                p['value'] = engine.analyze_value(
                    {k: v / 100.0 for k, v in p['prob'].items()}, o['had'])
                odds_loaded += 1
                if p['value'] and p['value'].get('signal') in ('value', 'strong'):
                    value_count += 1
                # 让球盘价值分析（hhad）
                hhad = o.get('hhad')
                if hhad and p.get('score_probs'):
                    try:
                        gl = int(hhad.get('goal_line') or 0)
                    except (ValueError, TypeError):
                        gl = 0
                    hw, hd, ha = engine.handicap_probs(p['score_probs'], gl)
                    p['value_hhad'] = {
                        'goal_line': gl,
                        'model_prob': {'home': round(hw * 100, 1), 'draw': round(hd * 100, 1), 'away': round(ha * 100, 1)},
                        'analysis': engine.analyze_value(
                            {'home': hw, 'draw': hd, 'away': ha},
                            {'h': hhad['h'], 'd': hhad['d'], 'a': hhad['a']})
                    }
                    if p['value_hhad']['analysis'].get('signal') in ('value', 'strong'):
                        handicap_count += 1
                # 比分矩阵用完即删（避免看板数据膨胀）
                p.pop('score_probs', None)

    # 2.6 记录预测日志（供赛果回测）
    log_path = os.path.join(args.data_dir, 'prediction_log.json')
    plog = {'records': {}}
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                plog = json.load(f)
        except (json.JSONDecodeError, OSError):
            plog = {'records': {}}
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    logged = 0
    for p in predictions:
        if 'error' in p or 'value' not in p:
            continue
        v = p['value']
        key = f"{p['date']}|{p['league']}|{p['home']}|{p['away']}"
        rec = plog.setdefault('records', {}).get(key, {})
        odds_for_dir = None
        if p.get('odds'):
            k = {'home': 'h', 'draw': 'd', 'away': 'a'}[v.get('best', 'home')]
            odds_for_dir = p['odds'].get(k)
        rec.update({
            'date': p['date'], 'league': p['league'], 'home': p['home'], 'away': p['away'],
            'model_prob': p['prob'],
            'market_prob': v.get('market_prob'),
            'direction': v.get('best'),
            'odds': odds_for_dir,
            'edge': v.get('best_edge'),
            'ev': (v.get('ev') or {}).get(v.get('best')),
            'kelly': (v.get('kelly') or {}).get(v.get('best')),
            'signal': v.get('signal'),
            'updated': now_str,
            'settled': rec.get('settled', False)
        })
        plog['records'][key] = rec
        logged += 1
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(plog, f, ensure_ascii=False, indent=2)

    # 3. 组装看板数据
    bt = None
    bt_path = os.path.join(args.data_dir, 'backtest.json')
    if os.path.exists(bt_path):
        try:
            with open(bt_path, 'r', encoding='utf-8') as f:
                bt = json.load(f)
        except (json.JSONDecodeError, OSError):
            bt = None
    data = {
        'meta': {
            'season': meta.get('season', ''),
            'round': meta.get('round', ''),
            'generated_at': meta.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M')),
            'source': 'sample' if meta.get('_sample', True) else 'live',
            'note': meta.get('note', '')
        },
        'teams': engine.teams,
        'leagues': engine.leagues,
        'predictions': predictions,
        'backtest': bt
    }

    # 4. 渲染模板
    with open(args.template, 'r', encoding='utf-8') as f:
        html = f.read()
    payload = json.dumps(data, ensure_ascii=False, indent=None)
    html = html.replace('__DATA__', payload)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(html)

    # 5. 汇总输出
    print(f"✅ 预测完成: {len(valid)} 场比赛 / 失败 {len(errors)} 场")
    print(f"   数据源: {meta.get('season','')} {meta.get('round','')}")
    print(f"   已加载 {len(engine.leagues)} 联赛 / {n_teams} 球队")
    if odds_loaded:
        print(f"   🎯 竞彩赔率匹配: {odds_loaded} 场 | 胜平负价值信号: {value_count} 场 | 让球价值信号: {handicap_count} 场")
        print(f"   📝 预测日志已记录: {logged} 条（供赛果回测）")
    else:
        print(f"   💡 未匹配到竞彩赔率（可先运行 python scripts/fetch_odds.py）")
    for e in errors:
        print(f"   ⚠ {e['league']} {e['home']} vs {e['away']}: {e['error']}")
    print(f"   看板已生成: {os.path.abspath(args.out)}")


if __name__ == '__main__':
    main()
