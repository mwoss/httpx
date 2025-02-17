import sys

import pytest
import trio

from httpx import AsyncioBackend, HTTPVersionConfig, SSLConfig, TimeoutConfig
from httpx.concurrency.trio import TrioBackend


@pytest.mark.parametrize(
    "backend, get_cipher",
    [
        pytest.param(
            AsyncioBackend(),
            lambda stream: stream.stream_writer.get_extra_info("cipher", default=None),
            marks=pytest.mark.asyncio,
        ),
        pytest.param(
            TrioBackend(),
            lambda stream: (
                stream.stream.cipher()
                if isinstance(stream.stream, trio.SSLStream)
                else None
            ),
            marks=pytest.mark.trio,
        ),
    ],
)
async def test_start_tls_on_socket_stream(https_server, backend, get_cipher):
    """
    See that the concurrency backend can make a connection without TLS then
    start TLS on an existing connection.
    """
    if isinstance(backend, AsyncioBackend) and sys.version_info < (3, 7):
        pytest.xfail(reason="Requires Python 3.7+ for AbstractEventLoop.start_tls()")

    ctx = SSLConfig().load_ssl_context_no_verify(HTTPVersionConfig())
    timeout = TimeoutConfig(5)

    stream = await backend.open_tcp_stream(
        https_server.url.host, https_server.url.port, None, timeout
    )

    try:
        assert stream.is_connection_dropped() is False
        assert get_cipher(stream) is None

        stream = await backend.start_tls(stream, https_server.url.host, ctx, timeout)
        assert stream.is_connection_dropped() is False
        assert get_cipher(stream) is not None

        await stream.write(b"GET / HTTP/1.1\r\n\r\n")
        assert (await stream.read(8192, timeout)).startswith(b"HTTP/1.1 200 OK\r\n")

    finally:
        await stream.close()
