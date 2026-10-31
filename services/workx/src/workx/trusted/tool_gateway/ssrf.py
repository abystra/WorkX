"""SSRF guard for the web_fetch tool (Part 4 §8, Part 13): only public http(s) addresses, checked after DNS
resolution and again on every redirect hop."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


class BlockedUrl(Exception):
    pass


def check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedUrl("Only http and https URLs are allowed.")
    if parsed.username or parsed.password:
        raise BlockedUrl("URLs with credentials are not allowed.")
    host = parsed.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".local") or host == "localhost":
        raise BlockedUrl("This host is not allowed.")
    try:
        infos = socket.getaddrinfo(
            host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise BlockedUrl("The host could not be resolved.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
            or (
                isinstance(address, ipaddress.IPv6Address)
                and address.ipv4_mapped is not None
                and not address.ipv4_mapped.is_global
            )
        ):
            raise BlockedUrl("Private, loopback and link-local addresses are not allowed.")
    return url
