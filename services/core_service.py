"""
core-service HTTP 适配层

监控流程只依赖本模块提供的父子记录模型和更新方法，不直接读写飞书多维表格。
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from models.record import ApplePackageRecord
from utils.logger import log_error, log_info


class CoreServiceError(RuntimeError):
    """core-service 请求失败"""


@dataclass
class CoreReviewGroup:
    """一个 App 主档及其当前提审记录"""

    app_entity_id: int
    parent_record: ApplePackageRecord
    current_record: Optional[ApplePackageRecord]
    submitting_children: List[ApplePackageRecord]
    has_children: bool


class CoreServiceClient:
    """通过 AppMgr 监控接口访问 core-service 数据及更新能力。"""

    MONITOR_PATH = "/api/monitor/v1"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        team_name: str,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
        monitor_path: str = MONITOR_PATH,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.team_name = (team_name or "").strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        self.monitor_path = "/" + monitor_path.strip("/")

    def _monitor_path(self, path: str) -> str:
        return f"{self.monitor_path}/{path.strip('/')}"

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送一次带 API key 的 JSON 请求，并校验统一响应封装。"""
        try:
            response = self.session.post(
                f"{self.base_url}{path}",
                headers={
                    "x-monitor-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CoreServiceError(f"请求 {path} 失败: {exc}") from exc

        if not isinstance(body, dict) or body.get("success") is not True:
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                message = error.get("message") or error.get("code") or str(error)
            else:
                message = str(error or body)
            raise CoreServiceError(f"请求 {path} 返回失败: {message}")

        return body

    @staticmethod
    def _as_int(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_string(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)

    @classmethod
    def _status_label(cls, value: Any) -> Optional[str]:
        if isinstance(value, dict):
            return cls._as_string(value.get("label") or value.get("code"))
        return cls._as_string(value)

    @classmethod
    def _timestamp(cls, value: Any) -> Optional[int]:
        if isinstance(value, str) and value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        return ApplePackageRecord._parse_timestamp(value)

    @classmethod
    def _record_from_review(cls, data: Dict[str, Any]) -> ApplePackageRecord:
        """将审核记录投影映射为现有监控模型。"""
        return ApplePackageRecord(
            record_id=cls._as_string(data.get("id")),
            package_name=cls._as_string(data.get("appName")),
            package_status=cls._as_string(data.get("packageStatus")),
            version=cls._as_string(data.get("versionName")),
            apple_id=cls._as_string(data.get("appleId")),
            production_package_name=cls._as_string(data.get("productionBundleId")),
            test_package_name=cls._as_string(data.get("testBundleId")),
            team=cls._as_string(data.get("teamName")),
            stage=cls._as_string(data.get("stage")),
            submission_time=cls._timestamp(data.get("submittedAt")),
            approval_time=cls._timestamp(data.get("approvedAt")),
            exception_time=cls._timestamp(data.get("exceptionAt")),
            exception_category=cls._as_string(data.get("exceptionCategory")),
            update_description=cls._as_string(data.get("releaseNotes")),
            notes=cls._as_string(data.get("remark")),
        )

    @classmethod
    def _record_from_app(cls, data: Dict[str, Any]) -> ApplePackageRecord:
        """将 App 主档投影映射为父记录快照。"""
        return ApplePackageRecord(
            record_id=f"app-{data.get('id')}",
            package_name=cls._as_string(data.get("appName")),
            package_status=cls._status_label(data.get("currentStatus")),
            version=cls._as_string(data.get("currentVersion")),
            apple_id=cls._as_string(data.get("appleId")),
            production_package_name=cls._as_string(data.get("productionBundleId")),
            test_package_name=cls._as_string(data.get("testBundleId")),
            product_code=cls._as_string(data.get("productCode")),
            team=cls._as_string(data.get("teamName")),
            stage=cls._as_string(data.get("stage")),
            approval_time=cls._timestamp(data.get("currentApprovedAt")),
            exception_time=cls._timestamp(data.get("currentExceptionAt")),
            exception_category=cls._as_string(data.get("currentExceptionCategory")),
            refund_callback_url=cls._as_string(data.get("refundCallbackUrl")),
            privacy_policy=cls._as_string(data.get("privacyPolicyUrl")),
            notes=cls._as_string(data.get("remark")),
        )

    @staticmethod
    def _sort_submitting_children(
        records: List[ApplePackageRecord],
    ) -> List[ApplePackageRecord]:
        return sorted(
            records,
            key=lambda record: (
                record.submission_time or 0,
                ApplePackageRecord._safe_version(record.version),
                record.record_id or "",
            ),
            reverse=True,
        )

    def get_review_groups(self) -> List[CoreReviewGroup]:
        """
        读取当前提审中的 App，并恢复监控需要的父子记录关系。

        App 主档的 status 决定旧流程的处理范围；current review 用于识别单记录
        和父子记录；额外查询全部“提审中”记录，以保留多子记录时的旧排序规则。
        """
        try:
            body = self._post(
                self._monitor_path("reviews/query"),
                {"teamName": self.team_name},
            )
            scope = body.get("data")
            if not isinstance(scope, dict):
                raise CoreServiceError("监控接口返回的数据格式不正确")

            active_apps = self._dict_items(scope.get("apps"), "apps")
            current_reviews = self._dict_items(scope.get("currentReviews"), "currentReviews")
            submitting_reviews = self._dict_items(scope.get("submittingReviews"), "submittingReviews")
        except CoreServiceError as exc:
            log_error(f"读取 AppMgr 监控数据失败: {exc}")
            return []

        current_by_app: Dict[int, Dict[str, Any]] = {}
        for review in current_reviews:
            app_entity_id = self._as_int(review.get("appEntityId"))
            if app_entity_id is not None and app_entity_id not in current_by_app:
                current_by_app[app_entity_id] = review

        submitting_by_app: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for review in submitting_reviews:
            app_entity_id = self._as_int(review.get("appEntityId"))
            if app_entity_id is None or review.get("isRootRecord") is True:
                continue
            submitting_by_app[app_entity_id].append(review)

        groups: List[CoreReviewGroup] = []
        for app in active_apps:
            app_entity_id = self._as_int(app.get("id"))
            if app_entity_id is None:
                continue

            parent_record = self._record_from_app(app)
            current_review = current_by_app.get(app_entity_id)
            submitting_children = [
                self._record_from_review(review)
                for review in submitting_by_app.get(app_entity_id, [])
            ]

            if (
                current_review
                and current_review.get("isRootRecord") is False
                and current_review.get("packageStatus") == "提审中"
            ):
                current_record = self._record_from_review(current_review)
                if all(item.record_id != current_record.record_id for item in submitting_children):
                    submitting_children.append(current_record)
            else:
                current_record = None

            submitting_children = self._sort_submitting_children(submitting_children)
            review_record_count = self._as_int(app.get("reviewRecordCount")) or 0
            has_children = bool(submitting_children) or (
                current_review is not None and current_review.get("isRootRecord") is False
            ) or review_record_count > 1

            if has_children:
                # 父子模式沿用旧逻辑：只从提审中的子记录中选择最新记录。
                current_record = submitting_children[0] if submitting_children else None
            elif current_review and current_review.get("isRootRecord") is True:
                current_record = self._record_from_review(current_review)

            groups.append(
                CoreReviewGroup(
                    app_entity_id=app_entity_id,
                    parent_record=parent_record,
                    current_record=current_record,
                    submitting_children=submitting_children,
                    has_children=has_children,
                )
            )

        log_info(f"AppMgr 返回当前审核中 App: {len(groups)} 个")
        return groups

    @staticmethod
    def _dict_items(value: Any, field_name: str) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            raise CoreServiceError(f"监控接口字段 {field_name} 格式不正确")
        return [item for item in value if isinstance(item, dict)]

    def mark_approved(
        self,
        review_record_id: int,
        app_entity_id: int,
    ) -> bool:
        """
        标记审核记录过审，并同步 App 主档状态。

        由 AppMgr 在服务端按固定顺序更新审核记录和 App 主档。
        releaseResult 和 submittedAt 刻意不写入。
        """
        try:
            self._post(
                self._monitor_path("reviews/approve"),
                {
                    "reviewRecordId": int(review_record_id),
                    "appEntityId": int(app_entity_id),
                },
            )
        except (CoreServiceError, TypeError, ValueError) as exc:
            log_error(f"通过 AppMgr 更新审核记录 {review_record_id} 失败: {exc}")
            return False

        log_info(f"已通过 AppMgr 更新审核记录 {review_record_id} 和 App 主档 {app_entity_id} 为已发布")
        return True
