# 博后扫描系统 - 配置指南

## 系统概述

每天自动扫描多个学术招聘平台 → Claude AI筛选匹配岗位 → 自动拟邮件 → 发送到您的邮箱。

```
GitHub Actions (每日07:00 UTC)
  → 爬取5个平台职位列表
  → 去重（seen_jobs.json）
  → Claude Haiku 批量评分（0-10分）
  → Claude Sonnet 为匹配岗位拟邮件
  → Gmail 发送 HTML 摘要邮件给您
  → 更新 seen_jobs.json 提交回仓库
```

---

## 第一步：填写个人信息

编辑 `config/profile.yml`，替换所有 `[placeholder]` 内容：

```yaml
researcher:
  name: "张三"
  email: "zhangsan@pku.edu.cn"
  university: "Peking University"
  # ...
research_profile:
  representative_papers:
    - "Efficient Edge Inference via Adaptive Partitioning, MobiSys 2025"
    - "Agent-Driven Task Offloading at the Network Edge, INFOCOM 2024"
```

---

## 第二步：获取所需 API 密钥

### A. Anthropic API Key
1. 前往 https://console.anthropic.com/
2. 创建 API Key
3. 预计费用：约 **$1-2/月**（Haiku筛选 + Sonnet拟邮件）

### B. Gmail App 密码（用于发送邮件）
> 必须是 App Password，不是 Gmail 登录密码

1. 登录 Google 账号 → 安全 → 两步验证（必须先开启）
2. 搜索"应用专用密码" → 生成一个新的
3. 记录那 16 位密码（格式：`xxxx xxxx xxxx xxxx`）

---

## 第三步：在 GitHub 仓库配置 Secrets

进入 GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret

| Secret 名称 | 值 | 说明 |
|------------|-----|------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Anthropic API Key |
| `SMTP_USER` | `yourgmail@gmail.com` | 发件邮箱（Gmail） |
| `SMTP_PASSWORD` | `xxxx xxxx xxxx xxxx` | Gmail App 密码（去掉空格） |
| `NOTIFY_EMAIL` | `yourpersonal@email.com` | 接收每日摘要的邮箱 |

---

## 第四步：手动触发测试

1. GitHub 仓库 → Actions → "Daily Postdoc Scan"
2. 点击 "Run workflow" → Run workflow
3. 等待约 2-5 分钟
4. 检查您的邮箱是否收到摘要

---

## 扫描来源

| 平台 | 类型 | 覆盖范围 |
|------|------|---------|
| Academic Jobs Online | RSS | 美国/全球 CS/AI 学术职位 |
| jobs.ac.uk | RSS | 英国/欧洲学术职位 |
| EURAXESS | API | 欧洲研究职位（EU资助为主） |
| Academic Positions | HTML | 全球学术职位 |
| Nature Careers | RSS | 自然期刊旗下职位平台 |

---

## 调整相关性阈值

在 `config/profile.yml` 中修改：
```yaml
relevance_threshold: 6  # 0-10分，分数≥此值才推送
```

- 设为 **7-8**：只推送强相关岗位（推荐，减少噪音）
- 设为 **5-6**：推送较宽泛匹配（不错过机会）

---

## 常见问题

**Q: 邮件没收到？**
- 检查 Secrets 是否正确配置（SMTP_PASSWORD 不要带空格）
- 检查 Actions 运行日志是否报错
- 确认 Gmail App Password 已生效（不是账号密码）

**Q: 每天推送太多/太少？**
- 调高 `relevance_threshold` 减少噪音
- 在 `research_profile.primary_areas` 中添加更精确的关键词

**Q: 想添加新的职位平台？**
- 在 `scripts/scraper.py` 中按现有函数模板添加新的 `fetch_xxx()` 函数
- 在 `fetch_all()` 函数末尾加入即可

**Q: 修改每日运行时间？**
- 编辑 `.github/workflows/daily_scan.yml` 中的 cron 表达式
- `0 7 * * *` = 每天 07:00 UTC（北京时间 15:00）
