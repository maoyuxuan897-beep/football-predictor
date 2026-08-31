# 云端自动更新部署指南（GitHub Actions + GitHub Pages）

> 目标：**不依赖本机开机**，每天 00:30 北京时间在 GitHub 云端自动拉取数据 →
> 预测 → 更新网页，网页链接永久固定。
>
> 成本：完全免费（公开仓库 Actions 免费）。

## ✅ 已部署完成（2026-08-30）

- 仓库：https://github.com/maoyuxuan897-beep/football-predictor （公开）
- 固定网页：**https://maoyuxuan897-beep.github.io/football-predictor/**
- 每日 **00:30 北京时间** 自动更新（本地 00:00 拉取推送赔率后）；Actions 页可手动 Run
- Secret `FOOTBALL_DATA_KEY` 已配置

## ⚠️ 关键机制：竞彩赔率的"本地推送"链路

GitHub 云端服务器在海外，访问中国体彩竞彩接口会被拦截（HTTP 567）。
因此竞彩赔率由**本机 00:00 拉取后推送到仓库**，云端自动使用：

```
本机（每日 00:00 计划任务）         GitHub 云端（每日 10:00 Actions）
fetch_odds.py 拉取竞彩赔率    →     push 到 data/odds.json（push_odds_to_github.py）
                                        ↓
                                   ci_run.py 用仓库中的赔率做价值分析 → 发布网页
```

- 本机推送脚本：`scripts/push_odds_to_github.py`（用 `.env` 中 `GH_TOKEN`）
- 云端已容错：赔率缺失时只出预测、跳过价值分析，不阻断发布
- 若本机连续几天未开机，网页的价值分析会使用仓库里最近一次推送的赔率（会提示数据时间）

## 手动触发 / 临时更新

Actions 页 → 「每日更新发布」→ Run workflow

## 相关文件

| 文件 | 作用 |
|------|------|
| `.github/workflows/daily.yml` | 定时任务定义（10:00 北京 + 手动触发） |
| `scripts/ci_run.py` | 云端执行入口（赔率→赛程→校准→结算→回测→预测→deploy） |
| `scripts/push_odds_to_github.py` | 本机推送竞彩赔率到仓库（供云端价值分析） |
| `.gitignore` | 排除 .env/生成物（Token 不入库） |
