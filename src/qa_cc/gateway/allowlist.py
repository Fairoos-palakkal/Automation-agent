"""Exact-host URL allowlist validator for ToolGateway and Crawler (T-02)."""
from typing import Sequence, Tuple, Optional
from urllib.parse import urlsplit


def parse_allowlist_entry(entry: str) -> Tuple[str, Optional[int]]:
    """Parse an allowlist entry into normalized (hostname, optional_port)."""
    entry = entry.strip()
    if entry.startswith("http://") or entry.startswith("https://"):
        parts = urlsplit(entry)
        host = (parts.hostname or "").lower().rstrip(".")
        return host, parts.port

    if ":" in entry and not entry.startswith("["):
        host, _, port_str = entry.partition(":")
        host = host.lower().rstrip(".")
        port = int(port_str) if port_str.isdigit() else None
        return host, port

    return entry.lower().rstrip("."), None


def is_url_allowed(url: str, allowlist: Sequence[str]) -> bool:
    """Validate if target URL strictly matches an exact host or host:port in the allowlist.

    Enforces:
    - Scheme must be http or https
    - No userinfo (username / password tricks)
    - Exact hostname match (case-insensitive, trailing dots normalized)
    - Exact port match when allowlist specifies a port
    - Rejects lookalike hosts (e.g. localhost.evil.com) and query/path substring tricks
    """
    if not url or not allowlist:
        return False

    try:
        parts = urlsplit(url)
    except Exception:
        return False

    # 1. Scheme validation
    if parts.scheme.lower() not in ("http", "https"):
        return False

    # 2. Reject userinfo tricks (e.g., http://localhost@evil.com)
    if parts.username or parts.password:
        return False

    # 3. Hostname extraction & normalization
    raw_hostname = parts.hostname
    if not raw_hostname:
        return False
    hostname = raw_hostname.lower().rstrip(".")

    url_port = parts.port

    # 4. Check against allowlist entries
    for entry in allowlist:
        if not entry:
            continue
        allowed_host, allowed_port = parse_allowlist_entry(entry)

        if not allowed_host:
            continue

        if hostname != allowed_host:
            continue

        # If allowlist entry specifies a port, it must match the URL port
        if allowed_port is not None:
            effective_url_port = url_port if url_port is not None else (80 if parts.scheme == "http" else 443)
            if effective_url_port != allowed_port:
                continue

        return True

    return False
