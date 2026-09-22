"""
Apple 应用监控主程序
负责业务流程编排
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List

from config.settings import settings
from models.record import ApplePackageRecord
from services.apple_service import AppleStoreService
from services.core_service import CoreReviewGroup, CoreServiceClient
from services.feishu_messenger import FeishuMessenger
from utils.logger import (
    is_github_actions,
    log_endgroup,
    log_error,
    log_group,
    log_info,
    log_success,
    log_warning,
)


@dataclass
class MonitorCandidate:
    """当前需要做 Apple 上线监控的对象"""

    parent_record: ApplePackageRecord
    current_record: ApplePackageRecord
    apple_id: str
    version: str
    app_entity_id: int
    review_record_id: int


class AppleMonitor:
    """Apple 应用监控类 - 负责业务流程编排"""

    def __init__(
        self,
        core_service: CoreServiceClient,
        feishu_messenger: FeishuMessenger,
        apple_service: AppleStoreService,
    ):
        self.core_service = core_service
        self.feishu_messenger = feishu_messenger
        self.apple_service = apple_service

    def evaluate_records(
        self,
        records: List[CoreReviewGroup],
    ) -> List[MonitorCandidate]:
        """解析当前记录，生成 Apple 上线监控候选。"""
        monitor_candidates: List[MonitorCandidate] = []

        for group in records:
            record = group.parent_record
            if not record.is_in_review_scope():
                continue

            current_record = group.current_record
            if group.has_children and not current_record:
                continue

            if not current_record:
                continue

            if not current_record.should_monitor_online():
                log_info(
                    f"{current_record.package_name or record.package_name} - "
                    f"当前记录阶段为 {current_record.stage}，跳过 Apple 上线监控"
                )
                continue

            apple_id = current_record.resolve_monitor_apple_id(record)
            online_errors = []
            if not apple_id:
                online_errors.append("缺少 Apple ID，无法监控上线")
            if not current_record.version:
                online_errors.append("缺少版本号，无法监控上线")

            if online_errors:
                log_warning(
                    f"{current_record.package_name or record.package_name} - "
                    f"跳过 Apple 上线监控: {'；'.join(online_errors)}"
                )
                continue

            monitor_candidates.append(
                MonitorCandidate(
                    parent_record=record,
                    current_record=current_record,
                    apple_id=str(apple_id),
                    version=current_record.version,
                    app_entity_id=group.app_entity_id,
                    review_record_id=int(current_record.record_id),
                )
            )

        return monitor_candidates

    def run(self) -> List[MonitorCandidate]:
        """
        运行监控任务

        Returns:
            Apple 上线监控候选列表
        """
        log_group("🚀 Apple 应用监控任务开始")
        log_info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_info(f"运行环境: {'GitHub Actions' if is_github_actions() else 'Local'}")
        log_endgroup()

        if not settings.validate():
            log_error("缺少必要的环境变量")
            log_info("请设置以下环境变量：")
            log_info("  - FEISHU_APP_ID")
            log_info("  - FEISHU_APP_SECRET")
            log_info("  - APPMGR_MONITOR_URL")
            log_info("  - APPMGR_MONITOR_API_KEY")
            log_info("  - APPMGR_MONITOR_TEAM_NAME")
            return []

        log_group("📊 步骤 1: 从 AppMgr 读取记录分组")
        grouped_records = self.core_service.get_review_groups()
        log_endgroup()

        log_group("🧾 步骤 2: 解析当前记录")
        monitor_candidates = self.evaluate_records(grouped_records)
        active_review_groups = [
            group for group in grouped_records if group.parent_record.is_in_review_scope()
        ]
        log_info(f"当前审核中记录组: {len(active_review_groups)}")
        log_info(f"Apple 监控候选: {len(monitor_candidates)} 条")
        log_endgroup()

        log_group("🍎 步骤 3: 查询 Apple Store 状态并更新")
        log_info(f"只处理 Apple 监控候选（共 {len(monitor_candidates)} 个）")

        current_timestamp = int(datetime.now().astimezone().timestamp() * 1000)
        success_count = 0
        waiting_count = 0
        query_failed_count = 0
        update_failed_count = 0
        dry_run_count = 0
        lookup_result = self.apple_service.query_app_statuses_with_meta(
            [candidate.apple_id for candidate in monitor_candidates],
            verbose=False,
        )
        status_by_apple_id = lookup_result.status_by_apple_id
        failed_lookup_ids = set(lookup_result.failed_apple_ids)

        log_info(
            f"去重后 Apple ID: {len(status_by_apple_id)} 个，分 {lookup_result.total_batches} 批查询"
        )
        log_info(f"查询成功批次: {lookup_result.successful_batches}")
        if lookup_result.failed_batches:
            log_warning(f"查询失败批次: {lookup_result.failed_batches}")

        for candidate in monitor_candidates:
            if candidate.apple_id in failed_lookup_ids:
                log_warning(
                    f"{candidate.parent_record.package_name} - Apple 状态查询失败，跳过本轮判定"
                )
                log_warning(f"  🆔 Apple ID: {candidate.apple_id}")
                query_failed_count += 1
                continue

            app_status = status_by_apple_id.get(candidate.apple_id)

            is_version_online = False
            if app_status and app_status["is_online"]:
                store_version = app_status["version"]
                if store_version and store_version == candidate.version:
                    is_version_online = True

            if is_version_online:
                log_info(f"{candidate.parent_record.package_name} - 指定版本已上线")
                log_info(f"  📱 应用名称: {app_status['track_name']}")
                log_info(f"  📦 版本号: {store_version} (当前监控版本: {candidate.version})")
                log_info(f"  🆔 Apple ID: {candidate.apple_id}")
                log_info(f"  📅 发布日期: {app_status['release_date']}")
                log_info(f"  🔄 当前版本发布日期: {app_status['current_version_release_date']}")
                if app_status.get("track_view_url"):
                    log_info(f"  🔗 应用链接: {app_status['track_view_url']}")

                if not settings.ENABLE_STATUS_UPDATE:
                    log_warning("ENABLE_STATUS_UPDATE=false，仅记录上线结果，不更新 AppMgr 状态")
                    dry_run_count += 1
                    continue

                status_updated = self.core_service.mark_approved(
                    review_record_id=candidate.review_record_id,
                    app_entity_id=candidate.app_entity_id,
                )
                if not status_updated:
                    log_warning("  AppMgr 状态更新失败，跳过飞书通知")
                    update_failed_count += 1
                    continue

                self.feishu_messenger.send_notifications(
                    notifications=settings.FEISHU_NOTIFICATIONS,
                    app_name=candidate.parent_record.package_name,
                    stage=candidate.current_record.stage or "未知",
                    version=candidate.version,
                )
                candidate.current_record.package_status = "已发布"
                candidate.current_record.approval_time = current_timestamp
                success_count += 1
            else:
                log_info(f"{candidate.parent_record.package_name} - 指定版本未上线")
                log_info(f"  📦 当前监控版本: {candidate.version}")
                log_info(f"  🆔 Apple ID: {candidate.apple_id}")
                if not app_status or not app_status["is_online"]:
                    log_info("  ❓ 原因: Apple Lookup 未返回该 Apple ID 的可用结果")
                else:
                    log_info(f"  📱 应用名称: {app_status['track_name']}")
                    log_info(f"  🏪 商店版本: {app_status['version']}")
                    log_info(f"  📅 发布日期: {app_status['release_date']}")
                    log_info(f"  🔄 当前版本发布日期: {app_status['current_version_release_date']}")
                    log_info("  ❓ 原因: 已查到应用，但商店版本与当前监控版本不一致")
                    if app_status.get("track_view_url"):
                        log_info(f"  🔗 应用链接: {app_status['track_view_url']}")
                waiting_count += 1

        log_endgroup()

        log_group("📊 任务执行总结")
        log_info(f"总共读取主记录组: {len(grouped_records)} 个")
        log_info(f"Apple 监控候选: {len(monitor_candidates)} 个")
        log_info(f"Apple 查询批次: {lookup_result.total_batches}")
        log_info(f"Apple 查询成功批次: {lookup_result.successful_batches}")
        log_info(f"Apple 查询失败批次: {lookup_result.failed_batches}")
        log_info(f"成功上线: {success_count} 个")
        log_info(f"等待上线: {waiting_count} 个")
        log_info(f"查询失败: {query_failed_count} 个")
        log_info(f"状态更新失败: {update_failed_count} 个")
        log_info(f"只读命中待更新: {dry_run_count} 个")
        log_info(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_endgroup()

        return monitor_candidates


def main():
    """主函数"""
    core_service = CoreServiceClient(
        base_url=settings.APPMGR_MONITOR_URL,
        api_key=settings.APPMGR_MONITOR_API_KEY,
        team_name=settings.APPMGR_MONITOR_TEAM_NAME,
    )

    feishu_messenger = FeishuMessenger(
        app_id=settings.FEISHU_APP_ID,
        app_secret=settings.FEISHU_APP_SECRET,
        message_prefix=settings.APPMGR_MONITOR_TEAM_NAME,
    )

    apple_service = AppleStoreService()

    monitor = AppleMonitor(
        core_service=core_service,
        feishu_messenger=feishu_messenger,
        apple_service=apple_service,
    )

    monitor.run()


if __name__ == "__main__":
    try:
        main()
        log_success("✅ 监控任务执行完成")
    except Exception as e:
        log_error(f"监控任务执行失败: {str(e)}")
        import traceback

        log_info(traceback.format_exc())
        exit(1)
