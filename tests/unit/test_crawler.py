"""Tests for Crawler — Phase 1.7 (Red -> Green)."""
import pytest
from qa_cc.crawler.crawler import Crawler, Inventory


# Deterministic mock site map for unit tests
MOCK_SITE = {
    "http://localhost:3000/": """
        <html>
            <body>
                <a href="/catalog.html">Catalog</a>
                <a href="/contact.html">Contact</a>
                <a href="https://external-tracker.com">External</a>
            </body>
        </html>
    """,
    "http://localhost:3000/catalog.html": """
        <html>
            <body>
                <a href="/cart.html">Cart</a>
                <form id="search-form" action="/search">
                    <input name="q" type="text"/>
                    <button type="submit">Search</button>
                </form>
            </body>
        </html>
    """,
    "http://localhost:3000/contact.html": """
        <html>
            <body>
                <form id="contact-form" action="/submit">
                    <input name="email" type="email"/>
                    <textarea name="msg"></textarea>
                </form>
            </body>
        </html>
    """,
    "http://localhost:3000/cart.html": """
        <html>
            <body>
                <a href="/">Home</a>
            </body>
        </html>
    """,
}


def mock_fetcher(url: str) -> str:
    return MOCK_SITE.get(url, "<html><body>404</body></html>")


class TestCrawler:
    def test_crawler_discovers_pages(self):
        """Crawler recursively discovers all internal pages on the target site."""
        crawler = Crawler(fetcher=mock_fetcher, allowlist=["localhost:3000"])
        inventory = crawler.crawl("http://localhost:3000/")

        assert isinstance(inventory, Inventory)
        assert "http://localhost:3000/" in inventory.pages
        assert "http://localhost:3000/catalog.html" in inventory.pages
        assert "http://localhost:3000/contact.html" in inventory.pages
        assert "http://localhost:3000/cart.html" in inventory.pages

    def test_crawler_discovers_forms(self):
        """Crawler extracts form elements and their input fields into the inventory."""
        crawler = Crawler(fetcher=mock_fetcher, allowlist=["localhost:3000"])
        inventory = crawler.crawl("http://localhost:3000/")

        forms = inventory.forms
        assert len(forms) >= 2
        form_ids = [f["id"] for f in forms if "id" in f]
        assert "search-form" in form_ids
        assert "contact-form" in form_ids

    def test_crawler_discovers_links(self):
        """Crawler discovers internal links and filters out disallowed/external links."""
        crawler = Crawler(fetcher=mock_fetcher, allowlist=["localhost:3000"])
        inventory = crawler.crawl("http://localhost:3000/")

        assert any("catalog.html" in link for link in inventory.links)
        # External domain must NOT be in internal links
        assert not any("external-tracker.com" in link for link in inventory.links)

    def test_crawler_coverage_calculation(self):
        """Calculates ratio of exercised pages vs total inventory pages."""
        inventory = Inventory(
            pages=["http://localhost:3000/", "http://localhost:3000/catalog.html", "http://localhost:3000/contact.html", "http://localhost:3000/cart.html"],
            forms=[{"id": "f1"}],
            links=["http://localhost:3000/catalog.html"],
        )
        exercised = {"http://localhost:3000/", "http://localhost:3000/catalog.html"}
        coverage = inventory.calculate_coverage(exercised_urls=exercised)

        assert pytest.approx(coverage, 0.01) == 0.50  # 2 of 4 pages
