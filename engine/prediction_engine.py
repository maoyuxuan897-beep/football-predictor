# -*- coding: utf-8 -*-
"""
五大联赛预测引擎 v2.0
模块: 联赛参数化 Elo + 泊松分布 + 进球分布 + 确定性指标

基于 football-match-analysis skill 的 prediction_engine.py 扩展:
- 联赛参数化: 各联赛场均进球、主场优势、平局下限不同
- 俱乐部口径: Elo 评级 + 场均进球/失球
- 输出: 胜平负概率、xG、最可能比分、总进球分布、推荐方向
"""

import math
import json
import os
from typing import Dict, List, Tuple

ELO_WEIGHT = 0.30
POISSON_WEIGHT = 0.70
ELO_HOME_BONUS = 60          # Elo 层面的主场加成（约合 60 分）
MAX_GOALS = 8                # 泊松矩阵扫描上限
XG_PER_SHOT = 0.11           # xG 转化率（每脚射门的期望进球），用于射门数反推
SHOT_ON_RATE = 0.36          # 射正率（射正/射门）
CARD_ATTACK_DAMP = 0.35      # 强队黄牌抑制系数
CORNER_DEF_DAMP = 0.40       # 角球防守抑制系数


class Top5PredictionEngine:
    """五大联赛预测引擎"""

    def __init__(self, data_dir: str = None):
        self.leagues = {}
        self.teams = {}       # {league: {team: stats}}
        if data_dir:
            self.load_data(data_dir)

    def load_data(self, data_dir: str):
        with open(os.path.join(data_dir, 'leagues.json'), 'r', encoding='utf-8') as f:
            self.leagues = json.load(f)
        with open(os.path.join(data_dir, 'teams.json'), 'r', encoding='utf-8') as f:
            self.teams = json.load(f)

    # ---------- Elo ----------
    @staticmethod
    def elo_expected(elo_a: float, elo_b: float) -> float:
        return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

    # ---------- 泊松 ----------
    @staticmethod
    def poisson_prob(lam: float, k: int) -> float:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    def expected_goals(self, league: str, home: str, away: str) -> Tuple[float, float]:
        """联赛参数化 xG: 主队 xG = 联赛均值*主攻*客防 + 主场优势"""
        cfg = self.leagues[league]
        league_avg = cfg['avg_goals']
        home_adv = cfg['home_advantage']

        th = self.teams[league][home]
        ta = self.teams[league][away]

        attack_h = th['avg_goals'] / league_avg
        defense_a = ta['avg_conceded'] / league_avg
        attack_a = ta['avg_goals'] / league_avg
        defense_h = th['avg_conceded'] / league_avg

        xg_home = (league_avg + home_adv) * attack_h * defense_a
        xg_away = league_avg * attack_a * defense_h
        return round(xg_home, 2), round(xg_away, 2)

    def poisson_matrix(self, xg_a: float, xg_b: float):
        """泊松比分矩阵 → 胜平负 + 比分概率 + 总进球分布"""
        win_a = draw = win_b = 0.0
        score_probs = {}
        goals_dist = {i: 0.0 for i in range(MAX_GOALS + 1)}
        goals_ge6 = 0.0

        for ga in range(MAX_GOALS + 1):
            for gb in range(MAX_GOALS + 1):
                p = self.poisson_prob(xg_a, ga) * self.poisson_prob(xg_b, gb)
                score_probs[f"{ga}-{gb}"] = p
                if ga > gb:
                    win_a += p
                elif ga == gb:
                    draw += p
                else:
                    win_b += p
                total = ga + gb
                if total <= MAX_GOALS:
                    goals_dist[total] += p
                else:
                    goals_ge6 += p
        goals_dist["6+"] = goals_ge6
        return {
            'win_a': win_a, 'draw': draw, 'win_b': win_b,
            'score_probs': score_probs,
            'goals_dist': goals_dist
        }

    def stat_expectations(self, league: str, home: str, away: str,
                          xg_home: float, xg_away: float, elo_h: float, elo_a: float) -> Dict:
        """统计期望模型: 射门/射正/角球/黄牌/控球率（基于攻防系数与 xG 反推）"""
        cfg = self.leagues[league]
        s = cfg.get('stats', {'shots': 13, 'shots_on': 4.7, 'corners': 5.3, 'cards': 3.5, 'possession': 50})
        league_avg = cfg['avg_goals']
        th = self.teams[league][home]
        ta = self.teams[league][away]
        attack_h = th['avg_goals'] / league_avg
        attack_a = ta['avg_goals'] / league_avg
        defense_a = ta['avg_conceded'] / league_avg
        defense_h = th['avg_conceded'] / league_avg

        # 射门: 攻防系数驱动（主场仅轻量加成，避免 xG 反推虚高）
        home_boost = 1 + cfg['home_advantage'] * 0.2
        shots_h = s['shots'] * (0.85 + 0.15 * attack_h) * (1.05 - 0.10 * defense_a) * home_boost
        shots_a = s['shots'] * (0.85 + 0.15 * attack_a) * (1.05 - 0.10 * defense_h)
        shots_h = min(max(shots_h, 6), 24)
        shots_a = min(max(shots_a, 6), 24)
        # 射正
        son_h = shots_h * SHOT_ON_RATE
        son_a = shots_a * SHOT_ON_RATE
        # 角球: 攻击压力驱动（0.7+0.3×攻系），对手防守轻微抑制
        corners_h = s['corners'] * (0.7 + 0.3 * attack_h) * (1 + (1 - defense_a) * 0.12)
        corners_a = s['corners'] * (0.7 + 0.3 * attack_a) * (1 + (1 - defense_h) * 0.12)
        corners_h = min(max(corners_h, 2.5), 9.0)
        corners_a = min(max(corners_a, 2.5), 9.0)
        # 黄牌: 强队(高攻)控制力强犯规少
        cards_h = s['cards'] * (1.15 - attack_h * 0.12)
        cards_a = s['cards'] * (1.15 - attack_a * 0.12)
        cards_h = min(max(cards_h, 1.2), 3.5)
        cards_a = min(max(cards_a, 1.2), 3.5)
        # 控球率: Elo 差驱动 + 主场微调，限幅 35-65
        poss_h = 50 + (elo_h - elo_a) / 30 + 2
        poss_h = min(max(poss_h, 35), 65)

        def r2(v):
            return round(v, 1)

        return {
            'shots': {'home': r2(shots_h), 'away': r2(shots_a)},
            'shots_on': {'home': r2(son_h), 'away': r2(son_a)},
            'corners': {'home': r2(corners_h), 'away': r2(corners_a)},
            'cards': {'home': r2(cards_h), 'away': r2(cards_a)},
            'possession': {'home': round(poss_h, 0), 'away': round(100 - poss_h, 0)}
        }

    def markets(self, pm: Dict, xg_home: float, xg_away: float, final_h: float,
                final_d: float, final_a: float) -> Dict:
        """衍生市场维度: 大小球 / 双方进球 / 双胜彩 / 让球盘"""
        gd = pm['goals_dist']  # 总进球分布 0..MAX_GOALS, 6+
        def p_over(n):
            s = 0.0
            for k, v in gd.items():
                if isinstance(k, int) and k > n:
                    s += v
            return s
        over25 = p_over(2)
        over15 = p_over(1)
        over35 = p_over(3)
        p0_h = math.exp(-xg_home)
        p0_a = math.exp(-xg_away)
        btts = (1 - p0_h) * (1 - p0_a)

        # 净胜球分布（用于让球盘）
        margin = {}
        for (score, p) in pm['score_probs'].items():
            gh, ga = map(int, score.split('-'))
            m = gh - ga
            margin[m] = margin.get(m, 0) + p
        # 主让1球: 赢盘=净胜>=2, 走水=净胜=1, 输盘=净胜<=0
        h1_win = sum(v for m, v in margin.items() if m >= 2)
        h1_push = margin.get(1, 0)
        h1_lose = sum(v for m, v in margin.items() if m <= 0)
        # 客让1球: 客净胜>=2 即主净胜<=-2
        a1_win = sum(v for m, v in margin.items() if m <= -2)
        a1_push = margin.get(-1, 0)
        a1_lose = sum(v for m, v in margin.items() if m >= 0)

        def pc(v):
            return round(v * 100, 1)

        return {
            'over_under': {'over25': pc(over25), 'under25': pc(1 - over25),
                           'over15': pc(over15), 'over35': pc(over35)},
            'btts': {'yes': pc(btts), 'no': pc(1 - btts)},
            'dbl_chance': {'1X': pc(final_h + final_d), 'X2': pc(final_d + final_a), '12': pc(final_h + final_a)},
            'asian': {
                'home_-1': {'win': pc(h1_win), 'push': pc(h1_push), 'lose': pc(h1_lose)},
                'away_+1': {'win': pc(a1_win), 'push': pc(a1_push), 'lose': pc(a1_lose)}
            }
        }

    def analyze_value(self, model_prob: Dict, odds: Dict,
                      threshold: float = 3.0, strong_threshold: float = 5.0) -> Dict:
        """价值投注分析: 模型概率 vs 市场赔率隐含概率

        model_prob: {'home': 0.414, 'draw': 0.281, 'away': 0.305}  (0-1)
        odds:       {'h': 4.85, 'd': 4.30, 'a': 1.45}
        返回 edge(百分点)、半Kelly仓位(百分点)、价值信号与建议
        """
        keys = ['home', 'draw', 'away']
        ok = {'home': odds.get('h'), 'draw': odds.get('d'), 'away': odds.get('a')}

        # 市场隐含概率（去水）
        impl = {}
        valid = True
        for k in keys:
            o = ok.get(k)
            if not o or o <= 1:
                valid = False
                break
            impl[k] = 1.0 / o
        if not valid:
            return {'error': '赔率数据不完整'}

        s = sum(impl.values())
        market = {k: v / s for k, v in impl.items()}
        vig = s - 1.0  # 抽水率

        # Edge = 模型概率 - 市场概率（百分点）
        edges = {k: round((model_prob[k] - market[k]) * 100, 1) for k in keys}

        # 半 Kelly: f = (p*o - 1)/(o - 1)，×0.5，下限 0；Kelly>0 ⟺ 期望值 p×odds>1
        kelly = {}
        ev = {}
        for k in keys:
            p, o = model_prob[k], ok[k]
            f = (p * o - 1) / (o - 1) if o > 1 else 0
            kelly[k] = round(max(0.0, f) * 50.0, 1)  # 半Kelly（%）
            ev[k] = round((p * o - 1) * 100, 1)  # 期望收益率（%）

        # 价值信号：edge 达标 且 Kelly>0（正期望）才有效；Kelly=0 归为"观察"
        best = max(keys, key=lambda k: edges[k])
        be = edges[best]
        mp = round(model_prob[best] * 100, 1)
        if be >= strong_threshold and kelly[best] > 0:
            signal, level = 'strong', '强价值'
        elif be >= threshold and kelly[best] > 0:
            signal, level = 'value', '价值'
        elif be >= threshold:
            signal, level = 'watch', '观察'
        else:
            signal, level = 'none', '无'

        # 建议文案（一句话可判定）
        name = {'home': '主胜', 'draw': '平局', 'away': '客胜'}[best]
        if signal == 'none':
            suggestion = "模型与市场基本一致，无显著价值机会"
        elif signal == 'watch':
            suggestion = (f"模型认为{name}概率 {mp}% 高于市场隐含 {round(market[best]*100,1)}%"
                          f"（edge {be}%），但赔率不足正期望，建议观望")
        else:
            suggestion = (f"模型认为{name}概率 {mp}% 高于市场隐含 {round(market[best]*100,1)}%，"
                          f"edge {be}%、期望收益 {ev[best]}%，存在{level}机会")

        return {
            'market_prob': {k: round(v * 100, 1) for k, v in market.items()},
            'edge': edges,
            'kelly': kelly,
            'ev': ev,
            'vig': round(vig * 100, 1),
            'best': best,
            'best_edge': be,
            'signal': signal,
            'level': level,
            'suggestion': suggestion
        }

    @staticmethod
    def handicap_probs(score_probs: Dict, goal_line: int) -> Tuple[float, float, float]:
        """让球胜平负概率。goal_line 为主队让球数：+1=主队受让1球，-1=主队让1球，0=平手盘
        返回 (让球后主胜, 让球后平, 让球后客胜) 0-1
        """
        hw = hd = ha = 0.0
        for score, p in score_probs.items():
            gh, ga = map(int, score.split('-'))
            adj = gh + goal_line
            if adj > ga:
                hw += p
            elif adj == ga:
                hd += p
            else:
                ha += p
        return hw, hd, ha

    def predict(self, league: str, home: str, away: str,
                corrections: Dict = None) -> Dict:
        """单场预测主流程"""
        corrections = corrections or {}
        cfg = self.leagues[league]

        # Elo
        elo_h = self.teams[league][home]['elo'] + ELO_HOME_BONUS
        elo_a = self.teams[league][away]['elo']
        elo_exp_h = self.elo_expected(elo_h, elo_a)

        # 泊松
        xg_h, xg_a = self.expected_goals(league, home, away)
        pm = self.poisson_matrix(xg_h, xg_a)

        # 合成: Elo 30% + 泊松 70%
        comb_h = elo_exp_h * ELO_WEIGHT + pm['win_a'] * POISSON_WEIGHT
        comb_d = pm['draw'] * POISSON_WEIGHT + (1 - abs(elo_exp_h - 0.5)) * cfg['draw_floor']
        comb_a = (1 - elo_exp_h) * ELO_WEIGHT + pm['win_b'] * POISSON_WEIGHT
        tot = comb_h + comb_d + comb_a
        comb_h, comb_d, comb_a = comb_h / tot, comb_d / tot, comb_a / tot

        # 修正因子（伤病/轮换等外部输入，单位：概率点）
        f_h = comb_h + corrections.get('home', 0)
        f_d = comb_d + corrections.get('draw', 0)
        f_a = comb_a + corrections.get('away', 0)
        tot2 = f_h + f_d + f_a
        final_h, final_d, final_a = f_h / tot2, f_d / tot2, f_a / tot2

        # 最可能比分 TOP6
        top_scores = sorted(pm['score_probs'].items(), key=lambda x: x[1], reverse=True)[:6]
        top_scores = [(s, round(p * 100, 1)) for s, p in top_scores]

        # 总进球分布（0,1,2,3,4,5,6+）
        gd = {str(k): round(v * 100, 1) for k, v in pm['goals_dist'].items()}

        # 确定性指标: 最大概率 - 次大概率
        probs = [final_h, final_d, final_a]
        probs_sorted = sorted(probs, reverse=True)
        confidence = round((probs_sorted[0] - probs_sorted[1]) * 100, 1)

        # 推荐方向
        if final_h >= max(final_d, final_a):
            direction = home
        elif final_a >= max(final_h, final_d):
            direction = away
        else:
            direction = "平局"

        # 统计期望 + 衍生市场
        stats = self.stat_expectations(league, home, away, xg_h, xg_a,
                                       elo_h - ELO_HOME_BONUS, elo_a)
        mkts = self.markets(pm, xg_h, xg_a, final_h, final_d, final_a)

        return {
            'league': league,
            'home': home, 'away': away,
            'elo': {'home': elo_h - ELO_HOME_BONUS, 'away': elo_a,
                    'gap': round(abs(elo_h - ELO_HOME_BONUS - elo_a), 0)},
            'xg': {'home': xg_h, 'away': xg_a,
                   'total': round(xg_h + xg_a, 2)},
            'prob': {
                'home': round(final_h * 100, 1),
                'draw': round(final_d * 100, 1),
                'away': round(final_a * 100, 1)
            },
            'stats': stats,
            'markets': mkts,
            'score_probs': pm['score_probs'],
            'top_scores': top_scores,
            'goals_dist': gd,
            'confidence': confidence,
            'direction': direction,
            'corrections': corrections
        }

    def batch_predict(self, fixtures: List[Dict]) -> List[Dict]:
        """批量预测赛程"""
        results = []
        for fx in fixtures:
            try:
                r = self.predict(fx['league'], fx['home'], fx['away'])
                r['date'] = fx['date']
                r['time'] = fx['time']
                r['round'] = fx.get('round', '')
                results.append(r)
            except KeyError as e:
                # 数据源可能包含未收录球队，跳过并记录
                results.append({
                    'league': fx['league'], 'home': fx['home'], 'away': fx['away'],
                    'date': fx['date'], 'time': fx['time'], 'round': fx.get('round', ''),
                    'error': f'数据缺失: {e}'
                })
        return results


if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    engine = Top5PredictionEngine(data_dir=data_dir)
    n_teams = sum(len(v) for v in engine.teams.values())
    print(f"已加载 {len(engine.leagues)} 个联赛 / {n_teams} 支球队")

    # 自测
    test = engine.predict("英超", "曼城", "阿森纳")
    print(f"\n测试: 曼城 vs 阿森纳")
    print(f"xG: {test['xg']}")
    print(f"胜平负: 主{test['prob']['home']}% 平{test['prob']['draw']}% 客{test['prob']['away']}%")
    print(f"最可能比分: {test['top_scores'][:3]}")
    print(f"总进球分布: {test['goals_dist']}")
