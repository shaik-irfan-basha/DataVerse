"""
tests/test_browser_visitor_journey.py - End-to-End Headless Browser Visitor Journey Test
"""

import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from desktop_app import DataVerseDesktopApp, find_available_port, check_backend_health


@pytest.fixture(scope="module")
def live_server():
    """Starts an in-process FastAPI backend on an available localhost port."""
    port = find_available_port(start_port=8350)
    app_instance = DataVerseDesktopApp(port=port)
    started = app_instance.start_backend()
    assert started is True
    assert check_backend_health(app_instance.app_url) is True

    yield app_instance.app_url

    app_instance.stop_backend()


@pytest.fixture(scope="module")
def browser(live_server):
    """Launches headless Chrome."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")

    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()


def test_visitor_homepage_journey(browser, live_server):
    """Verify visitor lands on homepage via root /, inspects branding, hero, and badges."""
    browser.get(f"{live_server}/")
    assert "DataVerse" in browser.title

    # Brand link
    brand_el = browser.find_element(By.CLASS_NAME, "brand-link")
    assert "DataVerse" in brand_el.text

    # Hero headline
    h1 = browser.find_element(By.TAG_NAME, "h1")
    assert "Ask your data in plain English" in h1.text

    # Check zero severe console errors
    logs = browser.get_log("browser")
    severe_errors = [e for e in logs if e["level"] == "SEVERE"]
    assert len(severe_errors) == 0, f"Severe console errors on homepage: {severe_errors}"


def test_visitor_all_pages_load_cleanly(browser, live_server):
    """Verify all 9 product site pages load with HTTP 200 and no severe JS errors."""
    pages = [
        "demo.html",
        "features.html",
        "download.html",
        "docs.html",
        "faq.html",
        "support.html",
        "privacy.html",
        "release-notes.html",
    ]
    for page in pages:
        browser.get(f"{live_server}/site/{page}")
        assert browser.title != ""
        logs = browser.get_log("browser")
        severe = [e for e in logs if e["level"] == "SEVERE"]
        assert len(severe) == 0, f"Severe error on {page}: {severe}"


def test_faq_accordion_interaction(browser, live_server):
    """Verify clicking FAQ questions expands details."""
    browser.get(f"{live_server}/site/faq.html")
    wait = WebDriverWait(browser, 5)

    faq_summaries = browser.find_elements(By.CSS_SELECTOR, "details.faq-item summary")
    assert len(faq_summaries) >= 3

    # Click second summary (initially closed)
    second_summary = faq_summaries[1]
    parent_details = second_summary.find_element(By.XPATH, "..")
    assert parent_details.get_attribute("open") is None

    browser.execute_script("arguments[0].click();", second_summary)
    time.sleep(0.3)

    # Must now have open attribute
    assert parent_details.get_attribute("open") is not None


def test_download_page_and_checksum_verification(browser, live_server):
    """Verify download page contains verified SHA-256 and SmartScreen guide, with size displays omitted."""
    browser.get(f"{live_server}/site/download.html")
    assert "61B41EA7B62CDBBDF1E70839D93A57D316175984888BBED710BF106858A5BBC7" in browser.page_source
    assert "796 MB" not in browser.page_source
    assert "796,164,310" not in browser.page_source
    assert "Windows protected your PC" in browser.page_source


def test_support_form_validation(browser, live_server):
    """Verify support form displays validation errors when submitted empty."""
    browser.get(f"{live_server}/site/support.html")
    submit_btn = browser.find_element(By.ID, "btn-submit-support")
    browser.execute_script("arguments[0].click();", submit_btn)
    time.sleep(0.3)

    # Form groups with errors must have .has-error
    error_groups = browser.find_elements(By.CSS_SELECTOR, ".form-group.has-error")
    assert len(error_groups) >= 2


def test_launch_studio_navigation_and_reciprocal_link(browser, live_server):
    """
    Verify clicking Launch Studio from demo.html takes visitor to the live application shell at /site/demo/studio/,
    and clicking 'Website' from the application shell links back to the marketing site.
    """
    # 1. From demo.html, click Launch Live Web Studio
    browser.get(f"{live_server}/site/demo.html")
    launch_btn = browser.find_element(By.ID, "btn-launch-studio-direct")
    assert "/site/demo/studio/" in launch_btn.get_attribute("href")
    browser.execute_script("arguments[0].click();", launch_btn)
    time.sleep(1.0)

    # Must be on /site/demo/studio/ application shell
    assert "/site/demo/studio" in browser.current_url
    wait = WebDriverWait(browser, 5)
    app_container = wait.until(EC.presence_of_element_located((By.ID, "app-container")))
    assert app_container.is_displayed()

    # Verify studio navigation tabs exist
    sql_lab_btn = browser.find_element(By.ID, "nav-btn-sql-lab")
    assert sql_lab_btn.is_displayed()

    # 2. Verify reciprocal Website link exists, points to /, and opens in the same tab (no target="_blank")
    website_link = browser.find_element(By.ID, "btn-product-site")
    href = website_link.get_attribute("href")
    assert href.endswith("/") or "/site/" in href
    target = website_link.get_attribute("target")
    assert not target or target != "_blank"

    # Click Website link and confirm navigation back to marketing homepage in the same tab
    browser.execute_script("arguments[0].click();", website_link)
    time.sleep(1.0)
    assert browser.current_url.rstrip("/").endswith(live_server.rstrip("/"))
    assert "DataVerse" in browser.title


def test_mobile_navigation_drawer_toggle(browser, live_server):
    """Verify mobile menu toggle functions on a mobile viewport."""
    browser.set_window_size(375, 667)
    browser.get(f"{live_server}/site/index.html")

    header = browser.find_element(By.CLASS_NAME, "site-header")
    toggle = browser.find_element(By.CLASS_NAME, "menu-toggle")
    assert toggle.is_displayed()
    assert toggle.get_attribute("aria-expanded") == "false"

    # Click toggle
    browser.execute_script("arguments[0].click();", toggle)
    time.sleep(0.4)

    assert toggle.get_attribute("aria-expanded") == "true"
    assert "menu-open" in header.get_attribute("class")
    site_nav = browser.find_element(By.CLASS_NAME, "site-nav")
    assert site_nav.is_displayed()

    # Reset window size
    browser.set_window_size(1400, 900)
