"""HTTP tool — safe HTTP client for API testing and evidence capture (Phase 2.4)."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from qa_cc.gateway.allowlist import is_url_allowed
from qa_cc.gateway.gateway import TargetNotAllowed
from qa_cc.verdict.evidence import Evidence, EvidenceType


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevents automatic redirect following so each hop can be inspected."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpTool:
    """Carries out HTTP requests and returns response data with Evidence."""

    def __init__(
        self,
        requester: Optional[Callable[..., Any]] = None,
        allowlist: Optional[List[str]] = None,
        max_redirects: int = 5,
        max_body_bytes: int = 256 * 1024,
    ):
        self.requester = requester
        self.allowlist = allowlist or ["localhost", "127.0.0.1"]
        self.max_redirects = max_redirects
        self.max_body_bytes = max_body_bytes

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request and format response + evidence."""
        if not is_url_allowed(url, self.allowlist):
            raise TargetNotAllowed(f"Target URL '{url}' is not permitted by allowlist: {self.allowlist}")

        current_url = url
        current_method = method.upper()
        current_headers = dict(headers or {})
        current_body = body
        hops = 0

        while True:
            if self.requester:
                resp = self.requester(
                    method=current_method,
                    url=current_url,
                    headers=current_headers,
                    body=current_body,
                )
                status_code = getattr(resp, "status_code", 200)
                text = getattr(resp, "text", "")
                resp_headers = dict(getattr(resp, "headers", {}))
            else:
                data = None
                if current_body is not None:
                    if isinstance(current_body, (dict, list)):
                        data = json.dumps(current_body).encode("utf-8")
                        if "content-type" not in [k.lower() for k in current_headers]:
                            current_headers["Content-Type"] = "application/json"
                    elif isinstance(current_body, str):
                        data = current_body.encode("utf-8")
                        if "content-type" not in [k.lower() for k in current_headers]:
                            stripped = current_body.strip()
                            if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
                                current_headers["Content-Type"] = "application/json"
                    elif isinstance(current_body, bytes):
                        data = current_body

                req = urllib.request.Request(
                    current_url,
                    data=data,
                    headers=current_headers,
                    method=current_method,
                )
                opener = urllib.request.build_opener(NoRedirectHandler)
                try:
                    with opener.open(req, timeout=10) as response:
                        status_code = response.status
                        raw = response.read(self.max_body_bytes + 1)
                        text = raw.decode("utf-8", errors="replace")
                        resp_headers = dict(response.headers)
                except urllib.error.HTTPError as e:
                    status_code = e.code
                    raw = e.read(self.max_body_bytes + 1)
                    text = raw.decode("utf-8", errors="replace")
                    resp_headers = dict(e.headers)
                except Exception as e:
                    status_code = 599
                    text = f"Network/Connection error: {e}"
                    resp_headers = {}

            # Inspect redirects
            if status_code in (301, 302, 303, 307, 308):
                location = None
                for k, v in resp_headers.items():
                    if k.lower() == "location":
                        location = v
                        break
                if location:
                    new_url = urllib.parse.urljoin(current_url, location)
                    if not is_url_allowed(new_url, self.allowlist):
                        raise TargetNotAllowed(
                            f"Redirect target '{new_url}' is not permitted by allowlist: {self.allowlist}"
                        )
                    if hops >= self.max_redirects:
                        raise RuntimeError(f"Exceeded maximum redirect hops ({self.max_redirects})")

                    hops += 1
                    current_url = new_url
                    if status_code in (302, 303):
                        current_method = "GET"
                        current_body = None
                    continue

            # Cap response body
            raw_encoded = text.encode("utf-8")
            if len(raw_encoded) > self.max_body_bytes:
                text = raw_encoded[:self.max_body_bytes].decode("utf-8", errors="ignore") + "\n[TRUNCATED: Exceeded 256 KB limit]"

            break

        evidence_content = (
            f"REQUEST: {current_method} {current_url}\n"
            f"HEADERS: {json.dumps(current_headers)}\n"
            f"BODY: {current_body}\n\n"
            f"RESPONSE STATUS: {status_code}\n"
            f"RESPONSE HEADERS: {json.dumps(resp_headers)}\n"
            f"RESPONSE BODY: {text}"
        )

        evidence = Evidence(
            type=EvidenceType.NETWORK_REQUEST,
            content=evidence_content,
            metadata={
                "method": current_method,
                "url": current_url,
                "status_code": status_code,
                "hops": hops,
            },
        )

        return {
            "status_code": status_code,
            "headers": resp_headers,
            "body": text,
            "evidence": evidence,
        }
