"""One-shot startup network probe — tells us WHY the bot can't reach Telegram.

Logs reachability of Telegram vs a control host, and whether forcing IPv4 helps.
Safe to keep: it only logs. Remove once connectivity is confirmed stable.
"""

import logging
import socket
import time

import httpx

log = logging.getLogger("app.diag")

TARGETS = {
    "telegram": "https://api.telegram.org",
    "gemini": "https://generativelanguage.googleapis.com",
    "control": "https://example.com",
}


async def _try(name: str, url: str, *, ipv4_only: bool) -> None:
    label = f"{name}{' (ipv4)' if ipv4_only else ''}"
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0") if ipv4_only else None
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            r = await client.get(url)
        log.info("PROBE %s -> HTTP %s in %.1fs", label, r.status_code, time.monotonic() - started)
    except Exception as e:
        log.warning("PROBE %s -> FAIL (%.1fs): %r", label, time.monotonic() - started, e)


def _dns(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        fams = {("IPv6" if i[0] == socket.AF_INET6 else "IPv4") for i in infos}
        addrs = sorted({i[4][0] for i in infos})
        log.info("PROBE dns %s -> %s %s", host, sorted(fams), addrs[:4])
    except Exception as e:
        log.warning("PROBE dns %s -> FAIL: %r", host, e)


async def run_probe() -> None:
    log.info("=== network probe start ===")
    _dns("api.telegram.org")
    for name, url in TARGETS.items():
        await _try(name, url, ipv4_only=False)
    # If default failed due to IPv6, forcing the local bind to an IPv4 address helps
    await _try("telegram", TARGETS["telegram"], ipv4_only=True)
    log.info("=== network probe end ===")
