# 自动打卡与日报系统

这是一个基于 Playwright 的自动化脚本，用于自动完成每日打卡和日报提交，并支持 WxPusher 微信通知。

## ✨ 功能特点

- **自动打卡**：每天定时自动登录并完成打卡
- **自动日报**：每天定时自动生成并提交日报（支持 AI 生成内容）
- **微信通知**：任务成功或失败都会通过 WxPusher 推送通知
- **GitHub Actions**：完全基于云端运行，无需本地挂机

## 🚀 快速开始

### 1. Fork 本仓库

将本项目 Fork 到你的 GitHub 账号。

### 2. 配置 Secrets

在仓库的 `Settings` -> `Secrets and variables` -> `Actions` 中添加以下 Secrets：

| Secret 名称 | 说明 |
|------------|------|
| `CHECKIN_USERNAME` | 你的登录用户名 |
| `CHECKIN_PASSWORD` | 你的登录密码 |
| `WXPUSHER_APP_TOKEN` | WxPusher 应用 Token |
| `WXPUSHER_UID` | WxPusher 用户 UID |

### 3. 启用 GitHub Actions

进入 `Actions` 标签页，启用工作流。系统将按照以下时间自动运行：

- **自动打卡**：每天北京时间 08:00 和 17:00
- **自动日报**：每天北京时间 19:00

## 🛠️ 本地运行（可选）

如果你需要在本地运行：

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. 配置 `config.json`（复制 `config.json.example`）：
   ```json
   {
     "username": "你的用户名",
     "password": "你的密码",
     "wxpusher_app_token": "你的Token",
     "wxpusher_uid": "你的UID"
   }
   ```

3. 运行脚本：
   ```bash
   python auto_checkin.py      # 运行打卡
   python auto_daily_report.py # 运行日报
   ```

## 📝 文件说明

- `auto_checkin.py`: 自动打卡核心脚本
- `auto_daily_report.py`: 自动日报核心脚本
- `.github/workflows/`: 定时任务配置

## ⚠️ 免责声明

本脚本仅供学习交流使用，请遵守相关规定。
