import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from models.record import ApplePackageRecord
from services.core_service import CoreReviewGroup, CoreServiceClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def success_response(data, total=None):
    payload = {"success": True, "data": data}
    if total is not None:
        payload["meta"] = {"total": total}
    return FakeResponse(payload)


class CoreServiceQueryTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.service = CoreServiceClient(
            base_url="http://core.example/",
            api_key="test-key",
            team_name="极光",
            session=self.session,
        )

    def test_get_review_groups_joins_apps_and_selects_latest_submitting_child(self):
        self.session.post.return_value = success_response(
            {
                "apps": [
                    {
                        "id": 10,
                        "appName": "Root App",
                        "appleId": "100",
                        "currentVersion": "1.0.0",
                        "currentStatus": {"code": "SUBMITTING", "label": "提审中"},
                        "stage": "开发",
                        "teamName": "极光",
                        "reviewRecordCount": 1,
                    },
                    {
                        "id": 20,
                        "appName": "Child App",
                        "appleId": "200",
                        "currentVersion": "2.0.0",
                        "currentStatus": {"code": "SUBMITTING", "label": "提审中"},
                        "stage": "旧阶段",
                        "teamName": "破晓",
                        "reviewRecordCount": 3,
                    },
                ],
                "currentReviews": [
                    {
                        "id": 101,
                        "appEntityId": 10,
                        "sourceFeishuRecordId": "root-10",
                        "sourceRootFeishuRecordId": "root-10",
                        "isRootRecord": True,
                        "isCurrentRecord": True,
                        "appName": "Root App",
                        "versionName": "1.0.0",
                        "packageStatus": "提审中",
                        "stage": "开发",
                        "submittedAt": "2026-09-03T10:00:00Z",
                    },
                    {
                        "id": 202,
                        "appEntityId": 20,
                        "sourceFeishuRecordId": "child-new",
                        "sourceRootFeishuRecordId": "root-20",
                        "isRootRecord": False,
                        "isCurrentRecord": True,
                        "appName": "Child App",
                        "versionName": "2.0.0",
                        "packageStatus": "提审中",
                        "stage": "新阶段",
                        "submittedAt": "2026-09-03T12:00:00Z",
                        "appleId": "201",
                    },
                ],
                "submittingReviews": [
                    {
                        "id": 202,
                        "appEntityId": 20,
                        "sourceFeishuRecordId": "child-new",
                        "sourceRootFeishuRecordId": "root-20",
                        "isRootRecord": False,
                        "isCurrentRecord": True,
                        "appName": "Child App",
                        "versionName": "2.0.0",
                        "packageStatus": "提审中",
                        "stage": "新阶段",
                        "submittedAt": "2026-09-03T12:00:00Z",
                        "appleId": "201",
                    },
                    {
                        "id": 201,
                        "appEntityId": 20,
                        "sourceFeishuRecordId": "child-old",
                        "sourceRootFeishuRecordId": "root-20",
                        "isRootRecord": False,
                        "isCurrentRecord": False,
                        "appName": "Child App",
                        "versionName": "1.9.0",
                        "packageStatus": "提审中",
                        "stage": "旧阶段",
                        "submittedAt": "2026-09-02T12:00:00Z",
                        "appleId": "200",
                    },
                ],
            }
        )

        groups = self.service.get_review_groups()

        self.assertEqual(2, len(groups))
        self.assertIsInstance(groups[0], CoreReviewGroup)
        self.assertFalse(groups[0].has_children)
        self.assertEqual("101", groups[0].current_record.record_id)
        self.assertTrue(groups[1].has_children)
        self.assertEqual("202", groups[1].current_record.record_id)
        self.assertEqual(["202", "201"], [item.record_id for item in groups[1].submitting_children])
        self.assertEqual("旧阶段", groups[1].parent_record.stage)
        self.assertEqual("新阶段", groups[1].current_record.stage)

        first_call = self.session.post.call_args_list[0]
        self.assertEqual("http://core.example/api/monitor/v1/reviews/query", first_call.args[0])
        self.assertEqual({"teamName": "极光"}, first_call.kwargs["json"])
        self.assertEqual("test-key", first_call.kwargs["headers"]["x-monitor-api-key"])


class CoreServiceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.service = CoreServiceClient(
            base_url="http://core.example",
            api_key="test-key",
            team_name="极光",
            session=self.session,
        )

    def test_mark_approved_updates_review_and_app_without_release_result_or_submitted_at(self):
        self.session.post.return_value = success_response({"reviewRecordId": 202, "appEntityId": 20})

        approved_at = datetime(2026, 9, 3, 12, 30, tzinfo=timezone.utc)
        result = self.service.mark_approved(
            review_record_id=202,
            app_entity_id=20,
            approved_at=approved_at,
        )

        self.assertTrue(result)
        self.assertEqual(
            "http://core.example/api/monitor/v1/reviews/approve",
            self.session.post.call_args.args[0],
        )
        review_payload = self.session.post.call_args.kwargs["json"]
        self.assertEqual(
            {"reviewRecordId": 202, "appEntityId": 20, "approvedAt": "2026-09-03T12:30:00+00:00"},
            review_payload,
        )
        self.assertNotIn("releaseResult", review_payload)
        self.assertNotIn("submittedAt", review_payload)

    def test_mark_approved_does_not_update_app_when_review_update_fails(self):
        self.session.post.return_value = FakeResponse(
            {"success": False, "error": {"code": "BAD_REQUEST", "message": "invalid"}}
        )

        result = self.service.mark_approved(
            review_record_id=202,
            app_entity_id=20,
            approved_at=datetime(2026, 9, 3, 12, 30, tzinfo=timezone.utc),
        )

        self.assertFalse(result)
        self.assertEqual(1, self.session.post.call_count)


if __name__ == "__main__":
    unittest.main()
