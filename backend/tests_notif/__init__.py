"""通知模块测试包：把 backend 加入 sys.path，保证 app.notifications 可导入。

运行方式（从 worktree 根目录）：
    python -m unittest discover -s backend/tests_notif -v
"""

import os
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
