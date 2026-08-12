#!/usr/bin/env python3
"""Two WebTransport clients against the Godot server, to exercise its roster.

    python roster_client.py --port 54370 --clients 2

Point it at `fabric-godot-core`'s `modules/http3/demo/wt_server_demo.gd`, which is the Godot
side serving. This is the half that has to be somebody else's implementation: a Godot client
against a Godot server agrees with itself about anything both ends get wrong, and the two would
pass each other's tests while failing a browser. aioquic is the second opinion.

What it is for is the part a single connection cannot show. `WebTransportPeer` kept its clients
in one bool until now, so everything worked with one client and the second was invisible: the
roster, `peer_connected` per session, and a disconnect that drops one client instead of the
server all need two sessions in the room at once.

The certificate is checked against nothing. The server builds a fresh self-signed P-256 cert on
every run, so there is no trust chain to check against and pretending otherwise would only mean
pinning a hash that changes every time the server restarts. This talks to localhost, on a port
it was told, for a test.
"""

import argparse
import asyncio
import ssl
import sys

from aioquic.asyncio.client import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DatagramReceived, HeadersReceived, WebTransportStreamDataReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated, QuicEvent


class WebTransportClient(QuicConnectionProtocol):
    """One WebTransport session, opened with an Extended CONNECT."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = H3Connection(self._quic, enable_webtransport=True)
        self._session_id = None
        self._ready = asyncio.Event()
        self.received = []
        self.terminated = asyncio.Event()

    def connect_session(self, authority: str, path: str) -> None:
        self._session_id = self._quic.get_next_available_stream_id(is_unidirectional=False)
        self._http.send_headers(
            stream_id=self._session_id,
            headers=[
                (b":method", b"CONNECT"),
                (b":protocol", b"webtransport"),
                (b":scheme", b"https"),
                (b":authority", authority.encode()),
                (b":path", path.encode()),
                (b"origin", authority.encode()),
            ],
            end_stream=False,
        )
        self.transmit()

    async def wait_ready(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def send_datagram(self, payload: bytes) -> None:
        self._http.send_datagram(self._session_id, payload)
        self.transmit()

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, ConnectionTerminated):
            # The server closing one session must reach only that client. A run where every
            # client sees this at once is the bug the roster was written to remove.
            self.terminated.set()
            return
        for h3_event in self._http.handle_event(event):
            if isinstance(h3_event, HeadersReceived):
                status = dict(h3_event.headers).get(b":status", b"")
                if status == b"200":
                    self._ready.set()
                else:
                    print(f"  CONNECT refused: :status={status.decode() or '(none)'}")
            elif isinstance(h3_event, (DatagramReceived, WebTransportStreamDataReceived)):
                self.received.append(h3_event.data)


async def one_client(index: int, host: str, port: int, path: str, hold: float) -> bool:
    config = QuicConfiguration(alpn_protocols=H3_ALPN, is_client=True)
    # See the module docstring: a fresh self-signed cert per run has no chain to verify.
    config.verify_mode = ssl.CERT_NONE

    async with connect(host, port, configuration=config,
                       create_protocol=WebTransportClient) as client:
        client.connect_session(f"{host}:{port}", path)
        if not await client.wait_ready(10.0):
            print(f"client {index}: no WebTransport session")
            return False
        print(f"client {index}: session open")

        client.send_datagram(f"hello from client {index}".encode())

        # Hold the session open. The point of the second client is to still be here when the
        # first one leaves, so it has to outlive it.
        try:
            await asyncio.wait_for(client.terminated.wait(), hold)
            print(f"client {index}: server closed the session")
        except asyncio.TimeoutError:
            print(f"client {index}: still connected after {hold:.0f}s, closing")
        print(f"client {index}: received {len(client.received)} message(s)")
        return True


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=54370)
    ap.add_argument("--path", default="/wt")
    ap.add_argument("--clients", type=int, default=2)
    ap.add_argument("--hold", type=float, default=15.0,
                    help="seconds to keep each session open")
    ap.add_argument("--stagger", type=float, default=1.0,
                    help="seconds between connections, so the server's joins are distinguishable")
    args = ap.parse_args()

    async def staggered(i: int) -> bool:
        # Connect one at a time. Simultaneous joins would still be two peers, but the server's
        # log would not say which id belongs to which client, and that is the thing under test.
        await asyncio.sleep(i * args.stagger)
        return await one_client(i + 1, args.host, args.port, args.path, args.hold)

    results = await asyncio.gather(*(staggered(i) for i in range(args.clients)),
                                   return_exceptions=True)
    ok = sum(1 for r in results if r is True)
    for r in results:
        if isinstance(r, BaseException):
            print(f"client raised: {r!r}")
    print(f"{ok} of {args.clients} clients got a session")
    return 0 if ok == args.clients else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
