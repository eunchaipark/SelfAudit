"""시험 중 바깥 접속이 막혔는지 (pytest-socket, pyproject `--allow-hosts`)."""

from __future__ import annotations

import socket  # noqa: TID251 — 막혔는지 보는 시험이라 직접 연다

import pytest
from pytest_socket import SocketConnectBlockedError

# RFC 5737 문서용 주소: 막기가 풀려 있어도 실제 기기에 닿지 않는다
DOC_ADDRESS = ("192.0.2.1", 80)


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_common_소켓_열면_실패() -> None:
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(DOC_ADDRESS, timeout=1)
