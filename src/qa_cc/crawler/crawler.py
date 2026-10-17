"""Crawler — Non-LLM systematic exploration that produces the reference inventory for coverage calculation."""
from dataclasses import dataclass, field
import re
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from qa_cc.gateway.allowlist import is_url_allowed


@dataclass
class Inventory:
    pages: List[str] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    links: List[str] = field(default_factory=list)

    def calculate_coverage(
        self,
        exercised_urls: Set[str],
        exercised_actions: Optional[Set[str]] = None,
    ) -> float:
        """Calculate coverage ratio of exercised pages vs total discovered inventory."""
        if not self.pages:
            return 0.0
        norm_exercised = {u.rstrip("/") for u in exercised_urls}
        norm_pages = {p.rstrip("/") for p in self.pages}
        matched = sum(1 for p in norm_pages if p in norm_exercised)
        return matched / len(norm_pages)


class Crawler:
    """Explores a target site deterministically, building an Inventory of pages, forms, and links."""

    def __init__(
        self,
        fetcher: Optional[Callable[[str], str]] = None,
        allowlist: Optional[List[str]] = None,
    ):
        self.fetcher = fetcher or (lambda u: "")
        self.allowlist = allowlist or ["localhost", "127.0.0.1"]

    def _is_allowed(self, url: str) -> bool:
        return is_url_allowed(url, self.allowlist)

    def crawl(self, start_url: str, max_pages: int = 50) -> Inventory:
        visited: Set[str] = set()
        to_visit: List[str] = [start_url]
        discovered_forms: List[Dict[str, Any]] = []
        discovered_links: Set[str] = set()

        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            html = self.fetcher(current_url)
            if not html:
                continue

            # Extract links
            href_matches = re.findall(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']', html, re.IGNORECASE)
            for href in href_matches:
                if href.startswith(("#", "javascript:", "mailto:")):
                    continue
                full_url = urljoin(current_url, href)
                if self._is_allowed(full_url):
                    discovered_links.add(full_url)
                    if full_url not in visited and full_url not in to_visit:
                        to_visit.append(full_url)

            # Extract forms
            form_matches = re.finditer(r'<form\s*([^>]*)>([\s\S]*?)<\/form>', html, re.IGNORECASE)
            for fm in form_matches:
                attrs = fm.group(1)
                body = fm.group(2)
                id_match = re.search(r'id=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                action_match = re.search(r'action=["\']([^"\']+)["\']', attrs, re.IGNORECASE)

                input_names = re.findall(r'<input\s+[^>]*name=["\']([^"\']+)["\']', body, re.IGNORECASE)
                textarea_names = re.findall(r'<textarea\s+[^>]*name=["\']([^"\']+)["\']', body, re.IGNORECASE)

                form_data = {
                    "id": id_match.group(1) if id_match else "",
                    "action": action_match.group(1) if action_match else "",
                    "page": current_url,
                    "fields": input_names + textarea_names,
                }
                discovered_forms.append(form_data)

        return Inventory(
            pages=sorted(list(visited)),
            forms=discovered_forms,
            links=sorted(list(discovered_links)),
        )
