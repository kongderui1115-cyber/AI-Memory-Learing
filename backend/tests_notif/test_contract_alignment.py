"""契约一致性测试：真实从 backend/app/contracts/enums.py 文件加载冻结枚举校验。

不依赖 pydantic（未安装），通过 importlib 从文件加载 StrEnum 模块完成比对。
"""

import os
import sys
import unittest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.channels import default_registry  # noqa: E402
from app.notifications.contract_values import (  # noqa: E402
    ChannelType,
    DeliveryStatus,
    JobStatus,
    WECHAT_CHANNEL_TYPES,
    WECOM_CHANNEL_TYPES,
    assert_contract_alignment,
    frozen_channel_types,
    frozen_job_statuses,
    load_frozen_enums,
)


class ContractAlignmentTest(unittest.TestCase):
    def test_alignment_passes_against_real_enums_file(self):
        # 真实读取冻结契约文件（不是写死的期望值），不一致会 AssertionError
        assert_contract_alignment()

    def test_frozen_enums_really_loaded_from_file(self):
        module = load_frozen_enums()
        self.assertEqual(set(frozen_channel_types(module)), set(ChannelType.ALL))
        self.assertEqual(set(frozen_job_statuses(module)), set(JobStatus.ALL))
        self.assertEqual(len(ChannelType.ALL), 7)
        self.assertEqual(len(JobStatus.ALL), 5)

    def test_all_builtin_channels_registered(self):
        registry = default_registry()
        self.assertEqual(set(registry.registered_types()), set(ChannelType.ALL))
        for channel_type in ChannelType.ALL:
            channel = registry.resolve(channel_type)
            self.assertEqual(channel.channel_type, channel_type)

    def test_wechat_family_matches_fr07_paths_a_b_c_d(self):
        self.assertEqual(set(WECHAT_CHANNEL_TYPES), {
            "wecom_app",
            "wechat_official_account",
            "third_party_push",
            "wecom_webhook",
        })
        self.assertEqual(len(WECHAT_CHANNEL_TYPES), 4)
        self.assertTrue(set(WECOM_CHANNEL_TYPES) <= set(ChannelType.ALL))

    def test_delivery_status_matches_contract_literal(self):
        self.assertEqual(set(DeliveryStatus.ALL), {"sending", "sent", "failed"})


if __name__ == "__main__":
    unittest.main()
