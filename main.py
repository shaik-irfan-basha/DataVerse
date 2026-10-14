"""
main.py - DataVerse NL-to-SQL Converter with Enterprise Intelligence

Presentation & GUI Layer (CustomTkinter)
- Natural Language Question Answering
- Automated Clarification Modal Dialogs
- Schema Intelligence & Clickable Question Suggestions
- Interactive Data Profiler & Column Diagnostics
- Persistent Query History & Session Memory
- Automated Data Visualizations (Matplotlib Canvas)
- Multi-format Result Export (CSV, Excel, JSON)
- Keyboard Shortcuts & Fast Workflow Controls
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import logging
from logger import setup_logging

from dotenv import load_dotenv
load_dotenv()

setup_logging()
logger = logging.getLogger("dataverse.ui")
logger.info("Application starting up...")

from data_connector import DataConnector
from query_service import QueryService
import config

# Matplotlib integration
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# Set modern theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DataVerseApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🔮 DataVerse — Enterprise Natural-Language Data Intelligence")
        self.root.geometry("1080x850")
        self.root.minsize(850, 720)
        
        # Core components
        self.connector = DataConnector()
        self.query_service = QueryService(self.connector)
        
        # UI State
        self.clarification_history = ""
        self.current_results = None  # Stores last execution result dict
        self.current_chart_figure = None
        self.canvas = None
        
        # Build UI
        self.create_widgets()
        self._bind_shortcuts()
    
    def _bind_shortcuts(self):
        """Registers enterprise keyboard shortcuts."""
        self.root.bind("<Control-Return>", lambda e: self.generate_and_run())
        self.root.bind("<Control-r>", lambda e: self.run_sql())
        self.root.bind("<F5>", lambda e: self.run_sql())
        self.root.bind("<Control-l>", lambda e: self.clear_all())
        self.root.bind("<Control-o>", lambda e: self.upload_file())
        self.root.bind("<Control-e>", lambda e: self._on_export_selected("Export CSV"))
    
    # =========================================================================
    # UI CREATION
    # =========================================================================
    
    def create_widgets(self):
        # Main container
        self.main_frame = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        # -- HEADER --
        self._create_header(self.main_frame)
        
        # -- SECTION 1: DATA SOURCE --
        self._create_data_section(self.main_frame)
        
        # -- SECTION 2: QUESTION & GENERATE --
        self._create_query_section(self.main_frame)
        
        # -- SECTION 3: GENERATED SQL --
        self._create_sql_section(self.main_frame)
        
        # -- SECTION 4: RESULTS & VISUALIZATION --
        self._create_results_section(self.main_frame)
        
        # -- STATUS BAR --
        self._create_status_bar(self.root)
    
    def _create_header(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, 15))
        
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")
        
        title = ctk.CTkLabel(
            title_box,
            text="🔮 DataVerse",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color="#00d9ff"
        )
        title.pack(side="left")
        
        subtitle = ctk.CTkLabel(
            title_box,
            text="Enterprise NL-to-SQL & Analytics",
            font=ctk.CTkFont(size=12),
            text_color="gray60"
        )
        subtitle.pack(side="left", padx=(12, 0), pady=(8, 0))
        
        # Action buttons in header
        btn_box = ctk.CTkFrame(header, fg_color="transparent")
        btn_box.pack(side="right")
        
        self.history_btn = ctk.CTkButton(
            btn_box,
            text="📜 Query History",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1f538d",
            hover_color="#14375e",
            width=120,
            command=self.show_history_dialog
        )
        self.history_btn.pack(side="right", padx=5)
        
        self.profile_btn = ctk.CTkButton(
            btn_box,
            text="📊 Profile Data",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2b2b36",
            hover_color="#3b3b46",
            width=110,
            command=self.show_data_profile_dialog
        )
        self.profile_btn.pack(side="right", padx=5)
    
    def _create_data_section(self, parent):
        frame = ctk.CTkFrame(parent, corner_radius=10)
        frame.pack(fill="x", pady=(0, 15), ipady=5)
        
        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            top_row,
            text="📂 Data Source",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#00d9ff"
        ).pack(side="left")
        
        self.upload_btn = ctk.CTkButton(
            top_row,
            text="📁 Upload File (Ctrl+O)",
            font=ctk.CTkFont(weight="bold"),
            command=self.upload_file,
            width=150
        )
        self.upload_btn.pack(side="right")
        
        self.file_label = ctk.CTkLabel(
            frame,
            text="No file loaded — upload a CSV, Excel, JSON, or SQLite file",
            text_color="gray60",
            anchor="w",
            justify="left"
        )
        self.file_label.pack(fill="x", padx=15, pady=(0, 5))
        
        self.schema_text = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="gray75",
            anchor="w",
            justify="left",
            wraplength=850
        )
        self.schema_text.pack(fill="x", padx=15, pady=(0, 10))
    
    def _create_query_section(self, parent):
        frame = ctk.CTkFrame(parent, corner_radius=10)
        frame.pack(fill="x", pady=(0, 15), ipady=5)
        
        ctk.CTkLabel(
            frame,
            text="💬 Ask a Question",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#00d9ff",
            anchor="w"
        ).pack(fill="x", padx=15, pady=(15, 5))
        
        self.question_entry = ctk.CTkTextbox(
            frame,
            height=70,
            font=ctk.CTkFont(size=14),
            border_width=1,
            corner_radius=8
        )
        self.question_entry.pack(fill="x", padx=15, pady=(5, 5))
        self.question_entry.insert("1.0", "e.g. Who is our best customer?")
        self.question_entry.bind("<FocusIn>", self._on_question_focus_in)
        self.question_entry.bind("<FocusOut>", self._on_question_focus_out)
        
        # Suggested questions container
        self.suggestions_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.suggestions_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(0, 15))
        
        self.generate_btn = ctk.CTkButton(
            btn_row,
            text="⚡ Generate SQL & Run (Ctrl+Enter)",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#00d9ff",
            text_color="#0f0f1a",
            hover_color="#00ff88",
            height=40,
            command=self.generate_and_run
        )
        self.generate_btn.pack(side="left")
        
        ctk.CTkButton(
            btn_row,
            text="🗑️ Clear (Ctrl+L)",
            fg_color="transparent",
            border_width=1,
            text_color="gray80",
            hover_color="gray30",
            command=self.clear_all,
            width=100
        ).pack(side="right")
    
    def _create_sql_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(0, 15))
        
        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 5))
        
        ctk.CTkLabel(
            top_row,
            text="🤖 Generated SQL",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#00ff88"
        ).pack(side="left")
        
        self.run_btn = ctk.CTkButton(
            top_row,
            text="▶️ Run SQL (F5)",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#1f538d",
            width=110,
            command=self.run_sql
        )
        self.run_btn.pack(side="right")
        
        self.sql_text = ctk.CTkTextbox(
            frame,
            height=85,
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color="#00ff88",
            fg_color="#0d1117",
            border_width=1,
            corner_radius=8
        )
        self.sql_text.pack(fill="x")
    
    def _create_results_section(self, parent):
        self.results_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.results_frame.pack(fill="both", expand=True)
        
        top_row = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 5))
        
        ctk.CTkLabel(
            top_row,
            text="📊 Results",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffaa00"
        ).pack(side="left")
        
        # View Mode Toggle (Table vs Chart)
        self.view_mode = ctk.CTkSegmentedButton(
            top_row,
            values=["📋 Table", "📈 Chart"],
            command=self._on_view_mode_changed,
            width=140
        )
        self.view_mode.set("📋 Table")
        self.view_mode.pack(side="left", padx=(15, 10))
        
        # Chart Type Option
        self.chart_type_menu = ctk.CTkOptionMenu(
            top_row,
            values=["Auto", "Bar", "Horizontal Bar", "Line", "Pie", "Scatter"],
            command=self._on_chart_type_changed,
            width=130
        )
        self.chart_type_menu.set("Auto")
        self.chart_type_menu.pack(side="left", padx=5)
        
        # Export Menu
        self.export_menu = ctk.CTkOptionMenu(
            top_row,
            values=["💾 Export...", "Export CSV", "Export Excel", "Export JSON"],
            command=self._on_export_selected,
            width=120,
            fg_color="#2b2b36",
            button_color="#3b3b46"
        )
        self.export_menu.set("💾 Export...")
        self.export_menu.pack(side="right", padx=5)
        
        self.result_info = ctk.CTkLabel(
            top_row,
            text="",
            text_color="gray60"
        )
        self.result_info.pack(side="right", padx=(0, 10))
        
        # Container holding either Table or Chart
        self.content_container = ctk.CTkFrame(self.results_frame, corner_radius=8)
        self.content_container.pack(fill="both", expand=True)
        
        # 1. Table Frame
        self.tree_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True)
        
        # Style ttk.Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#1e1e1e",
            foreground="white",
            fieldbackground="#1e1e1e",
            borderwidth=0,
            rowheight=30,
            font=("Segoe UI", 11)
        )
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure(
            "Treeview.Heading",
            background="#2b2b2b",
            foreground="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padding=5
        )
        style.map("Treeview.Heading", background=[('active', '#3b3b3b')])
        
        y_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical")
        x_scroll = ttk.Scrollbar(self.tree_frame, orient="horizontal")
        
        self.tree = ttk.Treeview(
            self.tree_frame,
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
            show="headings"
        )
        
        y_scroll.config(command=self.tree.yview)
        x_scroll.config(command=self.tree.xview)
        
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True, padx=2, pady=2)
        
        # 2. Chart Frame (initially hidden)
        self.chart_frame = ctk.CTkFrame(self.content_container, fg_color="#0f111a")
        
        self.answer_label = ctk.CTkLabel(
            self.results_frame,
            text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00ff88",
            anchor="w",
            justify="left"
        )
        self.answer_label.pack(fill="x", pady=(10, 0))
    
    def _create_status_bar(self, parent):
        status_frame = ctk.CTkFrame(parent, height=30, corner_radius=0, fg_color="#1a1a2e")
        status_frame.pack(fill="x", side="bottom")
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Ready — upload a file to get started",
            text_color="gray60",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(side="left", padx=20, pady=2)
        
        shortcut_info = ctk.CTkLabel(
            status_frame,
            text="Ctrl+Enter: Run | F5: Run SQL | Ctrl+O: Open | Ctrl+L: Clear",
            text_color="gray45",
            font=ctk.CTkFont(size=11)
        )
        shortcut_info.pack(side="right", padx=20, pady=2)
    
    # =========================================================================
    # LOGIC & EVENT HANDLERS
    # =========================================================================
    
    def _on_question_focus_in(self, event):
        if self.question_entry.get("1.0", "end-1c").strip() == "e.g. Who is our best customer?":
            self.question_entry.delete("1.0", "end")
    
    def _on_question_focus_out(self, event):
        if not self.question_entry.get("1.0", "end-1c").strip():
            self.question_entry.insert("1.0", "e.g. Who is our best customer?")
    
    def upload_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a data file",
            filetypes=DataConnector.get_filetypes()
        )
        if not file_path:
            return
        
        self.status_label.configure(text=f"Loading {os.path.basename(file_path)}...")
        self.root.update()
        
        threading.Thread(target=self._load_file_thread, args=(file_path,)).start()
    
    def _load_file_thread(self, file_path: str):
        try:
            table_names = self.query_service.load_file(file_path)
            self.root.after(0, lambda: self._on_file_loaded(file_path, table_names))
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._on_file_error(err))
    
    def _on_file_loaded(self, file_path: str, table_names: list):
        filename = os.path.basename(file_path)
        total_rows = sum(self.connector.get_row_count(t) for t in table_names)
        
        self.file_label.configure(
            text=f"✅ {filename}  ({self.connector.file_type})  —  {len(table_names)} table(s), {total_rows:,} rows",
            text_color="#00ff88"
        )
        self.schema_text.configure(text=self.connector.get_schema_string())
        self.status_label.configure(text=f"File loaded: {filename}")
        self._clear_results()
        self.sql_text.delete("1.0", "end")
        
        # Generate suggested questions
        self._update_suggested_questions()
    
    def _update_suggested_questions(self):
        """Generates smart clickable suggested question pills."""
        for widget in self.suggestions_frame.winfo_children():
            widget.destroy()
            
        questions = self.query_service.get_suggested_questions(max_questions=4)
        if not questions:
            return
            
        label = ctk.CTkLabel(
            self.suggestions_frame,
            text="💡 Suggestions:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray60"
        )
        label.pack(side="left", padx=(0, 8))
        
        for q in questions:
            pill = ctk.CTkButton(
                self.suggestions_frame,
                text=q,
                font=ctk.CTkFont(size=11),
                fg_color="#1a1d2e",
                hover_color="#242942",
                border_width=1,
                border_color="#333c5e",
                text_color="#99b3ff",
                height=26,
                command=lambda question_text=q: self._use_suggested_question(question_text)
            )
            pill.pack(side="left", padx=4)
    
    def _use_suggested_question(self, question: str):
        self.question_entry.delete("1.0", "end")
        self.question_entry.insert("1.0", question)
        self.generate_and_run()
    
    def _on_file_error(self, error_msg: str):
        logger.error(f"File load failed: {error_msg}")
        self.file_label.configure(text=f"❌ Error: {error_msg}", text_color="#ff4444")
        self.status_label.configure(text="File load failed")
        messagebox.showerror("Load Error", error_msg)
    
    def generate_and_run(self):
        if not self.connector.is_loaded():
            messagebox.showwarning("No Data", "Please upload a data file first.")
            return
        
        question = self.question_entry.get("1.0", "end-1c").strip()
        if not question or question.startswith("e.g."):
            messagebox.showwarning("No Question", "Please enter a question.")
            return
        
        self.generate_btn.configure(state="disabled", text="⏳ Working...")
        self.status_label.configure(text="Analyzing intent...")
        self.sql_text.delete("1.0", "end")
        self._clear_results()
        self.root.update()
        
        if not self.clarification_history:
            self.clarification_history = ""
            
        threading.Thread(target=self._generate_and_run_thread, args=(question,)).start()
    
    def _generate_and_run_thread(self, question: str):
        try:
            self.root.after(0, lambda: self.status_label.configure(text="Analyzing query intent..."))
            
            def ui_retry_callback(attempt, max_retries, current_sql, err_msg):
                self.root.after(0, lambda s=current_sql: self._show_generated_sql(s))
                status = f"Retrying ({attempt}/{max_retries})..."
                self.root.after(0, lambda: self.status_label.configure(text=status))
                
            response = self.query_service.query(
                question=question,
                clarification_history=self.clarification_history,
                retry_callback=ui_retry_callback
            )
            
            if response.status == "CLARIFICATION_REQUIRED":
                user_choice = self._ask_user_clarification(response.clarification_question, response.clarification_options)
                if not user_choice:
                    self.root.after(0, lambda: self.status_label.configure(text="Cancelled by user."))
                    self.root.after(0, lambda: self.generate_btn.configure(state="normal", text="⚡ Generate SQL & Run (Ctrl+Enter)"))
                    self.clarification_history = ""
                    return
                
                self.clarification_history += f"AI: {response.clarification_question}\nUser: {user_choice}\n\n"
                self._generate_and_run_thread(question)
                return
            
            self.clarification_history = ""
            
            if response.sql:
                self.root.after(0, lambda s=response.sql: self._show_generated_sql(s))
                
            if response.status == "SUCCESS":
                self.root.after(0, lambda res=response.data: self._show_results(res))
            else:
                self.root.after(0, lambda res=response.data if response.data else {"success": False, "error": response.error_message}: self._show_results(res))
                
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._show_error(err))

    def _validate_and_execute(self, sql: str):
        """Locked validation and execution pipeline."""
        result = self.query_service.execute_manual_sql(sql)
        self.root.after(0, lambda res=result: self._show_results(res))

    def _ask_user_clarification(self, question: str, options: list) -> str:
        event = threading.Event()
        result = [None]
        self.root.after(0, lambda: ClarificationDialog(self.root, question, options, event, result))
        event.wait()
        return result[0]
        
    def run_sql(self):
        if not self.connector.is_loaded():
            return
        sql = self.sql_text.get("1.0", "end-1c").strip()
        if not sql:
            return
        
        self._clear_results()
        self.status_label.configure(text="Validating and executing SQL...")
        threading.Thread(target=self._validate_and_execute, args=(sql,)).start()
    
    def _show_generated_sql(self, sql: str):
        self.sql_text.delete("1.0", "end")
        self.sql_text.insert("1.0", sql)
        self.status_label.configure(text="SQL generated — executing query...")
    
    def _show_results(self, result: dict):
        self.generate_btn.configure(state="normal", text="⚡ Generate SQL & Run (Ctrl+Enter)")
        self.current_results = result
        
        if not result["success"]:
            self.status_label.configure(text="❌ Query failed")
            self.answer_label.configure(text=f"❌ {result['error']}", text_color="#ff4444")
            return
        
        self._clear_results()
        cols, rows = result.get("columns", []), result.get("rows", [])
        
        if not cols:
            self.status_label.configure(text="✅ Query executed (no results)")
            self.answer_label.configure(text="Query executed successfully — no rows returned.", text_color="#ffaa00")
            return
        
        # Populate Treeview
        self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor="w")
        
        for row in rows[:config.MAX_DISPLAY_ROWS]:
            self.tree.insert("", "end", values=row)
        
        info = f"{min(result['row_count'], config.MAX_DISPLAY_ROWS)} of {result['row_count']:,} rows — {result['execution_time']}s"
        self.result_info.configure(text=info)
        self.status_label.configure(text="✅ Query executed successfully!")
        
        if result["row_count"] == 1 and len(cols) <= 3:
            parts = [f"{cols[i]}: {rows[0][i]}" for i in range(len(cols))]
            self.answer_label.configure(text=f"📌 {' | '.join(parts)}", text_color="#00ff88")
            
        # If user currently has Chart mode selected, render chart
        if self.view_mode.get() == "📈 Chart":
            self._render_current_chart()
    
    def _show_error(self, error_msg: str):
        self.generate_btn.configure(state="normal", text="⚡ Generate SQL & Run (Ctrl+Enter)")
        self.status_label.configure(text="❌ Generation failed")
        self.answer_label.configure(text=f"❌ {error_msg}", text_color="#ff4444")
    
    def _clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []
        self.result_info.configure(text="")
        self.answer_label.configure(text="")
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None
    
    def clear_all(self):
        self.question_entry.delete("1.0", "end")
        self.question_entry.insert("1.0", "e.g. Who is our best customer?")
        self.sql_text.delete("1.0", "end")
        self._clear_results()
        self.status_label.configure(text="Cleared")
    
    # =========================================================================
    # VISUALIZATION & EXPORT
    # =========================================================================
    
    def _on_view_mode_changed(self, mode: str):
        if mode == "📈 Chart":
            self.tree_frame.pack_forget()
            self.chart_frame.pack(fill="both", expand=True)
            self._render_current_chart()
        else:
            self.chart_frame.pack_forget()
            self.tree_frame.pack(fill="both", expand=True)
            
    def _on_chart_type_changed(self, chart_type_label: str):
        if self.view_mode.get() == "📈 Chart":
            self._render_current_chart()
            
    def _render_current_chart(self):
        """Renders or updates the chart in chart_frame."""
        if not self.current_results or not self.current_results.get("success"):
            return
            
        cols = self.current_results.get("columns", [])
        rows = self.current_results.get("rows", [])
        if not cols or not rows:
            return
            
        # Map label to internal chart type
        label = self.chart_type_menu.get().lower().replace(" ", "_")
        ctype = "auto" if label == "auto" else label
        
        # Clear existing canvas
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None
            
        if self.current_chart_figure:
            plt.close(self.current_chart_figure)
            
        self.current_chart_figure = self.query_service.generate_chart(
            columns=cols,
            rows=rows,
            chart_type=ctype,
            title="Data Visualization"
        )
        
        self.canvas = FigureCanvasTkAgg(self.current_chart_figure, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
    
    def _on_export_selected(self, choice: str):
        self.export_menu.set("💾 Export...")
        if choice == "💾 Export...":
            return
            
        if not self.current_results or not self.current_results.get("columns"):
            messagebox.showinfo("No Results", "There are no query results available to export.")
            return
            
        cols = self.current_results["columns"]
        rows = self.current_results["rows"]
        
        fmt = "csv"
        file_ext = "*.csv"
        file_desc = "CSV Files (*.csv)"
        
        if "Excel" in choice:
            fmt = "excel"
            file_ext = "*.xlsx"
            file_desc = "Excel Files (*.xlsx)"
        elif "JSON" in choice:
            fmt = "json"
            file_ext = "*.json"
            file_desc = "JSON Files (*.json)"
            
        file_path = filedialog.asksaveasfilename(
            title=f"Export Results as {choice}",
            defaultextension=file_ext.replace("*", ""),
            filetypes=[(file_desc, file_ext), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
            
        try:
            saved_path = self.query_service.export_results(cols, rows, file_path, format_type=fmt)
            self.status_label.configure(text=f"Exported: {os.path.basename(saved_path)}")
            messagebox.showinfo("Export Successful", f"Results successfully exported to:\n{saved_path}")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            messagebox.showerror("Export Failed", f"Could not export results: {e}")
            
    # =========================================================================
    # DIALOGS (History & Data Profiler)
    # =========================================================================
    
    def show_history_dialog(self):
        HistoryDialog(self.root, self.query_service, self._load_from_history)
        
    def _load_from_history(self, question: str, sql: str):
        if question and question != "Manual SQL Execution":
            self.question_entry.delete("1.0", "end")
            self.question_entry.insert("1.0", question)
        if sql:
            self.sql_text.delete("1.0", "end")
            self.sql_text.insert("1.0", sql)
        self.status_label.configure(text="Loaded query from history")
        
    def show_data_profile_dialog(self):
        if not self.connector.is_loaded():
            messagebox.showinfo("No Data", "Please upload a data file first to view its profile.")
            return
        DataProfileDialog(self.root, self.query_service)


# =============================================================================
# MODAL DIALOGS
# =============================================================================

class ClarificationDialog(ctk.CTkToplevel):
    def __init__(self, parent, question: str, options: list, event, result_container):
        super().__init__(parent)
        self.title("🤔 Clarification Needed")
        self.geometry("550x400")
        self.attributes('-topmost', 'true')
        
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (550 // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (400 // 2)
        self.geometry(f"+{x}+{y}")
        
        self.event = event
        self.result_container = result_container
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        frame = ctk.CTkFrame(self, corner_radius=15)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            frame, 
            text="⚠️ Clarification Required", 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffaa00"
        ).pack(fill="x", pady=(15, 10))
        
        ctk.CTkLabel(
            frame, 
            text=question, 
            font=ctk.CTkFont(size=14),
            wraplength=480,
            justify="left"
        ).pack(fill="x", padx=20, pady=(0, 20))
        
        self.radio_var = tk.StringVar(value="")
        for opt in options:
            ctk.CTkRadioButton(
                frame, 
                text=opt, 
                variable=self.radio_var, 
                value=opt,
                font=ctk.CTkFont(size=14)
            ).pack(anchor="w", padx=40, pady=8)
            
        self.custom_entry = ctk.CTkEntry(
            frame, 
            placeholder_text="Or type something else...",
            height=35
        )
        self.custom_entry.pack(fill="x", padx=40, pady=(15, 20))
        
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=40, pady=(0, 20))
        
        ctk.CTkButton(
            btn_frame, 
            text="Cancel", 
            fg_color="gray30", 
            hover_color="gray40",
            command=self._on_close
        ).pack(side="left", expand=True, padx=5)
        
        ctk.CTkButton(
            btn_frame, 
            text="Submit", 
            fg_color="#00d9ff",
            text_color="#0f0f1a",
            hover_color="#00ff88",
            command=self._on_submit
        ).pack(side="right", expand=True, padx=5)
        
    def _on_submit(self):
        val = self.custom_entry.get().strip()
        choice = val if val else self.radio_var.get()
        if not choice:
            return
        self.result_container[0] = choice
        self.event.set()
        self.destroy()
        
    def _on_close(self):
        self.result_container[0] = None
        self.event.set()
        self.destroy()


class HistoryDialog(ctk.CTkToplevel):
    """Interactive Query History Viewer & Loader."""
    def __init__(self, parent, query_service: QueryService, load_callback):
        super().__init__(parent)
        self.title("📜 Query History & Session Log")
        self.geometry("780x520")
        self.query_service = query_service
        self.load_callback = load_callback
        
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (780 // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (520 // 2)
        self.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        top_bar = ctk.CTkFrame(frame, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            top_bar, 
            text="📜 Recent Query History", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00d9ff"
        ).pack(side="left")
        
        ctk.CTkButton(
            top_bar,
            text="🗑️ Clear All",
            fg_color="#3a1c22",
            hover_color="#54242d",
            text_color="#ff7b88",
            width=90,
            command=self._on_clear
        ).pack(side="right")
        
        self.scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self._populate_history()
        
    def _populate_history(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
            
        entries = self.query_service.get_history(limit=50)
        if not entries:
            ctk.CTkLabel(
                self.scroll_frame, 
                text="No query history recorded yet.", 
                text_color="gray50",
                font=ctk.CTkFont(size=13)
            ).pack(pady=40)
            return
            
        for e in entries:
            card = ctk.CTkFrame(self.scroll_frame, corner_radius=8, fg_color="#1a1c29")
            card.pack(fill="x", pady=4, padx=5)
            
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(8, 2))
            
            status_badge = "✅" if e.success else "❌"
            badge_color = "#00ff88" if e.success else "#ff4444"
            
            ctk.CTkLabel(
                top,
                text=f"{status_badge}  {e.timestamp}  |  {e.dataset_name or 'Default'}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=badge_color
            ).pack(side="left")
            
            ctk.CTkButton(
                top,
                text="Load Query ↗",
                width=80,
                height=22,
                font=ctk.CTkFont(size=11),
                command=lambda entry=e: self._load_entry(entry)
            ).pack(side="right")
            
            q_label = ctk.CTkLabel(
                card,
                text=f"Q: {e.question}",
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
                justify="left"
            )
            q_label.pack(fill="x", padx=10, pady=2)
            
            if e.sql_query:
                sql_lbl = ctk.CTkLabel(
                    card,
                    text=f"SQL: {e.sql_query}",
                    font=ctk.CTkFont(family="Consolas", size=11),
                    text_color="#89ddff",
                    anchor="w",
                    justify="left"
                )
                sql_lbl.pack(fill="x", padx=10, pady=(0, 6))

    def _load_entry(self, entry):
        self.load_callback(entry.question, entry.sql_query)
        self.destroy()

    def _on_clear(self):
        if messagebox.askyesno("Confirm Clear", "Clear all query history?"):
            self.query_service.clear_history()
            self._populate_history()


class DataProfileDialog(ctk.CTkToplevel):
    """Detailed Statistical Data Profiling View."""
    def __init__(self, parent, query_service: QueryService):
        super().__init__(parent)
        self.title("📊 Dataset Profile & Quality Diagnostics")
        self.geometry("880x600")
        self.query_service = query_service
        
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (880 // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (600 // 2)
        self.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            header,
            text="📊 Comprehensive Data Profile",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00d9ff"
        ).pack(side="left")
        
        self.scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self._load_profiles()
        
    def _load_profiles(self):
        profiles = self.query_service.profile_all_tables()
        if not profiles:
            ctk.CTkLabel(self.scroll_frame, text="No tables available to profile.").pack(pady=30)
            return
            
        for tname, prof in profiles.items():
            card = ctk.CTkFrame(self.scroll_frame, corner_radius=10, fg_color="#181a26")
            card.pack(fill="x", pady=8, padx=5)
            
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=15, pady=(10, 5))
            
            ctk.CTkLabel(
                top,
                text=f"📋 Table: {prof.table_name}",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#00ff88"
            ).pack(side="left")
            
            ctk.CTkLabel(
                top,
                text=f"{prof.total_rows:,} rows  •  {prof.total_columns} columns",
                font=ctk.CTkFont(size=12),
                text_color="gray60"
            ).pack(side="right")
            
            # Columns table
            cols_box = ctk.CTkFrame(card, fg_color="#11131c", corner_radius=6)
            cols_box.pack(fill="x", padx=15, pady=(5, 15))
            
            # Header
            h_row = ctk.CTkFrame(cols_box, fg_color="#212536", corner_radius=4)
            h_row.pack(fill="x", padx=5, pady=4)
            
            ctk.CTkLabel(h_row, text="Column", width=140, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
            ctk.CTkLabel(h_row, text="Type", width=70, anchor="center", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
            ctk.CTkLabel(h_row, text="Nulls", width=80, anchor="center", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
            ctk.CTkLabel(h_row, text="Uniques", width=80, anchor="center", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
            ctk.CTkLabel(h_row, text="Diagnostics & Distributions", anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5, fill="x", expand=True)
            
            for col in prof.columns:
                row_f = ctk.CTkFrame(cols_box, fg_color="transparent")
                row_f.pack(fill="x", padx=5, pady=2)
                
                ctk.CTkLabel(row_f, text=col.name, width=140, anchor="w", text_color="#00d9ff").pack(side="left", padx=5)
                ctk.CTkLabel(row_f, text=col.data_type, width=70, anchor="center", text_color="gray70").pack(side="left", padx=5)
                ctk.CTkLabel(row_f, text=f"{col.null_percentage}%", width=80, anchor="center", text_color="#ff7b88" if col.null_percentage > 0 else "gray60").pack(side="left", padx=5)
                ctk.CTkLabel(row_f, text=f"{col.unique_count:,}", width=80, anchor="center", text_color="gray70").pack(side="left", padx=5)
                
                # Summary details
                if col.is_numeric:
                    detail = f"Min: {col.min_val}  |  Max: {col.max_val}  |  Mean: {col.mean_val}  |  Med: {col.median_val}"
                elif col.top_values:
                    parts = [f"'{v['value']}': {v['percentage']}%" for v in col.top_values[:3]]
                    detail = "Top: " + ", ".join(parts)
                else:
                    detail = "—"
                    
                ctk.CTkLabel(row_f, text=detail, anchor="w", text_color="gray85").pack(side="left", padx=5, fill="x", expand=True)


if __name__ == "__main__":
    app = ctk.CTk()
    DataVerseApp(app)
    app.mainloop()
    logger.info("Application shutting down.")
