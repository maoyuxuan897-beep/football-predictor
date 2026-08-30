# 欧洲足球预测分析系统（欧冠 + 英超 + 西甲 + 德甲）

> **v3.1（已固化）** · 2026-08-29 · 真实赛程/赔率自动更新 + 预测 + 统计期望 + 价值投注（胜平负+让球）+ 资金规划 + 赛果回测
> 投注建议限定**近 3 天**场次（总览页自动过滤）

基于 **Elo 评级 + 联赛参数化泊松分布 + 价值投注分析** 的个人预测系统，
覆盖欧冠/英超/西甲/德甲，输出胜平负概率、xG、统计期望、市场维度，
并以**中国体彩竞彩赔率**为市场基准，计算 edge/期望/Kelly，发现价值机会。

## 快速开始

```bash
# 1. 一键更新（竞彩赔率 → 赛程 → Elo校准 → 预测 → 价值分析 → 看板）
python scripts/auto_update.py --days 7

# 2. 打开看板
dashboard/index.html   # 双击即可（自包含单文件，无外部依赖）
```

## 系统结构

```
top5-predictor/
├── data/
│   ├── leagues.json          # 联赛参数: 场均进球 / 主场优势 / 平局下限 / 统计基准
│   ├── teams.json            # 球队表: Elo / 场均进球 / 场均失球（随数据源自动扩展）
│   ├── fixtures.json         # 赛程（含 _meta 元信息与数据源标注）
│   ├── odds.json             # 竞彩赔率（fetch_odds.py 生成，供价值分析）
│   └── team_aliases.json     # 数据源队名 -> 系统中文名 映射（tla/english/juhe 三段）
├── engine/
│   └── prediction_engine.py  # 预测引擎: Elo+泊松+统计期望+市场维度+价值分析
├── scripts/
│   ├── run_prediction.py     # 主流程: 读数据 → 预测+价值 → 生成看板
│   ├── fetch_footballdata.py # 主数据源: football-data.org 拉取赛程+积分榜
│   ├── fetch_odds.py         # 竞彩赔率拉取（免费无 key，胜平负+让球）
│   ├── update_elo_from_odds.py # 赔率反推 Elo 校准（迭代 3 轮）
│   ├── fetch_thesportsdb.py  # 零门槛备选: TheSportsDB（无需 key）
│   ├── fetch_juhe.py         # 备选: juhe API
│   ├── auto_update.py        # 一键自动更新: 赔率→赛程→校准→预测→看板
│   └── setup_scheduled_task.bat # Windows 每日计划任务注册脚本
├── docs/
│   └── prediction_method.md  # 完整预测方案（公式/校准/价值模型/参数）
└── dashboard/
    ├── template.html         # 看板模板（可自行改样式）
    └── index.html            # 生成的自包含看板（含价值投注页签）
```

## 模型方法

| 模块 | 方法 |
|------|------|
| 胜平负概率 | Elo 期望（含主场 +60）权重 30% + 泊松矩阵权重 70%，平局下限兜底 |
| xG 期望 | `xG = 联赛场均 × 主队攻系 × 客队防系`，主队叠加联赛主场优势 |
| 最可能比分 | 泊松二维矩阵扫描 0-8 球，取概率 TOP4 |
| 总进球分布 | 泊松矩阵按总进球聚合，输出 0/1/2/3/4/5/6+ 概率 |
| 统计期望 | 射门/射正/角球/黄牌/控球率（攻防系数 × 联赛基准） |
| 市场维度 | 大小球 1.5/2.5/3.5、BTTS、双胜彩、让球盘 |
| **价值投注** | 模型概率 vs 竞彩去水概率 → edge / EV / 半Kelly / 信号分级（胜平负 + 让球双维度） |
| **赛果回测** | 预测日志 → 结算比分 → 命中率统计 + 100 元本金模拟投注收益 |

## 接入真实数据（自动更新）

### 数据源（2026-08 调研结论）

| 数据源 | 费用 | 用途 |
|--------|------|------|
| **football-data.org** ⭐ | 免费（永久） | 欧冠/英超/西甲/德甲赛程+积分榜（10次/分钟） |
| **中国体彩竞彩** ⭐ | 免费（无需key） | 官方赔率（胜平负/让球），价值投注市场基准 |
| TheSportsDB | 免费 | 备用赛程源（免费接口限 5 条/请求） |
| juhe / API-Football | 免费 | 备选（juhe 缺西甲；API-Football 额度紧） |

### 一键自动更新（含赔率 + 价值分析）

```bash
python scripts/auto_update.py --days 7
# 流程: 竞彩赔率 → football-data 赛程+积分榜 → 赔率反推 Elo → 预测+价值 → 看板
```

**Windows 每日定时**：双击 `scripts/setup_scheduled_task.bat` 注册每日 09:30 任务。
**WorkBuddy 自动化**：配置每日任务运行上述命令并汇报价值信号。

### 单独操作

```bash
python scripts/fetch_odds.py                 # 拉取竞彩赔率 → data/odds.json
python scripts/update_elo_from_odds.py --rounds 3   # 赔率反推 Elo 校准
python scripts/fetch_footballdata.py --days 7       # 拉取赛程+积分榜
python scripts/run_prediction.py                    # 预测+价值 → 看板
```

### 方式一：football-data.org（推荐，完整赛程 + 积分榜 + Elo 校准）

1. 免费注册：<https://www.football-data.org/> → 登录后在个人页生成 Token（1 分钟）
2. 配置并拉取：
   ```bash
   export FOOTBALL_DATA_KEY=你的Token        # 永久: setx FOOTBALL_DATA_KEY "你的Token"
   python scripts/fetch_footballdata.py --days 7   # 拉取欧冠/英超/西甲/德甲赛程+积分榜
   python scripts/run_prediction.py                # 生成看板
   ```
   > 积分榜会自动校准新球队 Elo（排名→Elo），并扩展缺失球队。

### 方式二：TheSportsDB（零门槛，无需 key）

```bash
python scripts/fetch_thesportsdb.py --days 7   # 拉取真实赛程（免费接口覆盖有限）
python scripts/run_prediction.py
```

### 方式三：一键自动更新（配置为每日任务）

```bash
# 完整流程: 拉取真实数据 → 预测 → 生成看板
python scripts/auto_update.py --days 7
```

**Windows 每日定时**：双击 `scripts/setup_scheduled_task.bat` 一次，
注册每日 09:30 自动任务（拉取 → 预测 → 更新看板，日志在 `logs/auto_update.log`）。

**WorkBuddy 每日自动化**：也可在 WorkBuddy 中配置每日自动化任务，
prompt 设为「运行 `python scripts/auto_update.py --days 7` 并汇报预测要点」。

### 数据更新说明

- 赛程日期滚动：`--days 7` 拉取未来 7 天，每日任务跑一次即保持看板最新
- 队名映射：`data/team_aliases.json`（english 段=football-data/TheSportsDB，juhe 段=聚合数据），
  未收录球队自动以英文兜底并自动加入球队表，可在该文件补充映射
- 新球队实力默认联赛均值（Elo 1500），接入积分榜后按排名自动校准

## 自定义数据

- **联赛参数**：改 `data/leagues.json` 的 `avg_goals`（该联赛每队场均进球）、`home_advantage`（主场加成）
- **球队实力**：改 `data/teams.json` 的 `elo` / `avg_goals` / `avg_conceded`（可基于上赛季或当前赛季数据校准）
- **赛程**：直接编辑 `data/fixtures.json` 或由 fetch 脚本生成

## 模型局限与风险

- 泊松模型假设进球相互独立，未建模赛程密度、伤病、裁判等动态因素（可通过 corrections 手动传入）
- 预测方向仅代表统计模型观点，**不构成任何投注建议**
- 足球比赛强随机性：即使高确定性比赛（如 60%）也有约 4 成概率出现其他结果
