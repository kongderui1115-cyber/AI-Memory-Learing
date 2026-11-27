"""通知任务编排测试（NOTIF-05）：幂等、退避重试、失败记录、状态追踪、历史。

明确标注：使用 FakeHttpTransport / FakeSmtpTransport 作为测试替身隔离 I/O，
验证的是领域编排逻辑，不代表真实推送成功；真实联调需 BLK-03/04 授权后另做。
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.config import ChannelConfig  # noqa: E402
from app.notifications.contract_values import DeliveryStatus, JobStatus  # noqa: E402
from app.notifications.errors import EmptyContentError, NotificationError  # noqa: E402
from app.notifications.jobs import InMemoryJobRepository  # noqa: E402
from app.notifications.retry import RetryPolicy  # noqa: E402
from app.notifications.transports import HttpResult  # noqa: E402
from app.notifications.worker import NotificationWorker  # noqa: E402
from app.notifications.channels import default_registry  # noqa: E402

try:
    from .fakes import (  # noqa: E402
        FakeHttpTransport,
        FakeSmtpTransport,
        make_content,
        make_template,
    )
except (ImportError, ValueError):
    from fakes import (  # noqa: E402
        FakeHttpTransport,
        FakeSmtpTransport,
        make_content,
        make_template,
    )


FIXED = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
OK_BODY = '{"errcode":0,"errmsg":"ok"}'


def _policy():
    return RetryPolicy(
        max_attempts=3, base_seconds=60, multiplier=2, max_delay_seconds=None
    )


class NotificationWorkerTest(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(os.environ, {
            "WECOM_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=K",
        }, clear=True)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.cfg = ChannelConfig(
            name="wecom", channel_type="wecom_webhook",
            credential_ref="WECOM", user_id="u1",
        )
        self.tpl = make_template()
        self.content = make_content()

    def _worker(self, http, smtp, *, policy=None, repository=None):
        return NotificationWorker(
            registry=default_registry(),
            http=http,
            smtp=smtp,
            repository=repository or InMemoryJobRepository(),
            retry_policy=policy or _policy(),
            clock=lambda: FIXED,
        )

    def _create(self, worker, *, template=None, content=None, key=None, task_id="t1"):
        return worker.create_job(
            user_id="u1",
            task_id=task_id,
            channel_config=self.cfg,
            template=template or self.tpl,
            content=content or self.content,
            idempotency_key=key,
        )

    def test_success_path_creates_sent_job_and_one_delivery(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        worker = self._worker(http, FakeSmtpTransport())
        job = self._create(worker)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertGreaterEqual(len(job.segments), 1)

        worker.process(job, now=FIXED)
        self.assertEqual(job.status, JobStatus.SENT)
        self.assertIsNotNone(job.sent_at)
        self.assertEqual(job.attempt_count, 1)
        self.assertEqual(http.call_count, len(job.segments))

        deliveries = worker.repository.list_deliveries(job.id)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].status, DeliveryStatus.SENT)
        self.assertEqual(deliveries[0].attempt_no, 1)
        self.assertIsNotNone(deliveries[0].duration_ms)
        self.assertEqual(worker.history(job.id)["deliveries"], deliveries)

    def test_create_job_is_idempotent(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        worker = self._worker(http, FakeSmtpTransport())
        first = self._create(worker)
        second = self._create(worker)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(worker.repository.list_jobs()), 1)
        self.assertEqual(http.call_count, 0)  # 创建阶段不发送

    def test_retry_then_success_records_failed_and_sent_deliveries(self):
        http = FakeHttpTransport(
            script=[HttpResult(503, '{"errcode":-1}')],
            default_body=OK_BODY,
        )
        worker = self._worker(http, FakeSmtpTransport())
        job = self._create(worker)

        worker.process(job, now=FIXED)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.attempt_count, 1)
        self.assertEqual(job.next_attempt_at, FIXED + timedelta(seconds=60))
        self.assertEqual(job.last_error_code, "EXTERNAL_SERVICE_ERROR")
        self.assertEqual(len(worker.repository.list_deliveries(job.id)), 1)

        worker.process(job, now=FIXED + timedelta(seconds=60))
        self.assertEqual(job.status, JobStatus.SENT)
        deliveries = worker.repository.list_deliveries(job.id)
        self.assertEqual([d.status for d in deliveries],
                         [DeliveryStatus.FAILED, DeliveryStatus.SENT])
        self.assertEqual([d.attempt_no for d in deliveries], [1, 2])

    def test_exhausted_retries_end_in_failed(self):
        http = FakeHttpTransport(default_status=503, default_body='{"errcode":-1}')
        worker = self._worker(http, FakeSmtpTransport())
        job = self._create(worker)
        offsets = [0, 60, 180]
        for offset in offsets:
            worker.process(job, now=FIXED + timedelta(seconds=offset))
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.attempt_count, 3)
        self.assertIsNone(job.next_attempt_at)
        deliveries = worker.repository.list_deliveries(job.id)
        self.assertEqual(len(deliveries), 3)
        self.assertTrue(all(d.status == DeliveryStatus.FAILED for d in deliveries))

    def test_missing_credentials_fails_without_any_io(self):
        with patch.dict(os.environ, {}, clear=True):
            http = FakeHttpTransport(default_body=OK_BODY)
            worker = self._worker(http, FakeSmtpTransport())
            job = self._create(worker)
            worker.process(job, now=FIXED)
            self.assertEqual(job.status, JobStatus.FAILED)
            self.assertEqual(job.last_error_code, "CONFIG_MISSING")
            self.assertEqual(http.call_count, 0)  # 缺凭据绝不发请求
            delivery = worker.repository.list_deliveries(job.id)[0]
            self.assertEqual(delivery.status, DeliveryStatus.FAILED)
            self.assertEqual(delivery.error_code, "CONFIG_MISSING")

    def test_retry_failed_requeues_only_failed(self):
        http = FakeHttpTransport(default_status=503, default_body='{"errcode":-1}')
        worker = self._worker(http, FakeSmtpTransport())
        job = self._create(worker)
        for offset in (0, 60, 180):
            worker.process(job, now=FIXED + timedelta(seconds=offset))
        self.assertEqual(job.status, JobStatus.FAILED)

        worker.retry_failed(job.id, now=FIXED + timedelta(seconds=300))
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.attempt_count, 0)
        # 重新排队后 history 仍保留全部历史投递（追加写）
        self.assertEqual(len(worker.repository.list_deliveries(job.id)), 3)

    def test_empty_content_rejected_before_job_created(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        worker = self._worker(http, FakeSmtpTransport())
        with self.assertRaises(EmptyContentError):
            self._create(worker, content=make_content(title=""))
        self.assertEqual(len(worker.repository.list_jobs()), 0)
        self.assertEqual(http.call_count, 0)

    def test_long_content_is_segmented_into_multiple_sends(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        worker = self._worker(http, FakeSmtpTransport())
        template = make_template(max_length=40)  # 触发按字节分段
        job = self._create(worker, template=template)
        self.assertGreater(len(job.segments), 1)
        worker.process(job, now=FIXED)
        self.assertEqual(job.status, JobStatus.SENT)
        self.assertEqual(http.call_count, len(job.segments))
        for call in http.calls:
            self.assertIn("msgtype", call.body)

    def test_run_pending_processes_all_due_jobs(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        worker = self._worker(http, FakeSmtpTransport())
        self._create(worker, task_id="t1")
        self._create(worker, task_id="t2")
        results = worker.run_pending(now=FIXED)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(job.status == JobStatus.SENT for job in results))

    def test_retry_failed_on_unknown_job_raises(self):
        worker = self._worker(FakeHttpTransport(), FakeSmtpTransport())
        with self.assertRaises(NotificationError) as ctx:
            worker.retry_failed("no-such-id")
        self.assertEqual(ctx.exception.code, "RESOURCE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
