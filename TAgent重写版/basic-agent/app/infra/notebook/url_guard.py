"""网址来源的安全检查（对应原版 validate_url）：防止借服务端去访问内网（SSRF）。

只许 http/https；主机解析出来的每个地址都不能是本机、内网、链路本地、组播、保留地址。
跳转由抽取器手动跟，每一跳都重新过这里。ON_ALLOW_PRIVATE_URLS=true 可以放开（只在自己机器上用）。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.errors.notebook import InvalidInput


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(url: str, *, allow_private: bool) -> str:
    value = (url or "").strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        raise InvalidInput("只支持 http/https 网址")
    if not parts.hostname:
        raise InvalidInput("网址里没有主机名")
    if parts.username or parts.password:
        raise InvalidInput("网址里不能带用户名和密码")
    if allow_private:
        return value
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise InvalidInput("网址端口不对") from exc
    try:
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise InvalidInput("网址的主机名解析不了") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public(address) for address in addresses):
        raise InvalidInput("不允许访问本机或内网地址")
    return value
