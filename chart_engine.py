"""
chart_engine.py - Automated Data Visualization Engine

Analyzes SQL execution results and automatically generates publication-grade visualizations.
Supports auto-detection of optimal chart types:
- Bar Charts (standard & horizontal)
- Line Charts (single & multi-series time trends)
- Pie / Donut Charts
- Scatter Plots
- Grouped Bar Charts

Styled with DataVerse modern dark aesthetics.
"""

from typing import List, Tuple, Any, Optional, Dict
import pandas as pd
import numpy as np
import logging
import os

# Use non-interactive backend by default to ensure headless testability
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

logger = logging.getLogger("dataverse.chart")

# DataVerse Color Palette (Dark Theme)
BG_COLOR = "#0f111a"
AXES_BG = "#16192b"
TEXT_COLOR = "#e0e6ed"
GRID_COLOR = "#2a2f4c"
PALETTE = [
    "#00d9ff",  # Cyan neon
    "#00ff88",  # Mint green
    "#ffaa00",  # Amber gold
    "#ff3366",  # Vibrant coral
    "#9d4edd",  # Purple
    "#4cc9f0",  # Sky blue
    "#f72585",  # Pink neon
    "#7209b7",  # Deep violet
    "#3a0ca3",  # Indigo
    "#4361ee"   # Royal blue
]

class ChartEngine:
    """
    Automated visualization generator for tabular query results.
    """

    @classmethod
    def detect_chart_type(cls, columns: List[str], rows: List[Tuple[Any, ...]]) -> str:
        """
        Determines the most suitable chart type for the given tabular data.
        Returns one of: 'none', 'bar', 'horizontal_bar', 'line', 'pie', 'scatter', 'grouped_bar'
        """
        if not columns or not rows:
            return "none"
            
        df = pd.DataFrame(rows, columns=columns)
        if len(df) == 0:
            return "none"
            
        # Determine numeric vs non-numeric columns
        numeric_cols = []
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                numeric_cols.append(col)
            else:
                # Try converting to numeric to see if numbers are stored as strings
                converted = pd.to_numeric(df[col], errors='coerce')
                if converted.notna().sum() > len(df) * 0.7:
                    numeric_cols.append(col)
                    
        categorical_cols = [c for c in df.columns if c not in numeric_cols]
        row_count = len(df)
        
        # Zero numeric columns -> cannot plot quantitative data
        if not numeric_cols:
            return "none"
            
        # Check if first categorical column resembles date/time
        is_date_col = False
        if categorical_cols:
            first_cat = categorical_cols[0]
            # Simple date heuristic
            sample = str(df[first_cat].iloc[0]) if len(df) > 0 else ""
            if any(sep in sample for sep in ["-", "/", ":"]) and len(sample) >= 4:
                try:
                    pd.to_datetime(df[first_cat].head(10))
                    is_date_col = True
                except Exception:
                    pass
        
        # 1 Categorical + 1 Numeric
        if len(categorical_cols) >= 1 and len(numeric_cols) == 1:
            if is_date_col:
                return "line"
            if row_count <= 6 and row_count >= 2:
                # Small distribution -> pie or bar
                return "bar"  # Bar is universally readable
            if row_count <= 25:
                # Check label lengths
                max_label_len = max(len(str(x)) for x in df[categorical_cols[0]].dropna().head(10))
                return "horizontal_bar" if max_label_len > 12 else "bar"
            return "horizontal_bar"
            
        # 1 Categorical + Multiple Numeric
        if len(categorical_cols) >= 1 and len(numeric_cols) > 1:
            if is_date_col:
                return "line"
            if len(numeric_cols) <= 4 and row_count <= 15:
                return "grouped_bar"
            return "line"
            
        # 0 Categorical, 2 Numeric
        if len(numeric_cols) == 2 and len(categorical_cols) == 0:
            if row_count > 10:
                return "scatter"
            return "bar"
            
        # 0 Categorical, >2 Numeric
        if len(numeric_cols) > 2 and len(categorical_cols) == 0:
            return "line"
            
        return "bar"

    @classmethod
    def create_figure(cls, 
                       columns: List[str], 
                       rows: List[Tuple[Any, ...]], 
                       chart_type: str = "auto", 
                       title: str = "",
                       figsize: Tuple[int, int] = (8, 5),
                       max_items: int = 20) -> Figure:
        """
        Creates a dark-mode styled Matplotlib Figure representing the query results.
        """
        fig = Figure(figsize=figsize, facecolor=BG_COLOR)
        ax = fig.add_subplot(111)
        ax.set_facecolor(AXES_BG)
        
        if not columns or not rows:
            ax.text(0.5, 0.5, "No data available to plot", 
                    color=TEXT_COLOR, ha='center', va='center', fontsize=12)
            cls._apply_minimal_styling(ax, title or "Empty Result")
            return fig

        df = pd.DataFrame(rows, columns=columns)
        
        # Convert numeric candidates
        numeric_cols = []
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                numeric_cols.append(col)
            else:
                converted = pd.to_numeric(df[col], errors='coerce')
                if converted.notna().sum() > len(df) * 0.7:
                    df[col] = converted
                    numeric_cols.append(col)
                    
        categorical_cols = [c for c in df.columns if c not in numeric_cols]
        
        if not numeric_cols:
            ax.text(0.5, 0.5, "No numeric columns found for quantitative visualization", 
                    color=TEXT_COLOR, ha='center', va='center', fontsize=11)
            cls._apply_minimal_styling(ax, title or "Unplottable Data")
            return fig

        if chart_type == "auto":
            chart_type = cls.detect_chart_type(columns, rows)
            
        # Limit rows for visualization clarity
        plot_df = df.head(max_items).copy()
        
        # Routing to specific chart renderer
        try:
            if chart_type in ("bar", "vertical_bar"):
                cls._render_bar(ax, plot_df, categorical_cols, numeric_cols)
            elif chart_type == "horizontal_bar":
                cls._render_horizontal_bar(ax, plot_df, categorical_cols, numeric_cols)
            elif chart_type == "line":
                cls._render_line(ax, plot_df, categorical_cols, numeric_cols)
            elif chart_type == "pie":
                cls._render_pie(ax, plot_df, categorical_cols, numeric_cols)
            elif chart_type == "scatter":
                cls._render_scatter(ax, plot_df, numeric_cols)
            elif chart_type == "grouped_bar":
                cls._render_grouped_bar(ax, plot_df, categorical_cols, numeric_cols)
            else:
                cls._render_bar(ax, plot_df, categorical_cols, numeric_cols)
        except Exception as e:
            logger.error(f"Error rendering chart: {e}")
            ax.clear()
            ax.text(0.5, 0.5, f"Could not render chart: {str(e)}", 
                    color="#ff4444", ha='center', va='center', fontsize=10)
                    
        cls._apply_minimal_styling(ax, title)
        fig.tight_layout()
        return fig

    @classmethod
    def _render_bar(cls, ax, df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
        num_col = num_cols[0]
        if cat_cols:
            labels = df[cat_cols[0]].astype(str).tolist()
        else:
            labels = [f"Row {i+1}" for i in range(len(df))]
            
        values = df[num_col].fillna(0).tolist()
        x = np.arange(len(labels))
        
        bars = ax.bar(x, values, color=PALETTE[0], edgecolor=BG_COLOR, width=0.6, alpha=0.9)
        ax.set_xticks(x)
        ax.set_xticklabels([cls._truncate_label(l, 14) for l in labels], 
                           rotation=30 if len(labels) > 5 else 0, 
                           ha='right' if len(labels) > 5 else 'center',
                           color=TEXT_COLOR)
        ax.set_ylabel(num_col, color=TEXT_COLOR)
        
        # Value labels on top of bars
        if len(bars) <= 15:
            for bar in bars:
                height = bar.get_height()
                ax.annotate(f"{height:,.2g}" if isinstance(height, float) else f"{height:,}",
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points",
                            ha='center', va='bottom', color="#00ff88", fontsize=8)

    @classmethod
    def _render_horizontal_bar(cls, ax, df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
        num_col = num_cols[0]
        if cat_cols:
            labels = df[cat_cols[0]].astype(str).tolist()
        else:
            labels = [f"Row {i+1}" for i in range(len(df))]
            
        values = df[num_col].fillna(0).tolist()
        # Reverse to show highest on top
        labels = labels[::-1]
        values = values[::-1]
        
        y = np.arange(len(labels))
        ax.barh(y, values, color=PALETTE[1], edgecolor=BG_COLOR, height=0.6, alpha=0.9)
        ax.set_yticks(y)
        ax.set_yticklabels([cls._truncate_label(l, 20) for l in labels], color=TEXT_COLOR)
        ax.set_xlabel(num_col, color=TEXT_COLOR)

    @classmethod
    def _render_line(cls, ax, df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
        if cat_cols:
            x_labels = df[cat_cols[0]].astype(str).tolist()
            x = np.arange(len(x_labels))
            ax.set_xticks(x)
            ax.set_xticklabels([cls._truncate_label(l, 12) for l in x_labels], 
                               rotation=35, ha='right', color=TEXT_COLOR)
        else:
            x = np.arange(len(df))
            ax.set_xlabel("Index", color=TEXT_COLOR)
            
        for i, col in enumerate(num_cols[:4]):
            color = PALETTE[i % len(PALETTE)]
            vals = df[col].fillna(0).tolist()
            ax.plot(x, vals, marker='o', linewidth=2.5, markersize=5, color=color, label=col)
            
        if len(num_cols) > 1:
            ax.legend(facecolor=AXES_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
        elif num_cols:
            ax.set_ylabel(num_cols[0], color=TEXT_COLOR)

    @classmethod
    def _render_pie(cls, ax, df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
        num_col = num_cols[0]
        if cat_cols:
            labels = [cls._truncate_label(str(x), 15) for x in df[cat_cols[0]].tolist()]
        else:
            labels = [f"Item {i+1}" for i in range(len(df))]
            
        values = [max(0, float(v)) for v in df[num_col].fillna(0).tolist()]
        if sum(values) == 0:
            values = [1] * len(values)
            
        colors = PALETTE[:len(labels)]
        wedges, texts, autotexts = ax.pie(
            values, 
            labels=labels, 
            autopct='%1.1f%%', 
            colors=colors,
            startangle=140,
            textprops=dict(color=TEXT_COLOR),
            wedgeprops=dict(width=0.7, edgecolor=BG_COLOR)  # Donut style
        )
        for at in autotexts:
            at.set_color("#0f111a")
            at.set_weight("bold")
            at.set_fontsize(8)

    @classmethod
    def _render_scatter(cls, ax, df: pd.DataFrame, num_cols: List[str]):
        x_col = num_cols[0]
        y_col = num_cols[1]
        x = df[x_col].fillna(0)
        y = df[y_col].fillna(0)
        ax.scatter(x, y, color=PALETTE[0], s=60, alpha=0.8, edgecolors=PALETTE[1])
        ax.set_xlabel(x_col, color=TEXT_COLOR)
        ax.set_ylabel(y_col, color=TEXT_COLOR)

    @classmethod
    def _render_grouped_bar(cls, ax, df: pd.DataFrame, cat_cols: List[str], num_cols: List[str]):
        labels = df[cat_cols[0]].astype(str).tolist()
        x = np.arange(len(labels))
        num_series = len(num_cols[:3])
        total_width = 0.8
        width = total_width / num_series
        
        for i, col in enumerate(num_cols[:3]):
            offset = (i - (num_series - 1) / 2) * width
            vals = df[col].fillna(0).tolist()
            ax.bar(x + offset, vals, width, label=col, color=PALETTE[i % len(PALETTE)])
            
        ax.set_xticks(x)
        ax.set_xticklabels([cls._truncate_label(l, 14) for l in labels], rotation=30, ha='right', color=TEXT_COLOR)
        ax.legend(facecolor=AXES_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)

    @classmethod
    def _apply_minimal_styling(cls, ax, title: str):
        if title:
            ax.set_title(title, color="#00d9ff", fontsize=13, weight="bold", pad=12)
        ax.tick_params(colors=TEXT_COLOR, labelsize=9)
        ax.grid(True, linestyle="--", alpha=0.2, color=GRID_COLOR)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)

    @staticmethod
    def _truncate_label(label: str, max_chars: int = 15) -> str:
        s = str(label)
        return s[:max_chars - 3] + "..." if len(s) > max_chars else s

    @classmethod
    def save_chart(cls, fig: Figure, file_path: str, dpi: int = 150) -> str:
        """Saves a figure to disk (PNG, SVG, PDF)."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        fig.savefig(file_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
        return os.path.abspath(file_path)
