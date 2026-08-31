# 足球预测系统每日更新部署 · 执行记忆

## 2026-08-30（首次记录）
- 执行：`python scripts/auto_update.py --days 7` 成功，耗时 158.9s。
- 赛程：英超 15 / 西甲 14 / 德甲 11 / 欧冠 0，共 40 场；Elo 校准跳过（已有精细 Elo）；结算 5 条待结算记录无匹配（遇一次 429 限流自动重试）。
- **竞彩赔率接口本次拉取失败**（SSL: UNEXPECTED_EOF_WHILE_READING），沿用本地缓存 odds.json（当日 14:11 拉取，非过期数据）；预测正常完成。
- 当日信号：4 个 STRONG（无 VALUE）——胜平负 2（曼联vs伊普斯维奇 客胜 Edge6.6%/EV36.7%；奥萨苏纳vs赫塔菲 客胜 Edge5.6%/EV11.4%）；让球盘 2（同两场，让-1：伊普斯维奇受让 Edge20%/EV50.5%、奥萨苏纳让球胜 Edge6.9%/EV20.8%）。
- 100 元半 Kelly 资金规划：¥2.9 / ¥1.8 / ¥12.0 / ¥2.8（合计 ¥19.5，单场上限 30%）。
- 看板 dashboard/index.html → deploy/index.html（md5 一致），已部署 CloudStudio。
- 新分享链接：https://6df645b4a6084052b35f2ac65c498be2.app.workbuddy.link
- 回测参考：value 1 场 0 命中（多特蒙德 7.7 倍客胜未中），半 Kelly 100→98.8（-1.2%）。

## 备注
- 流程模板：更新 → 校验 md5 → 部署 → 汇报（链接 + 信号明细 + 资金规划）。
- 若竞彩接口连续失败需关注：fetch_odds.py 的 SSL 问题（偶发，本地缓存兜底）。
