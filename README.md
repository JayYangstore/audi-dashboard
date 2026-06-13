# 上汽奥迪南区 · 月度项目监控看板

> 自动抓取本页数据 → 解析项目执行日期 → 钉钉机器人主动提醒

## 📊 看板说明

- 数据源：`/Users/jay/Desktop/5月计划表看板/优化版/【月度计划表】潜客数据0611-V6.xlsm`
- 推送渠道：钉钉群机器人
- 推送规则：
  - **🔥 今日执行中** — 项目 `start ≤ today ≤ end`
  - **⏰ 未来 3 天内开始** — `today < start ≤ today+3`
  - 静默规则：无内容时默认不推送

## 🤖 自动提醒（GitHub Actions）

由 `.github/workflows/daily-reminder.yml` 驱动，**北京时间每天 09:00** 触发。

### 配置 GitHub Secrets

进入 `Settings → Secrets and variables → Actions → New repository secret`，添加：

| 名称 | 必填 | 说明 |
|---|---|---|
| `DINGTALK_WEBHOOK` | ✅ | 钉钉机器人 webhook 完整 URL |
| `DINGTALK_SECRET` | ❌ | 加签密钥（如开启加签） |
| `DINGTALK_KEYWORD` | ❌ | 钉钉机器人关键词，默认 `月度看板` |
| `DASHBOARD_URL` | ❌ | 看板 URL，默认本仓库 Pages |

## 🛠 本地调试

```bash
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx"
export DINGTALK_KEYWORD="月度看板"
python scripts/dashboard_monitor.py
```

## 📁 目录结构

```
audi-dashboard/
├── index.html                          # 看板页面
├── scripts/
│   ├── dashboard_monitor.py            # 监控主脚本
│   └── requirements.txt                # 依赖（无）
├── .github/workflows/
│   └── daily-reminder.yml              # GitHub Actions 定时
└── README.md
```
