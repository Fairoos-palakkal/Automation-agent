"""HTTP tool — safe HTTP client for API testing and evidence capture (Phase 2.4)."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional
import urllib.error
import urllib.request

from qa_cc.verdict.evidence import Evidence, EvidenceType


class HttpTool:
    """Carries out HTTP requests and returns response data with Evidence."""

    def __init__(self, requester: Optional[Callable[..., Any]] = None):
        self.requester = requester

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request and format response + evidence."""
        method = method.upper()
        req_headers = headers or {}

        if self.requester:
            resp = self.requester(method=method, url=url, headers=req_headers, body=body)
            status_code = getattr(resp, "status_code", 200)
            text = getattr(resp, "text", "")
            resp_headers = dict(getattr(resp, "headers", {}))
        else:
            data = None
            if body is not None:
                if isinstance(body, (dict, list)):
                    data = json.dumps(body).encode("utf-8")
                    if "content-type" not in [k.lower() for k in req_headers]:
                        req_headers["Content-Type"] = "application/json"
                elif isinstance(body, str):
                    data = body.encode("utf-8")
                elif isinstance(body, bytes):
                    data = body

            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status_code = response.status
                    text = response.read().decode("utf-8", errors="replace")
                    resp_headers = dict(response.headers)
            except urllib.error.HTTPError as e:
                status_code = e.code
                text = e.read().decode("utf-8", errors="replace")
                resp_headers = dict(e.headers)
            except Exception as e:
                status_code = 599
                text = f"Network/Connection error: {e}"
                resp_headers = {}

        evidence_content = (
            f"REQUEST: {method} {url}\n"
            f"HEADERS: {json.dumps(req_headers)}\n"
            f"BODY: {body}\n\n"
            f"RESPONSE STATUS: {status_code}\n"
            f"RESPONSE HEADERS: {json.dumps(resp_headers)}\n"
            f"RESPONSE BODY: {text}"
        )

        evidence = Evidence(
            type=EvidenceType.NETWORK_REQUEST,
            content=evidence_content,
            metadata={
                "method": method,
                "url": url,
                "status_code": status_code,
            },
        )

        return {
            "status_code": status_code,
            "headers": resp_headers,
            "body": text,
            "evidence": evidence,
        }
