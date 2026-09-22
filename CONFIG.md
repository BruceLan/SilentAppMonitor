# 配置说明

本文档详细说明了 Apple 应用监控系统的所有配置项。

## 环境变量配置

### 必需配置

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `ENV` | 环境标识 | `local` 或 `production` |
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_a9ccfb2bbf385cc6` |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | `your_secret_here` |
| `APPMGR_MONITOR_URL` | AppMgr 监控接口地址 | `https://appmgr.example.com` |
| `APPMGR_MONITOR_API_KEY` | AppMgr 监控接口 Key | `your_monitor_api_key` |
| `APPMGR_MONITOR_TEAM_NAME` | 本次监控所属团队名称，同时作为飞书消息前缀 | `静界` |

**ENV 说明：**
- `local`：本地调试模式，不发送飞书通知，适合开发测试
- `production`：生产环境，发送飞书通知，适合正式运行

### 可选配置（飞书通知）

**注意：** 当 `ENV=local` 时，以下配置不生效（不发送通知）

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `FEISHU_CHAT_ID_ALL` | @所有人的群聊 ID | `oc_1de66c6e3d6dba470e302b2d474db39f` |
| `FEISHU_CHAT_ID_TEAM` | @指定用户的群聊 ID | `oc_26e985ac87884ce23bc1c181cf0f61dc` |
| `FEISHU_MENTION_USERS` | 要 @ 的用户 ID 列表（逗号分隔） | `ou_aaa,ou_bbb,ou_ccc` |

### 可选配置（监控写入）

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `ENABLE_STATUS_UPDATE` | 是否允许将上线记录标记为已发布；首次接入建议关闭 | `false` |

## 配置文件位置

### 本地开发

创建 `.env` 文件在项目根目录：

```bash
# 复制模板
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 本地调试模式（不发送飞书通知）
ENV=local

# 飞书应用配置（用于群通知）
FEISHU_APP_ID=cli_a9ccfb2bbf385cc6
FEISHU_APP_SECRET=your_secret_here

# AppMgr 监控接口配置
APPMGR_MONITOR_URL=https://appmgr.example.com
APPMGR_MONITOR_API_KEY=your_monitor_api_key
APPMGR_MONITOR_TEAM_NAME=静界
ENABLE_STATUS_UPDATE=false

# 本地调试时可以不配置通知
# FEISHU_CHAT_ID_ALL=oc_xxx
# FEISHU_CHAT_ID_TEAM=oc_yyy
# FEISHU_MENTION_USERS=ou_aaa,ou_bbb,ou_ccc
```

### GitHub Actions

在 GitHub 仓库中配置 Secrets：

1. 进入仓库 Settings -> Secrets and variables -> Actions
2. 点击 "New repository secret" 添加密钥

**注意：** GitHub Actions 默认为生产环境（`ENV=production`），会发送飞书通知。

## 配置管理（config/settings.py）

配置类 `Settings` 负责加载和管理所有配置：

```python
from config.settings import settings

# 访问配置
app_id = settings.FEISHU_APP_ID
appmgr_monitor_url = settings.APPMGR_MONITOR_URL
appmgr_monitor_api_key = settings.APPMGR_MONITOR_API_KEY
team_name = settings.APPMGR_MONITOR_TEAM_NAME
enable_status_update = settings.ENABLE_STATUS_UPDATE
notifications = settings.FEISHU_NOTIFICATIONS

# 验证配置
if settings.validate():
    print("配置有效")
```

### 通知配置结构

`FEISHU_NOTIFICATIONS` 是一个列表，每个元素包含：

```python
{
    "chat_id": "oc_xxx",              # 群聊 ID（必需）
    "mention_all": True,              # 是否 @ 所有人（可选）
    "mention_user_ids": ["ou_xxx"]    # 要 @ 的用户列表（可选）
}
```

## 飞书应用配置

### 1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 获取 App ID 和 App Secret

### 2. 配置权限

在应用管理页面添加以下权限：

- `im:message` - 发送消息

### 3. 添加应用到群聊

1. 打开飞书群聊
2. 点击右上角「...」->「设置」
3. 找到「群机器人」->「添加机器人」
4. 搜索并添加你的应用

## AppMgr 监控接口

GitHub 只访问 AppMgr 的专用监控接口，core-service 保持在 AppMgr 内部访问：

- `POST /api/monitor/v1/reviews/query`：按 `teamName` 查询监控所需的 App、当前审核记录和提审中的记录
- `POST /api/monitor/v1/reviews/approve`：请求体只需 `{ "reviewRecordId": 123, "appEntityId": 456 }`，`approvedAt` 由 AppMgr 自动生成并更新过审状态

查询请求体为 `{ "teamName": "静界" }`，使用 `x-monitor-api-key` 认证。`APPMGR_MONITOR_TEAM_NAME` 必须与 core-service 的团队名称完全一致。首次接入时监控端的 `ENABLE_STATUS_UPDATE` 应为 `false`，确认查询结果后再开启过审写入。API key 只应配置在部署环境变量或 GitHub Actions Secrets 中，不要提交到代码仓库。

## 获取群聊 ID 和用户 ID

### 获取群聊 ID

方法 1：通过群设置
1. 打开飞书群聊
2. 点击右上角「...」->「设置」
3. 在 URL 中可以看到群聊 ID（格式：`oc_xxx`）

方法 2：通过开发者工具
1. 使用飞书 API 获取群列表
2. 查找对应群聊的 `chat_id`

### 获取用户 ID

方法 1：通过用户信息
1. 在飞书中打开用户个人资料
2. 使用飞书 API 查询用户信息

方法 2：通过开发者工具
1. 使用飞书 API 获取部门用户列表
2. 查找对应用户的 `open_id`

## 业务规则配置

当前流程只有 Apple 上线监控：

- `services/core_service.py` 的 `get_review_groups()`：按 `APPMGR_MONITOR_TEAM_NAME` 查询 App/审核记录，并按 `appEntityId` 构建父子分组
- `monitor_apple.py` 的 `AppleMonitor.evaluate_records()`：生成 Apple Store 监控候选
- `models/record.py` 的 `should_monitor_online()`：决定是否跳过“五图”记录

### 当前规则

**1. 当前发包流水选择**

- 只处理 AppMgr 返回的“提审中的 App”
- 单记录模式：记录本身 `包状态 = 提审中` 时，记录本身就是当前流水
- 父子模式：父记录快照 `包状态 = 提审中` 时，记录组才进入处理范围
- 在已进入处理范围的父子组里，只在子记录里选择 `包状态 = 提审中` 的记录
- 当存在多条提审中子记录时，按 `提审时间` 倒序、`版本号` 倒序选出当前流水

**2. Apple 上线监控**

- 只对“当前流水”做 Apple 监控
- `阶段 = 五图`：跳过 Apple 上线监控
- 非 `五图`：要求具备 `Apple ID + 版本号`

### 自定义规则

如需调整规则，优先修改以下方法：

```python
class ApplePackageRecord:
    def should_monitor_online(self):
        """定义哪些记录需要进入 Apple 上线监控"""
```

## 日志配置

日志工具在 `utils/logger.py` 中定义，支持：

- GitHub Actions 日志分组
- 不同级别的日志（info, warning, error, success）
- 时间戳自动添加

### 使用日志

```python
from utils.logger import log_info, log_warning, log_error, log_success

log_info("信息日志")
log_warning("警告日志")
log_error("错误日志")
log_success("成功日志")
```

## 高级配置

### 调整监控查询

AppMgr 会按 `teamName` 查询提审中的 App、`isCurrentRecord=true` 的当前记录和提审中的记录。父子关系通过审核记录返回的 `appEntityId` 和 `isRootRecord` 识别，同时保留“提审中子记录按时间/版本选择最新”的规则。相关编排位于 `services/core_service.py`。

### 修改 Apple 监控条件

如果要调整哪些记录进入 Apple 监控，优先改两个位置：

```python
def should_monitor_online(self):
    return self.stage != "五图"
```

```python
apple_id = current_record.resolve_monitor_apple_id(record)
if not apple_id:
    online_errors.append("缺少 Apple ID，无法监控上线")
if not current_record.version:
    online_errors.append("缺少版本号，无法监控上线")
```

## 故障排查

### 配置验证失败

运行以下命令检查配置：

```python
from config.settings import settings

if settings.validate():
    print("✅ 配置有效")
    print(f"App ID: {settings.FEISHU_APP_ID}")
    print(f"通知配置: {len(settings.FEISHU_NOTIFICATIONS)} 个群")
else:
    print("❌ 配置无效，请检查环境变量")
```

### AppMgr 或飞书权限问题

如果遇到权限错误，检查：

1. `APPMGR_MONITOR_URL` 和 `APPMGR_MONITOR_API_KEY` 是否正确
2. AppMgr 的 `MONITOR_API_KEY` 是否一致
3. 飞书开放平台是否已添加 `im:message` 权限
4. 飞书应用是否已添加到目标群聊

### 环境变量未生效

确保：

1. `.env` 文件在项目根目录
2. 环境变量名称正确（区分大小写）
3. 重启应用以加载新的环境变量
