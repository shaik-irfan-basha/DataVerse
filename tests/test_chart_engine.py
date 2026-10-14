import pytest
import os
import tempfile
from chart_engine import ChartEngine
from matplotlib.figure import Figure

def test_detect_chart_type_bar():
    columns = ["category", "sales"]
    rows = [("A", 100), ("B", 200), ("C", 150)]
    chart_type = ChartEngine.detect_chart_type(columns, rows)
    assert chart_type in ("bar", "horizontal_bar")

def test_detect_chart_type_line_for_dates():
    columns = ["date", "revenue"]
    rows = [("2026-01-01", 100), ("2026-01-02", 150), ("2026-01-03", 200)]
    chart_type = ChartEngine.detect_chart_type(columns, rows)
    assert chart_type == "line"

def test_detect_chart_type_scatter_for_two_numeric():
    columns = ["age", "income"]
    rows = [(20 + i, 30000 + i * 2000) for i in range(15)]
    chart_type = ChartEngine.detect_chart_type(columns, rows)
    assert chart_type == "scatter"

def test_detect_chart_type_none_for_no_numeric():
    columns = ["first_name", "last_name"]
    rows = [("John", "Doe"), ("Jane", "Smith")]
    chart_type = ChartEngine.detect_chart_type(columns, rows)
    assert chart_type == "none"

def test_create_figure_bar():
    columns = ["product", "revenue"]
    rows = [("Apples", 50), ("Bananas", 80), ("Cherries", 40)]
    fig = ChartEngine.create_figure(columns, rows, chart_type="bar", title="Fruit Revenue")
    assert isinstance(fig, Figure)
    assert len(fig.axes) > 0

def test_create_figure_horizontal_bar():
    columns = ["department_name_very_long", "headcount"]
    rows = [("Research and Engineering", 42), ("Marketing & Communications", 15)]
    fig = ChartEngine.create_figure(columns, rows, chart_type="horizontal_bar")
    assert isinstance(fig, Figure)

def test_create_figure_pie():
    columns = ["status", "count"]
    rows = [("Active", 70), ("Pending", 20), ("Inactive", 10)]
    fig = ChartEngine.create_figure(columns, rows, chart_type="pie", title="Status Breakdown")
    assert isinstance(fig, Figure)

def test_create_figure_line():
    columns = ["month", "visitors"]
    rows = [("Jan", 1000), ("Feb", 1200), ("Mar", 1500)]
    fig = ChartEngine.create_figure(columns, rows, chart_type="line")
    assert isinstance(fig, Figure)

def test_create_figure_empty_data():
    fig = ChartEngine.create_figure([], [])
    assert isinstance(fig, Figure)

def test_save_chart():
    columns = ["metric", "value"]
    rows = [("X", 10), ("Y", 20)]
    fig = ChartEngine.create_figure(columns, rows, chart_type="bar")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        saved = ChartEngine.save_chart(fig, path)
        assert os.path.exists(saved)
        assert os.path.getsize(saved) > 0
    finally:
        if os.path.exists(path):
            os.remove(path)
