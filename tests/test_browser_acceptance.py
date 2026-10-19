"""
tests/test_browser_acceptance.py - Automated Headless Browser Acceptance Test for DataVerse
"""

import os
import time
import tempfile
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


@pytest.fixture(scope="module")
def driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")

    drv = webdriver.Chrome(options=options)
    drv.get("http://127.0.0.1:8000/")
    yield drv
    drv.quit()


def test_browser_page_load_and_branding(driver):
    """Verifies that the page loads with exact 'DataVerse' title and zero console errors."""
    assert driver.title == "DataVerse"

    # Verify top navigation branding
    brand_el = driver.find_element(By.CLASS_NAME, "brand")
    assert "DataVerse" in brand_el.text

    # Check for JavaScript errors in console
    logs = driver.get_log("browser")
    severe_errors = [entry for entry in logs if entry["level"] == "SEVERE"]
    assert len(severe_errors) == 0, f"Severe console errors found: {severe_errors}"


def test_browser_studio_navigation(driver):
    """Verifies smooth tab switching between SQL Lab, Clarification Engine, and Insights."""
    wait = WebDriverWait(driver, 5)

    # 1. Switch to Clarification Engine
    btn_ce = wait.until(EC.element_to_be_clickable((By.ID, "nav-btn-clarification")))
    btn_ce.click()
    time.sleep(0.3)

    view_ce = driver.find_element(By.ID, "studio-view-clarification")
    assert view_ce.is_displayed()
    assert "active" in view_ce.get_attribute("class")

    # Verify welcome card and quick chips exist in stream
    welcome_chips = driver.find_elements(By.CSS_SELECTOR, ".ce-welcome-chips .ce-option-chip")
    assert len(welcome_chips) >= 2
    chip_texts = [chip.text for chip in welcome_chips]
    assert any("Analyze missing values" in t for t in chip_texts)
    assert any("Check duplicate rows" in t for t in chip_texts)

    # 2. Switch to Insights Studio
    btn_insights = wait.until(EC.element_to_be_clickable((By.ID, "nav-btn-insights")))
    btn_insights.click()
    time.sleep(0.3)

    view_insights = driver.find_element(By.ID, "studio-view-insights")
    assert view_insights.is_displayed()

    # 3. Switch back to SQL Lab
    btn_sql = wait.until(EC.element_to_be_clickable((By.ID, "nav-btn-sql-lab")))
    btn_sql.click()
    time.sleep(0.3)

    view_sql = driver.find_element(By.ID, "studio-view-sql-lab")
    assert view_sql.is_displayed()


def test_browser_dataset_upload_and_sidebar_sync(driver):
    """Uploads a test dataset via file input and verifies sidebar table sync."""
    wait = WebDriverWait(driver, 5)

    # Create temporary CSV file
    csv_data = "item,category,price\nWidget A,Hardware,15.50\nWidget B,Hardware,22.00\nWidget C,Software,49.99\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tf:
        tf.write(csv_data)
        tf_path = tf.name

    try:
        # Upload through hidden file input
        file_input = driver.find_element(By.ID, "file-input")
        file_input.send_keys(tf_path)

        # Wait for table to appear in sidebar
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#sidebar-tables .table-item")))
        table_items = driver.find_elements(By.CSS_SELECTOR, "#sidebar-tables .table-item")
        assert len(table_items) >= 1

        # Check dataset header pill
        header_pill = driver.find_element(By.ID, "header-dataset-pill")
        assert "active" in header_pill.get_attribute("class")

    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_browser_conversational_clarification_interaction(driver):
    """Verifies typing into the Clarification Engine composer and receiving responses."""
    wait = WebDriverWait(driver, 5)

    # Switch to Clarification Engine
    btn_ce = wait.until(EC.element_to_be_clickable((By.ID, "nav-btn-clarification")))
    btn_ce.click()
    time.sleep(0.3)

    # Find composer input
    ce_input = driver.find_element(By.ID, "ce-followup-input")
    ce_input.clear()
    ce_input.send_keys("check for duplicate rows")

    # Click send button
    btn_send = driver.find_element(By.ID, "ce-btn-send")
    btn_send.click()

    # Wait for assistant response in message stream
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ce-msg-assistant")))
    messages = driver.find_elements(By.CSS_SELECTOR, ".ce-msg-assistant")
    assert len(messages) >= 1

    # Check for console errors after full interaction
    logs = driver.get_log("browser")
    severe_errors = [entry for entry in logs if entry["level"] == "SEVERE"]
    assert len(severe_errors) == 0, f"Severe console errors found during interaction: {severe_errors}"


def test_browser_schema_studio_lifecycle(driver):
    """Verifies Schema Studio ER diagram, node selection, relationship inspector, and JOIN proposal execution in SQL Lab."""
    import sqlite3

    wait = WebDriverWait(driver, 8)

    # Create multi-table SQLite database
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        cur.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, FOREIGN KEY(customer_id) REFERENCES customers(id))")
        cur.execute("INSERT INTO customers VALUES (1, 'Alice', 'alice@test.com')")
        cur.execute("INSERT INTO orders VALUES (101, 1, 99.50)")
        conn.commit()
        conn.close()

        # Upload database
        file_input = driver.find_element(By.ID, "file-input")
        file_input.send_keys(db_path)

        # Wait for tables to appear in sidebar
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#sidebar-tables .table-item")))

        # 1. Switch to Schema Studio
        btn_schema = wait.until(EC.element_to_be_clickable((By.ID, "nav-btn-schema")))
        btn_schema.click()
        time.sleep(1.0)

        schema_view = driver.find_element(By.ID, "studio-view-schema")
        assert schema_view.is_displayed()
        assert "active" in schema_view.get_attribute("class")

        # Verify header counter badge accurately displays inferred relationship
        rel_badge = driver.find_element(By.ID, "schema-rel-count-badge")
        assert "1 Inferred" in rel_badge.text
        assert "0 Confirmed" in rel_badge.text

        # 2. Verify Table Nodes
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".schema-table-node")))
        nodes = driver.find_elements(By.CSS_SELECTOR, ".schema-table-node")
        assert len(nodes) >= 2

        # 3. Select node and verify inspector details
        nodes[0].click()
        time.sleep(0.5)
        details_pane = driver.find_element(By.ID, "pane-inspector-details")
        assert details_pane.is_displayed()
        assert "Table:" in details_pane.text

        # 4. Switch to Relationships subtab and test confirming relationship
        rel_tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".schema-tab-btn[data-subtab='relationships']")))
        rel_tab.click()
        time.sleep(0.5)
        rel_pane = driver.find_element(By.ID, "pane-inspector-relationships")
        assert rel_pane.is_displayed()

        btn_confirm = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-rel-confirm")))
        btn_confirm.click()
        time.sleep(1.0)

        # Counter badge must update immediately to 1 Confirmed • 0 Inferred
        assert "1 Confirmed" in rel_badge.text
        assert "0 Inferred" in rel_badge.text

        # 5. Switch to JOIN Builder subtab and generate JOIN
        join_tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".schema-tab-btn[data-subtab='join']")))
        join_tab.click()
        time.sleep(0.5)
        # Ensure distinct tables are selected in join builder
        sel_a = driver.find_element(By.ID, "join-table-a-select")
        sel_b = driver.find_element(By.ID, "join-table-b-select")
        options = [o.get_attribute("value") for o in sel_a.find_elements(By.TAG_NAME, "option")]
        orders_opt = next((o for o in options if "order" in o), None)
        cust_opt = next((o for o in options if "cust" in o), None)
        if orders_opt and cust_opt:
            driver.execute_script(f"arguments[0].value = '{cust_opt}';", sel_a)
            driver.execute_script(f"arguments[0].value = '{orders_opt}';", sel_b)

        btn_propose = wait.until(EC.element_to_be_clickable((By.ID, "btn-execute-join-proposal")))
        btn_propose.click()
        time.sleep(1.0)

        sql_code = driver.find_element(By.ID, "join-sql-code")
        assert "SELECT" in sql_code.text
        assert "JOIN" in sql_code.text

        # 6. Open & Execute in SQL Lab
        btn_send = wait.until(EC.presence_of_element_located((By.ID, "btn-send-join-to-sql-lab")))
        driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", btn_send)
        time.sleep(1.5)

        sql_view = driver.find_element(By.ID, "studio-view-sql-lab")
        assert sql_view.is_displayed()
        sql_editor = driver.find_element(By.ID, "sql-editor")
        assert "SELECT" in sql_editor.get_attribute("value")

        # 7. Check for console errors
        logs = driver.get_log("browser")
        severe_errors = [entry for entry in logs if entry["level"] == "SEVERE"]
        assert len(severe_errors) == 0, f"Severe console errors found in Schema Studio: {severe_errors}"

    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_browser_chart_and_diagnostics_workflow(driver):
    """
    Validates:
    1. Executing product sales & revenue aggregation in SQL Lab.
    2. Switching to Chart tab, auto-rendering chart without re-running.
    3. Selecting chart styles (Bar, Line) and verifying chart update.
    4. Switching to Diagnostics tab, auto-selecting active/first table.
    5. Table switching in Diagnostics and inspecting column health.
    6. Capturing screenshots for artifacts.
    """
    wait = WebDriverWait(driver, 10)
    artifact_dir = os.path.join(tempfile.gettempdir(), "dataverse_browser_artifacts")
    os.makedirs(artifact_dir, exist_ok=True)

    # 1. Upload retail_demo.sqlite
    file_input = driver.find_element(By.ID, "file-input")
    retail_db_path = os.path.abspath("sample_data/retail_demo.sqlite")
    file_input.send_keys(retail_db_path)

    # Wait for tables to appear in sidebar
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#sidebar-tables .table-item")))
    time.sleep(1.0)

    # 2. Switch to SQL Lab
    btn_sql = wait.until(EC.element_to_be_clickable((By.ID, "nav-btn-sql-lab")))
    btn_sql.click()
    time.sleep(0.5)

    # 3. Enter aggregation query in SQL Lab and run
    query = """SELECT p."product_name", SUM(o."quantity") AS units_sold, ROUND(SUM(o."total_amount"), 2) AS revenue FROM "retail_demo_products" p LEFT JOIN "retail_demo_orders" o ON p."product_id" = o."product_id" GROUP BY p."product_id", p."product_name" ORDER BY revenue DESC LIMIT 10"""
    sql_editor = driver.find_element(By.ID, "sql-editor")
    sql_editor.clear()
    sql_editor.send_keys(query)

    btn_run = driver.find_element(By.ID, "btn-run-sql")
    btn_run.click()
    time.sleep(2.0)

    # Verify table results rendered
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#table-wrapper table.data-table tbody tr")))
    rows = driver.find_elements(By.CSS_SELECTOR, "#table-wrapper table.data-table tbody tr")
    assert len(rows) > 0

    # 4. Switch to Chart Tab
    tab_chart = wait.until(EC.element_to_be_clickable((By.ID, "tab-chart")))
    tab_chart.click()
    time.sleep(1.0)

    view_chart = driver.find_element(By.ID, "view-chart")
    assert view_chart.is_displayed()

    # Verify chart image rendered
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#chart-container img.chart-image")))
    chart_img = driver.find_element(By.CSS_SELECTOR, "#chart-container img.chart-image")
    src = chart_img.get_attribute("src")
    assert src.startswith("data:image/png;base64,")

    # Verify chart type selector exists
    chart_select = driver.find_element(By.ID, "chart-type-select")
    assert chart_select.is_displayed()

    # Capture chart tab screenshot
    chart_screenshot_path = os.path.join(artifact_dir, "dataverse_chart_tab_rendered.png")
    driver.save_screenshot(chart_screenshot_path)

    # Change chart type to 'line'
    driver.execute_script("arguments[0].value = 'line'; arguments[0].dispatchEvent(new Event('change'));", chart_select)
    time.sleep(1.5)

    chart_img_updated = driver.find_element(By.CSS_SELECTOR, "#chart-container img.chart-image")
    assert chart_img_updated.get_attribute("src").startswith("data:image/png;base64,")

    # 5. Switch to Diagnostics Tab
    tab_diag = wait.until(EC.element_to_be_clickable((By.ID, "tab-profile")))
    tab_diag.click()
    time.sleep(1.5)

    view_diag = driver.find_element(By.ID, "view-profile")
    assert view_diag.is_displayed()

    # Verify table diagnostics auto-loaded
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#profile-container .stat-card")))
    stat_cards = driver.find_elements(By.CSS_SELECTOR, "#profile-container .stat-card")
    assert len(stat_cards) >= 3

    # Capture diagnostics tab screenshot
    diag_screenshot_path = os.path.join(artifact_dir, "dataverse_diagnostics_tab_rendered.png")
    driver.save_screenshot(diag_screenshot_path)

    # Test selecting another table from diagnostics dropdown
    prof_select = driver.find_element(By.ID, "profile-table-select")
    opts = [o.get_attribute("value") for o in prof_select.find_elements(By.TAG_NAME, "option")]
    orders_opt = next((o for o in opts if "orders" in o), None)
    if orders_opt:
        driver.execute_script(f"arguments[0].value = '{orders_opt}'; arguments[0].dispatchEvent(new Event('change'));", prof_select)
        time.sleep(1.5)
        cards_orders = driver.find_elements(By.CSS_SELECTOR, "#profile-container .stat-card")
        assert len(cards_orders) >= 4

    # 6. Check console errors
    logs = driver.get_log("browser")
    severe_errors = [entry for entry in logs if entry["level"] == "SEVERE"]
    assert len(severe_errors) == 0, f"Severe console errors found in Chart/Diagnostics: {severe_errors}"
