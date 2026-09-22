"""
飞书消息服务模块
"""
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
from typing import List, Dict, Any
import json
import uuid
from utils.logger import log_info, log_warning, log_success, log_error


class FeishuMessenger:
    """飞书消息服务类"""
    
    def __init__(self, app_id: str, app_secret: str, message_prefix: str = ""):
        """
        初始化飞书客户端
        
        Args:
            app_id: 飞书应用的 App ID
            app_secret: 飞书应用的 App Secret
            message_prefix: 飞书消息前缀（可选）
        """
        self.message_prefix = (message_prefix or "").strip()
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

    def _apply_prefix(self, message_text: str) -> str:
        """为消息正文添加统一前缀"""
        if not self.message_prefix:
            return message_text
        return f"{self.message_prefix} {message_text}"
    
    def send_message(
        self,
        chat_id: str,
        app_name: str,
        stage: str,
        version: str,
        mention_all: bool = False,
        mention_user_ids: List[str] = None
    ) -> bool:
        """
        发送消息到飞书群聊
        
        Args:
            chat_id: 飞书群聊 ID
            app_name: 应用名称
            stage: 阶段
            version: 版本号
            mention_all: 是否 @ 所有人
            mention_user_ids: 要 @ 的用户 open_id 列表（可选）
        
        Returns:
            发送是否成功
        """
        if not chat_id:
            log_warning("飞书群聊 ID 未配置，跳过发送消息")
            return False
        
        try:
            message_text = self._apply_prefix(f"{app_name} {stage} V{version} 过审并发布了")
            
            # 构建富文本消息内容（支持 @ 功能）
            content_parts = []
            
            # 添加 @ 所有人
            if mention_all:
                content_parts.append({
                    "tag": "at",
                    "user_id": "all"
                })
                content_parts.append({
                    "tag": "text",
                    "text": " "
                })
            
            # 添加 @ 多个用户
            if mention_user_ids:
                for user_id in mention_user_ids:
                    content_parts.append({
                        "tag": "at",
                        "user_id": user_id
                    })
                    content_parts.append({
                        "tag": "text",
                        "text": " "
                    })
            
            # 添加消息正文
            content_parts.append({
                "tag": "text",
                "text": message_text
            })
            
            # 构建消息内容
            content = json.dumps({
                "zh_cn": {
                    "title": "",
                    "content": [content_parts]
                }
            }, ensure_ascii=False)
            
            # 生成唯一的 UUID
            message_uuid = str(uuid.uuid4())
            
            # 构建请求
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("post")  # 使用富文本消息类型
                    .content(content)
                    .uuid(message_uuid)
                    .build()
                ) \
                .build()
            
            # 发送消息
            response = self.client.im.v1.message.create(request)
            
            if response.success():
                mention_info = ""
                if mention_all:
                    mention_info = " (@所有人)"
                elif mention_user_ids:
                    mention_info = f" (@{len(mention_user_ids)}人)"
                log_info(f"飞书消息发送成功{mention_info}: {message_text}")
                return True
            else:
                log_error("飞书消息发送失败")
                log_info(f"  错误码: {response.code}")
                log_info(f"  错误信息: {response.msg}")
                if response.code == 230002:
                    log_error("  💡 机器人不在该群聊中，请先将应用添加到群聊")
                    log_info("     - 打开飞书群聊")
                    log_info("     - 点击右上角「...」->「设置」")
                    log_info("     - 找到「群机器人」->「添加机器人」")
                    log_info("     - 搜索并添加你的应用")
                return False
                
        except Exception as e:
            log_error(f"发送飞书消息异常: {str(e)}")
            return False

    def send_notifications(
        self,
        notifications: List[Dict[str, Any]],
        app_name: str,
        stage: str,
        version: str
    ) -> None:
        """
        发送通知到多个飞书群聊
        
        Args:
            notifications: 通知配置列表，每个配置包含：
                - chat_id: 群聊 ID
                - mention_all: 是否 @ 所有人（可选）
                - mention_user_ids: 要 @ 的用户 open_id 列表（可选）
            app_name: 应用名称
            stage: 阶段
            version: 版本号
        
        示例：
            notifications = [
                {"chat_id": "oc_xxx", "mention_all": True},
                {"chat_id": "oc_yyy", "mention_user_ids": ["ou_xxx", "ou_yyy"]}
            ]
        """
        if not notifications:
            log_warning("未配置飞书通知，跳过发送")
            return
        
        log_info(f"📨 发送飞书通知到 {len(notifications)} 个群聊...")
        for config in notifications:
            chat_id = config.get("chat_id")
            mention_all = config.get("mention_all", False)
            mention_user_ids = config.get("mention_user_ids")
            
            if not chat_id:
                log_warning("通知配置缺少 chat_id，跳过")
                continue
            
            self.send_message(
                chat_id=chat_id,
                app_name=app_name,
                stage=stage,
                version=version,
                mention_all=mention_all,
                mention_user_ids=mention_user_ids
            )
