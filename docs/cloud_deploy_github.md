# 云端自动更新部署指南（GitHub Actions + GitHub Pages）

> 目标：**不依赖本机开机**，每天 10:00 北京时间在 GitHub 云端自动拉取数据 →
> 预测 → 更新网页，网页链接永久固定。
>
> 成本：完全免费（GitHub 私有仓库免费层每月 2000 分钟 Actions 额度，每日 1 次约 10 分钟）。

## 原理

```
GitHub Actions (云端, 定时 10:00)                  GitHub Pages (云端托管)
┌────────────────────────────────────┐            ┌─────────────────────┐
│ cron 触发 → 拉竞彩赔率/赛程/积分榜  │            │ 固定链接:            │
│ → Elo校准 → 结算/回测 → 预测+价值   │  push      │ https://<用户名>.    │
│ → 生成 index.html → 发布 gh-pages  │──────────▶ │   github.io/<仓库名>/ │
└────────────────────────────────────┘            └─────────────────────┘
```

## 一键部署步骤（约 10 分钟）

### 1. 注册 GitHub 并创建仓库
- 注册 https://github.com （免费）
- New repository → 名称随意（如 `football-predictor`）→ Private 或 Public 均可 → 不要勾选 README

### 2. 把项目推送到仓库（二选一）

**方式 A：用 Git 命令（推荐）**
```bash
cd C:\Users\ASUS\WorkBuddy\2026-08-29-20-32-59\top5-predictor
git init
git add .
git commit -m "v3.1 足球预测与价值投注系统"
git branch -M main
git remote add origin https://github.com/<你的用户名>/football-predictor.git
git push -u origin main
```

**方式 B：请 WorkBuddy 代推**（告诉我你的 GitHub 用户名，我用 PAT 帮你推）

### 3. 配置密钥（关键，不会泄露）
仓库页面 → **Settings → Secrets and variables → Actions → New repository secret**
- Name: `FOOTBALL_DATA_KEY`
- Value: `f1310a00ba7b4e8fb5d240cdcd10b38a`（你 football-data.org 的 Token）

### 4. 开启 GitHub Pages
仓库页面 → **Settings → Pages**
- Source 选 **GitHub Actions**（或 Branch: `gh-pages`）

### 5. 触发首次运行并验证
- 仓库 **Actions** 页 → 左侧「每日更新发布」→ **Run workflow**（手动触发一次）
- 首次运行约 2-3 分钟（含云端拉取+预测）
- 完成后访问：`https://<你的用户名>.github.io/football-predictor/`

### 6. 之后每天自动运行
- 每天 **10:00 北京时间** 云端自动更新，链接不变
- 运行记录/日志在 Actions 页查看（Run 详情里有完整输出）

## 手动触发 / 临时更新

Actions 页 → 「每日更新发布」→ Run workflow → 可选填 `days`（默认 7）

## 常见问题

| 问题 | 处理 |
|------|------|
| 竞彩赔率拉取失败（海外访问国内接口超时） | 非致命步骤，workflow 会继续，仅当天的价值分析可能缺赔率；可稍后手动 Run |
| Actions 定时有几分钟延迟 | 正常（GitHub 排队），设置 10:00 一般 10:05 左右跑 |
| 想换时间 | 改 `.github/workflows/daily.yml` 里 cron（UTC 时间，北京=UTC+8，如 10:00 北京= `0 2 * * *`） |
| 想保留旧 CloudStudio 链接 | 不受影响；也可在「设置-数据管理-我发布的应用」下线旧网页 |

## 备选方案（国内访问更快的付费/进阶路线）

- **腾讯云**：SCF 云函数定时（每日 cron）+ COS 静态网站托管 → 国内访问快、链接固定，需云账号与少量配置
- **Cloudflare Pages + Cron**：Pages 免费 500 次构建/月 + Workers Cron，但需要把 Python 流程改写为 Node/无服务器函数
- 需要时我可以帮你做其中任一方案。

## 相关文件

| 文件 | 作用 |
|------|------|
| `.github/workflows/daily.yml` | 定时任务定义（10:00 北京 + 手动触发） |
| `scripts/ci_run.py` | 云端执行入口（赔率→赛程→校准→结算→回测→预测→deploy） |
| `.gitignore` | 排除 .env/生成物（Token 不入库） |
