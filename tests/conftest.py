"""birth 单测默认走 stub 开口，避免依赖 OpenCode/网络。"""

import pytest

from birth.articulate import set_stub_mode


@pytest.fixture(autouse=True)
def _birth_stub_articulate():
    set_stub_mode(True)
    yield
    set_stub_mode(True)
