# -*- coding: utf-8 -*-
"""
五大联赛预测系统 · 一键自动更新
================================
流程: 拉取真实数据(football-data.org) → 预测计算 → 生成可视化看板

用法:
  python scripts/auto_update.py               # 完整流程（需已配置 FOOTBALL_DATA_KEY）
  python scripts/auto_update.py --no-fetch    # 跳过拉取，只用本地数据刷新看板
  python scripts/auto_update.py --key XXX     # 临时指定 key

该脚本适合配置为 Windows 计划任务 / WorkBuddy 每日自动化，实现"每天自动更新"。
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def load_key():
    """读取 API Key: 环境变量 > 项目 .env 文件（保证计划任务场景可用）"""
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


def setup_logging():
    """输出同时写入 logs/auto_update.log（计划任务无控制台时仍可留痕）"""
    log_path = os.path.join(BASE, 'logs', 'auto_update.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                try:
                    s.write(data)
                    s.flush()
                except Exception:
                    pass

        def flush(self):
            for s in self.streams:
                try:
                    s.flush()
                except Exception:
                    pass

    f = open(log_path, 'a', encoding='utf-8')
    sys.stdout = Tee(sys.__stdout__, f)
    sys.stderr = Tee(sys.__stderr__, f)
    return f


def run(script, extra=None, fatal=True):
    cmd = [PY, os.path.join(BASE, 'scripts', script)]
    if extra:
        cmd += extra
    print(f"\n▶ 执行: {' '.join(cmd)}")
    # 强制子进程 UTF-8 输出 + capture 转发，确保日志完整
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env, timeout=240)
    if r.stdout:
        print(r.stdout, end='')
    if r.stderr:
        print(r.stderr, end='', file=sys.stderr)
    if r.returncode != 0:
        print(f"⚠ 步骤失败: {script} (exit={r.returncode})")
        if fatal:
            sys.exit(r.returncode)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', default='')
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--no-fetch', action='store_true', help='跳过拉取，仅用本地数据刷新')
    args = ap.parse_args()

    log_f = setup_logging()
    t0 = datetime.now()
    print(f"=== 五大联赛预测系统自动更新 @ {t0.strftime('%Y-%m-%d %H:%M:%S')} ===")

    # 1) 竞彩赔率（免费，无 key）→ 推送到 GitHub 供云端价值分析
    run('fetch_odds.py')
    run('push_odds_to_github.py', fatal=False) if os.path.exists(os.path.join(BASE, 'scripts', 'push_odds_to_github.py')) else None

    # 2) 真实赛程 + 积分榜
    key = args.key or load_key()
    if not args.no_fetch:
        if not key:
            print("⚠ 未检测到 FOOTBALL_DATA_KEY（环境变量/.env），跳过赛程拉取（仅用本地数据）")
        else:
            run('fetch_footballdata.py', ['--key', key, '--days', str(args.days)])

    # 3) 赔率反推 Elo 校准（提升模型贴近市场）
    run('update_elo_from_odds.py', ['--rounds', '3'])

    # 4) 赛果结算 + 回测（有 key 时结算；回测无 key 依赖）
    if not args.no_fetch and key:
        run('settle_results.py', ['--key', key])
    run('backtest.py')

    # 5) 预测 + 价值分析 → 看板
    run('run_prediction.py')

    el = (datetime.now() - t0).total_seconds()
    print(f"\n✅ 更新完成，耗时 {el:.1f}s")
    print(f"   看板: {os.path.join(BASE, 'dashboard', 'index.html')}")
    log_f.close()


if __name__ == '__main__':
    main()
