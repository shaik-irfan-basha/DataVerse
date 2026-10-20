"""
tests/test_product_site.py - Verification of Product Website Pages, SEO, GA4, GSC, and Formspree Integration
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_SITE_DIR = REPO_ROOT / "product-site"
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_SITE_DIR = FRONTEND_DIR / "site"

VERIFIED_SHA256 = "61B41EA7B62CDBBDF1E70839D93A57D316175984888BBED710BF106858A5BBC7"
GA4_ID = "G-H7BHJ4W523"
GSC_TAG = "N_0YgkrZaG-GsiVOXh9qH1raQb7GiT2dQWYxhd4t444"
FORMSPREE_ENDPOINT = "https://formspree.io/f/xzedwwlv"

EXPECTED_PAGES = [
    "index.html",
    "demo.html",
    "features.html",
    "download.html",
    "docs.html",
    "faq.html",
    "support.html",
    "privacy.html",
    "release-notes.html",
]


def test_product_site_directory_structure():
    """Verify all core pages and assets exist in product-site/ and frontend/site/."""
    assert PRODUCT_SITE_DIR.exists()
    assert FRONTEND_SITE_DIR.exists()

    for page in EXPECTED_PAGES:
        file_path = PRODUCT_SITE_DIR / page
        assert file_path.exists(), f"Missing page: {page}"
        mirror_path = FRONTEND_SITE_DIR / page
        assert mirror_path.exists(), f"Missing mirrored page in frontend/site/: {page}"

    assert (PRODUCT_SITE_DIR / "robots.txt").exists()
    assert (PRODUCT_SITE_DIR / "sitemap.xml").exists()
    assert (PRODUCT_SITE_DIR / "google9c2dd5fcd8e18414.html").exists()
    assert (PRODUCT_SITE_DIR / "css" / "main.css").exists()
    assert (PRODUCT_SITE_DIR / "css" / "components.css").exists()
    assert (PRODUCT_SITE_DIR / "css" / "responsive.css").exists()
    assert (PRODUCT_SITE_DIR / "js" / "main.js").exists()
    assert (PRODUCT_SITE_DIR / "js" / "analytics.js").exists()
    assert (PRODUCT_SITE_DIR / "js" / "support-form.js").exists()

    # Verify root frontend assets for search engines
    assert (FRONTEND_DIR / "robots.txt").exists()
    assert (FRONTEND_DIR / "sitemap.xml").exists()
    assert (FRONTEND_DIR / "google9c2dd5fcd8e18414.html").exists()


def test_google_site_verification_token():
    """Ensure Google Search Console verification file and meta tag exist."""
    # HTML verification file
    gsc_file = PRODUCT_SITE_DIR / "google9c2dd5fcd8e18414.html"
    assert gsc_file.exists()
    assert "google-site-verification: google9c2dd5fcd8e18414.html" in gsc_file.read_text(encoding="utf-8")

    # Meta tag in product-site/index.html
    index_html = (PRODUCT_SITE_DIR / "index.html").read_text(encoding="utf-8")
    assert GSC_TAG in index_html


def test_google_analytics_integration():
    """Ensure GA4 tracking is referenced across all product site pages and frontend."""
    # Check JS module
    analytics_js = (PRODUCT_SITE_DIR / "js" / "analytics.js").read_text(encoding="utf-8")
    assert GA4_ID in analytics_js
    assert "anonymize_ip: true" in analytics_js
    assert "window.__dv_ga_initialized" in analytics_js

    # Check that pages import analytics.js
    for page in EXPECTED_PAGES:
        html = (PRODUCT_SITE_DIR / page).read_text(encoding="utf-8")
        assert "js/analytics.js" in html, f"Missing analytics in {page}"

    # Check frontend/index.html also includes GA4 with anonymize_ip
    frontend_html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    assert GA4_ID in frontend_html
    assert "'anonymize_ip': true" in frontend_html
    assert GSC_TAG in frontend_html


def test_formspree_integration():
    """Ensure Formspree endpoint and configuration are correctly defined without PII leaks."""
    # Check JS handler
    handler_js = (PRODUCT_SITE_DIR / "js" / "support-form.js").read_text(encoding="utf-8")
    assert FORMSPREE_ENDPOINT in handler_js

    # Check support.html form
    support_html = (PRODUCT_SITE_DIR / "support.html").read_text(encoding="utf-8")
    assert FORMSPREE_ENDPOINT in support_html
    assert 'name="_gotcha"' in support_html
    assert 'id="support-form"' in support_html
    assert 'id="btn-submit-support"' in support_html

    # Invariant: analytics tracking must only pass coarse category, never message or email content
    assert "trackSupportSubmitted(categoryVal)" in handler_js


def test_verified_installer_checksum_in_pages():
    """Ensure verified SHA-256 hash is accurately reported on download and release notes pages and size displays are omitted."""
    # Check product-site
    download_html = (PRODUCT_SITE_DIR / "download.html").read_text(encoding="utf-8")
    assert VERIFIED_SHA256 in download_html
    assert "796 MB" not in download_html
    assert "796,164,310" not in download_html

    release_html = (PRODUCT_SITE_DIR / "release-notes.html").read_text(encoding="utf-8")
    assert VERIFIED_SHA256 in release_html
    assert "v1.0.0" in release_html
    assert "796 MB" not in release_html
    assert "796,164,310" not in release_html

    # Check frontend/site mirror
    frontend_dl = (FRONTEND_SITE_DIR / "download.html").read_text(encoding="utf-8")
    assert VERIFIED_SHA256 in frontend_dl
    assert "796 MB" not in frontend_dl
    assert "796,164,310" not in frontend_dl

    frontend_rel = (FRONTEND_SITE_DIR / "release-notes.html").read_text(encoding="utf-8")
    assert VERIFIED_SHA256 in frontend_rel
    assert "796 MB" not in frontend_rel
    assert "796,164,310" not in frontend_rel


def test_root_and_studio_routing_and_ctas():
    """Ensure demo page CTA points to /site/demo/studio/ and FastAPI routes serve marketing at /, studio at /studio/, and nested demo studio at /site/demo/studio/."""
    from starlette.testclient import TestClient
    from backend.app import app

    client = TestClient(app)

    # 1. Root browser request (Accept: text/html) -> Marketing website
    res_root = client.get("/", headers={"accept": "text/html"})
    assert res_root.status_code == 200
    assert "Ask your data in plain English" in res_root.text
    assert 'id="app-container"' not in res_root.text

    # 2. Studio route -> Web Studio application shell
    res_studio = client.get("/studio/", headers={"accept": "text/html"})
    assert res_studio.status_code == 200
    assert 'id="app-container"' in res_studio.text

    # 3. Studio route without slash
    res_studio_no_slash = client.get("/studio", headers={"accept": "text/html"})
    assert res_studio_no_slash.status_code == 200
    assert 'id="app-container"' in res_studio_no_slash.text

    # 4. /site/ route continues to serve marketing site
    res_site = client.get("/site/")
    assert res_site.status_code == 200
    assert "Ask your data in plain English" in res_site.text

    # 5. Nested demo studio route -> Web Studio application shell
    res_nested = client.get("/site/demo/studio/", headers={"accept": "text/html"})
    assert res_nested.status_code == 200
    assert 'id="app-container"' in res_nested.text

    # 6. Nested demo studio route without slash
    res_nested_no_slash = client.get("/site/demo/studio", headers={"accept": "text/html"})
    assert res_nested_no_slash.status_code == 200
    assert 'id="app-container"' in res_nested_no_slash.text

    # 7. Demo page Launch CTA points to /site/demo/studio/
    demo_html = (FRONTEND_SITE_DIR / "demo.html").read_text(encoding="utf-8")
    assert 'href="/site/demo/studio/"' in demo_html
    assert 'id="btn-launch-studio-direct"' in demo_html
    assert "796 MB" not in demo_html

    product_demo = (PRODUCT_SITE_DIR / "demo.html").read_text(encoding="utf-8")
    assert 'href="/site/demo/studio/"' in product_demo


def test_factual_benchmark_claims_not_spider():
    """Verify that benchmark claims accurately describe the 55-case Semantic Evaluation Suite rather than Spider 1.0."""
    features_html = (PRODUCT_SITE_DIR / "features.html").read_text(encoding="utf-8")
    assert "Spider" not in features_html
    assert "55-Case Semantic Evaluation Suite Results" in features_html
    assert "82.9%" in features_html
    assert "94.3%" in features_html

    release_html = (PRODUCT_SITE_DIR / "release-notes.html").read_text(encoding="utf-8")
    assert "Spider" not in release_html
    assert "Verified Semantic Evaluation Benchmark Performance" in release_html

    faq_html = (PRODUCT_SITE_DIR / "faq.html").read_text(encoding="utf-8")
    assert "Spider" not in faq_html
    assert "82.9% Semantic Benchmark" in faq_html


def test_sitemap_covers_all_pages():
    """Ensure sitemap.xml includes all 9 pages with valid XML syntax."""
    sitemap = (PRODUCT_SITE_DIR / "sitemap.xml").read_text(encoding="utf-8")
    for page in EXPECTED_PAGES:
        loc = f"https://dataverse-studio.netlify.app/{page if page != 'index.html' else ''}"
        assert loc in sitemap, f"Missing {loc} in sitemap"


def test_robots_txt_references_sitemap():
    """Ensure robots.txt allows crawling and points to sitemap."""
    robots = (PRODUCT_SITE_DIR / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Sitemap: https://dataverse-studio.netlify.app/sitemap.xml" in robots
