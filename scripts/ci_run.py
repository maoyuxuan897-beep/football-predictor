# -*- coding: utf-8 -*-
"""
云端 CI 入口脚本（GitHub Actions 专用）
=======================================
在 GitHub Actions 云端定时执行：拉取竞彩赔率 → 赛程/积分榜 → Elo 校准
→ 赛果结算 → 回测 → 预测+价值 → 生成看板到 deploy/（由 workflow 发布到 Pages）

与本地 auto_update.py 的差异：
- FOOTBALL_DATA_KEY 从环境变量读取（GitHub Secret 注入，无 .env）
- 竞彩接口（国内）在海外服务器可能超时 → 非致命步骤，失败不影响主流程
- 强制 UTF-8 输出

用法（workflow 中）:
  python scripts/ci_run.py --days 7
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(script, extra=None, fatal=True, note=''):
    cmd = [PY, os.path.join(BASE, 'scripts', script)] + (extra or [])
    print(f"\n▶ [{script}] {note}".rstrip())
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env, timeout=240)
    if r.stdout:
        print(r.stdout, end='')
    if r.stderr:
        print(r.stderr, end='', file=sys.stderr)
    if r.returncode != 0:
        print(f"  ⚠ 步骤失败: {script} (exit={r.returncode})")
        if fatal:
            sys.exit(r.returncode)
    return r.returncode


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    args = ap.parse_args()

    t0 = datetime.now()
    print(f"=== 云端自动更新 @ {t0.strftime('%Y-%m-%d %H:%M:%S')} UTC ===")
    key = os.environ.get('FOOTBALL_DATA_KEY', '')

    # 1) 竞彩赔率（海外访问国内接口可能慢/失败 → 非致命）
    run('fetch_odds.py', fatal=False, note='竞彩赔率（非致命）')

    # 2) 赛程 + 积分榜（核心，必须成功）
    if not key:
        print("❌ 未配置 FOOTBALL_DATA_KEY（请在仓库 Settings→Secrets 添加）")
        sys.exit(1)
    run('fetch_footballdata.py', ['--key', key, '--days', str(args.days)], note='赛程+积分榜')

    # 3) 赔率反推 Elo 校准
    run('update_elo_from_odds.py', ['--rounds', '3'], note='Elo 校准')

    # 4) 赛果结算 + 回测
    run('settle_results.py', ['--key', key], fatal=False, note='赛果结算')
    run('backtest.py', note='回测统计')

    # 5) 预测 + 价值分析 → 看板
    run('run_prediction.py', note='预测+价值+看板')

    # 6) 复制到 deploy/（workflow 发布此目录到 Pages）
    src = os.path.join(BASE, 'dashboard', 'index.html')
    dst = os.path.join(BASE, 'deploy', 'index.html')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    print(f"\n✅ deploy/index.html 已更新（{os.path.getsize(dst)} bytes）")
    print(f"   总耗时 {(datetime.now()-t0).total_seconds():.0f}s")


if __name__ == '__main__':
    main()
