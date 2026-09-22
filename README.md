# Apple 应用监控系统

按团队监控 Apple Store 应用上线状态，并在过审后更新 App 状态。

## 功能特性

- 🔍 自动查询 Apple Store 应用状态
- 📊 通过 AppMgr 监控接口查询应用和提审记录
- � 应用上线后自动发送飞书通知（支持 @ 所有人或指定用用户）
- ⏰ 支持定时执行（GitHub Actions）
- 📝 通过 AppMgr 更新提审状态和 App 主档

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 环境配置
ENV=local  # 本地调试模式（不发送飞书通知）

# 飞书应用配置（用于群通知）
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret

# AppMgr 监控接口配置（必需）
APPMGR_MONITOR_URL=https://appmgr.example.com
APPMGR_MONITOR_API_KEY=your_monitor_api_key
APPMGR_MONITOR_TEAM_NAME=静界

# 首次接入建议设为 false，只查询并检查，不写入状态
ENABLE_STATUS_UPDATE=false

# 飞书通知配置（生产环境需要，本地调试可不填）
# FEISHU_CHAT_ID_ALL=oc_xxx
# FEISHU_CHAT_ID_TEAM=oc_yyy
# FEISHU_MENTION_USERS=ou_aaa,ou_bbb
```

`APPMGR_MONITOR_TEAM_NAME` 必须使用 core-service 中的精确团队名称，同时用于团队查询和飞书消息前缀。

**环境说明：**
- `ENV=local`：本地调试模式，不发送飞书通知
- `ENV=production`：生产环境，发送飞书通知

### 3. 运行脚本

```bash
python monitor_apple.py
```

## 配置说明

详细配置说明请查看 [CONFIG.md](CONFIG.md)

## 部署指南

GitHub Actions 部署指南请查看 [DEPLOY.md](DEPLOY.md)

## 项目结构

```
apple_monitor/
├── config/                    # 配置管理
│   ├── __init__.py
│   └── settings.py           # 环境变量配置
├── models/                    # 数据模型
│   ├── __init__.py
│   └── record.py             # ApplePackageRecord 数据模型
├── services/                  # 外部服务
│   ├── __init__.py
│   ├── apple_service.py      # Apple Store API 服务
│   ├── core_service.py       # AppMgr 监控接口查询与更新服务
│   └── feishu_messenger.py   # 飞书消息服务
├── utils/                     # 工具函数
│   ├── __init__.py
│   └── logger.py             # 日志工具
├── monitor_apple.py          # 主入口（业务流程编排）
├── requirements.txt          # 依赖包
├── .env                      # 环境变量配置
├── CONFIG.md                 # 配置文档
└── DEPLOY.md                 # 部署文档
```

## 业务规则

- 只处理 AppMgr 按 `APPMGR_MONITOR_TEAM_NAME` 返回的“提审中” App
- 单记录模式使用当前审核记录
- 父子模式按提审时间、版本号选择最新的提审中子记录，确保过审时更新正确的审核记录
- `阶段 = 五图`：跳过 Apple Store 上线监控
- 其他记录必须具备 `Apple ID + 版本号`
- Apple Store 版本与当前监控版本一致并确认上线后，调用 AppMgr 更新审核记录和 App 主档

## 权限要求

飞书应用仅用于群通知，需要：

- ✅ `im:message` - 发送消息

应用和提审记录的读写由 AppMgr 监控接口完成，AppMgr 在服务端访问 core-service。

## 本地开发

### 环境要求

- Python 3.7+
- pip

### 开发流程

1. 克隆仓库
2. 安装依赖：`pip install -r requirements.txt`
3. 配置 `.env` 文件
4. 运行脚本：`python monitor_apple.py`

## 故障排查

### 问题：飞书消息发送失败

- 检查应用是否已添加到目标群聊
- 检查应用是否有 `im:message` 权限
- 查看错误码和错误信息

### 问题：core-service 更新失败

- 检查 `APPMGR_MONITOR_URL` 是否可访问
- 检查 `APPMGR_MONITOR_API_KEY` 是否正确

## License

MIT
