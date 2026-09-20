"""
main.py - NL to SQL Converter with Universal Dataset Support & Clarification Engine

Phase 3:
- Modern UI using CustomTkinter
- Clarification Engine for handling ambiguous questions
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os

from dotenv import load_dotenv
load_dotenv()

from data_connector import DataConnector
from llm_client import LLMClient
from sql_executor import SQLExecutor
import config

# Set modern theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class NLtoSQLApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🔮 NL to SQL — Ask Your Data Anything")
        self.root.geometry("1000x850")
        self.root.minsize(800, 700)
        
        # Core components
        self.connector = DataConnector()
        self.executor = SQLExecutor()
        self.llm_client = None
        
        # Build UI
        self.create_widgets()
    
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
        
        # -- SECTION 4: RESULTS --
        self._create_results_section(self.main_frame)
        
        # -- STATUS BAR --
        self._create_status_bar(self.root)
    
    def _create_header(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        
        title = ctk.CTkLabel(
            header,
            text="🔮 NL to SQL",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#00d9ff"
        )
        title.pack(side="left")
    
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
            text="📁 Upload File",
            font=ctk.CTkFont(weight="bold"),
            command=self.upload_file,
            width=120
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
        self.schema_text.pack(fill="x", padx=15, pady=(0, 15))
    
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
            height=80,
            font=ctk.CTkFont(size=14),
            border_width=1,
            corner_radius=8
        )
        self.question_entry.pack(fill="x", padx=15, pady=(5, 15))
        self.question_entry.insert("1.0", "e.g. Who is our best customer?")
        self.question_entry.bind("<FocusIn>", self._on_question_focus_in)
        self.question_entry.bind("<FocusOut>", self._on_question_focus_out)
        
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(0, 15))
        
        self.generate_btn = ctk.CTkButton(
            btn_row,
            text="⚡ Generate SQL & Run",
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
            text="🗑️ Clear",
            fg_color="transparent",
            border_width=1,
            text_color="gray80",
            hover_color="gray30",
            command=self.clear_all,
            width=80
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
            text="▶️ Run SQL",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#1f538d",
            width=100,
            command=self.run_sql
        )
        self.run_btn.pack(side="right")
        
        self.sql_text = ctk.CTkTextbox(
            frame,
            height=100,
            font=ctk.CTkFont(family="Consolas", size=14),
            text_color="#00ff88",
            fg_color="#0d1117",
            border_width=1,
            corner_radius=8
        )
        self.sql_text.pack(fill="x")
    
    def _create_results_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        
        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 5))
        
        ctk.CTkLabel(
            top_row,
            text="📊 Results",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffaa00"
        ).pack(side="left")
        
        self.result_info = ctk.CTkLabel(
            top_row,
            text="",
            text_color="gray60"
        )
        self.result_info.pack(side="right")
        
        # Style ttk.Treeview to match CustomTkinter
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
        
        tree_frame = ctk.CTkFrame(frame, corner_radius=8)
        tree_frame.pack(fill="both", expand=True)
        
        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        self.tree = ttk.Treeview(
            tree_frame,
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
            show="headings"
        )
        
        y_scroll.config(command=self.tree.yview)
        x_scroll.config(command=self.tree.xview)
        
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.answer_label = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(size=20, weight="bold"),
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
    
    # =========================================================================
    # LOGIC
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
            table_names = self.connector.load_file(file_path)
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
    
    def _on_file_error(self, error_msg: str):
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
        
        threading.Thread(target=self._generate_and_run_thread, args=(question,)).start()
    
    def _generate_and_run_thread(self, question: str):
        from clarification_engine import build_analysis_prompt
        
        clarification_history = ""
        try:
            if self.llm_client is None:
                self.llm_client = LLMClient()
                
            schema_str = self.connector.get_schema_string()
            sample_data = self.connector.get_sample_data_string(config.MAX_SAMPLE_ROWS)

            while True:
                prompt = build_analysis_prompt(question, schema_str, sample_data, clarification_history)
                self.root.after(0, lambda: self.status_label.configure(text="Analyzing query intent..."))
                
                analysis = self.llm_client.generate_json(prompt)
                
                if analysis.get("is_ambiguous", False):
                    cq = analysis.get("clarification_question", "Please clarify.")
                    opts = analysis.get("options", [])
                    
                    user_choice = self._ask_user_clarification(cq, opts)
                    if not user_choice:
                        self.root.after(0, lambda: self.status_label.configure(text="Cancelled by user."))
                        self.root.after(0, lambda: self.generate_btn.configure(state="normal", text="⚡ Generate SQL & Run"))
                        return
                    
                    clarification_history += f"AI: {cq}\nUser: {user_choice}\n\n"
                    continue
                else:
                    sql = analysis.get("sql_query", "")
                    if not sql:
                        raise ValueError("No SQL generated.")
                    
                    sql = self._clean_sql(sql)
                    self.root.after(0, lambda: self._show_generated_sql(sql))
                    self.root.after(0, lambda: self.status_label.configure(text="Executing query..."))
                    
                    result = self.executor.execute(self.connector.get_connection(), sql)
                    self.root.after(0, lambda: self._show_results(result))
                    break
                    
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._show_error(err))

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
        self.status_label.configure(text="Executing SQL...")
        result = self.executor.execute(self.connector.get_connection(), sql)
        self._show_results(result)
    
    def _show_generated_sql(self, sql: str):
        self.sql_text.delete("1.0", "end")
        self.sql_text.insert("1.0", sql)
        self.status_label.configure(text="SQL generated — executing query...")
    
    def _show_results(self, result: dict):
        self.generate_btn.configure(state="normal", text="⚡ Generate SQL & Run")
        
        if not result["success"]:
            self.status_label.configure(text="❌ Query failed")
            self.answer_label.configure(text=f"❌ {result['error']}", text_color="#ff4444")
            return
        
        self._clear_results()
        cols, rows = result["columns"], result["rows"]
        
        if not cols:
            self.status_label.configure(text="✅ Query executed (no results)")
            self.answer_label.configure(text="Query executed successfully — no rows returned.", text_color="#ffaa00")
            return
        
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
    
    def _show_error(self, error_msg: str):
        self.generate_btn.configure(state="normal", text="⚡ Generate SQL & Run")
        self.status_label.configure(text="❌ Generation failed")
        self.answer_label.configure(text=f"❌ {error_msg}", text_color="#ff4444")
    
    def _clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []
        self.result_info.configure(text="")
        self.answer_label.configure(text="")
    
    def clear_all(self):
        self.question_entry.delete("1.0", "end")
        self.question_entry.insert("1.0", "e.g. Who is our best customer?")
        self.sql_text.delete("1.0", "end")
        self._clear_results()
        self.status_label.configure(text="Cleared")
    
    @staticmethod
    def _clean_sql(sql: str) -> str:
        sql = sql.strip()
        if sql.startswith("```sql"): sql = sql[6:]
        elif sql.startswith("```"): sql = sql[3:]
        if sql.endswith("```"): sql = sql[:-3]
        sql = sql.strip()
        if ";" in sql: sql = sql[:sql.index(";") + 1]
        return sql.strip()


class ClarificationDialog(ctk.CTkToplevel):
    def __init__(self, parent, question: str, options: list, event, result_container):
        super().__init__(parent)
        self.title("🤔 Clarification Needed")
        self.geometry("550x400")
        self.attributes('-topmost', 'true')
        
        # Center dialog
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

if __name__ == "__main__":
    app = ctk.CTk()
    NLtoSQLApp(app)
    app.mainloop()
