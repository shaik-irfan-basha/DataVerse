"""
main.py - NL to SQL Converter with Python GUI

Phase 1: Data Preparation and LLM SQL Generation
- WikiSQL dataset integration
- SQL structure parsing (sel, conds, agg)
- LLM-based SQL generation via Groq API

Run with: python main.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import json

from dotenv import load_dotenv
load_dotenv()

from data_loader import WikiSQLLoader, get_schema_string, AGG_OPS, COND_OPS
from prompt_builder import build_sql_prompt
from llm_client import LLMClient


class NLtoSQLApp:
    """
    Natural Language to SQL Converter - Python GUI
    
    Features:
    - Input your own question and table schema
    - Load examples from WikiSQL dataset
    - View SQL structure (sel, conds, agg)
    - Generate SQL using Groq LLM
    """
    
    def __init__(self, root):
        self.root = root
        self.root.title("NL to SQL Generator - Phase 1")
        self.root.geometry("800x700")
        self.root.minsize(600, 500)
        self.root.configure(bg="#0f0f1a")
        
        # Data
        self.llm_client = None
        self.loader = None
        self.current_example = None
        self.example_index = 0
        
        # Create UI
        self.create_widgets()
        
        # Load initial data
        self.root.after(100, self.load_dataset)
    
    def create_widgets(self):
        """Create all UI widgets."""
        # Main container with padding
        main_frame = tk.Frame(self.root, bg="#0f0f1a", padx=25, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # =====================================================================
        # HEADER
        # =====================================================================
        header_frame = tk.Frame(main_frame, bg="#0f0f1a")
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        title = tk.Label(
            header_frame,
            text="🔮 Natural Language to SQL",
            font=("Segoe UI", 22, "bold"),
            fg="#00d9ff",
            bg="#0f0f1a"
        )
        title.pack(side=tk.LEFT)
        
        phase_label = tk.Label(
            header_frame,
            text="Phase 1",
            font=("Segoe UI", 10),
            fg="#00ff88",
            bg="#1a1a3e",
            padx=10,
            pady=3
        )
        phase_label.pack(side=tk.RIGHT)
        
        # =====================================================================
        # INPUT SECTION
        # =====================================================================
        input_frame = tk.Frame(main_frame, bg="#1a1a2e", padx=15, pady=15)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Question
        q_label = tk.Label(
            input_frame,
            text="💬 Question (Natural Language)",
            font=("Segoe UI", 10, "bold"),
            fg="#00d9ff",
            bg="#1a1a2e",
            anchor="w"
        )
        q_label.pack(fill=tk.X)
        
        self.question_entry = tk.Text(
            input_frame,
            height=2,
            font=("Segoe UI", 11),
            bg="#2a2a4e",
            fg="white",
            insertbackground="white",
            relief="flat",
            padx=10,
            pady=8,
            wrap=tk.WORD
        )
        self.question_entry.pack(fill=tk.X, pady=(5, 12))
        
        # Columns and Table in same row
        col_table_frame = tk.Frame(input_frame, bg="#1a1a2e")
        col_table_frame.pack(fill=tk.X)
        
        # Columns
        col_frame = tk.Frame(col_table_frame, bg="#1a1a2e")
        col_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        col_label = tk.Label(
            col_frame,
            text="📊 Table Schema (comma-separated columns)",
            font=("Segoe UI", 10, "bold"),
            fg="#00d9ff",
            bg="#1a1a2e",
            anchor="w"
        )
        col_label.pack(fill=tk.X)
        
        self.columns_entry = tk.Entry(
            col_frame,
            font=("Segoe UI", 10),
            bg="#2a2a4e",
            fg="white",
            insertbackground="white",
            relief="flat"
        )
        self.columns_entry.pack(fill=tk.X, pady=(5, 0), ipady=6)
        
        # Table name
        table_frame = tk.Frame(col_table_frame, bg="#1a1a2e", width=150)
        table_frame.pack(side=tk.RIGHT)
        table_frame.pack_propagate(False)
        
        table_label = tk.Label(
            table_frame,
            text="📁 Table",
            font=("Segoe UI", 10, "bold"),
            fg="#00d9ff",
            bg="#1a1a2e",
            anchor="w"
        )
        table_label.pack(fill=tk.X)
        
        self.table_entry = tk.Entry(
            table_frame,
            font=("Segoe UI", 10),
            bg="#2a2a4e",
            fg="white",
            insertbackground="white",
            relief="flat"
        )
        self.table_entry.insert(0, "table")
        self.table_entry.pack(fill=tk.X, pady=(5, 0), ipady=6)
        
        # =====================================================================
        # SQL STRUCTURE (from dataset)
        # =====================================================================
        struct_frame = tk.Frame(main_frame, bg="#1a1a2e", padx=15, pady=10)
        struct_frame.pack(fill=tk.X, pady=(0, 10))
        
        struct_header = tk.Frame(struct_frame, bg="#1a1a2e")
        struct_header.pack(fill=tk.X)
        
        struct_label = tk.Label(
            struct_header,
            text="🔧 SQL Structure (from WikiSQL)",
            font=("Segoe UI", 10, "bold"),
            fg="#ffaa00",
            bg="#1a1a2e"
        )
        struct_label.pack(side=tk.LEFT)
        
        self.struct_text = tk.Label(
            struct_frame,
            text="sel: - | agg: - | conds: -",
            font=("Consolas", 10),
            fg="#888",
            bg="#1a1a2e",
            anchor="w"
        )
        self.struct_text.pack(fill=tk.X, pady=(5, 0))
        
        # =====================================================================
        # INFO LABEL
        # =====================================================================
        info_label = tk.Label(
            main_frame,
            text="ℹ️ Schema and question are passed as text to LLM (database stays local)",
            font=("Segoe UI", 9, "italic"),
            fg="#6a8a9a",
            bg="#0f0f1a"
        )
        info_label.pack(fill=tk.X, pady=(0, 8))
        
        # =====================================================================
        # BUTTONS
        # =====================================================================
        btn_frame = tk.Frame(main_frame, bg="#0f0f1a")
        btn_frame.pack(fill=tk.X, pady=(5, 10))
        
        # Generate button
        self.generate_btn = tk.Button(
            btn_frame,
            text="⚡ Generate SQL",
            font=("Segoe UI", 11, "bold"),
            bg="#00d9ff",
            fg="#0f0f1a",
            activebackground="#00ff88",
            activeforeground="#0f0f1a",
            relief="flat",
            cursor="hand2",
            width=20,
            command=self.generate_sql
        )
        self.generate_btn.pack(side=tk.LEFT, ipady=8)
        
        # Load next example button
        self.next_btn = tk.Button(
            btn_frame,
            text="📥 Load Next Example",
            font=("Segoe UI", 10),
            bg="#2a2a4e",
            fg="white",
            activebackground="#3a3a5e",
            relief="flat",
            cursor="hand2",
            command=self.load_next_example
        )
        self.next_btn.pack(side=tk.LEFT, padx=(10, 0), ipady=6)
        
        # Clear button
        clear_btn = tk.Button(
            btn_frame,
            text="🗑️ Clear",
            font=("Segoe UI", 10),
            bg="#2a2a4e",
            fg="white",
            activebackground="#3a3a5e",
            relief="flat",
            cursor="hand2",
            command=self.clear_all
        )
        clear_btn.pack(side=tk.RIGHT, ipady=6)
        
        # =====================================================================
        # RESULTS SECTION
        # =====================================================================
        result_frame = tk.Frame(main_frame, bg="#0f0f1a")
        result_frame.pack(fill=tk.BOTH, expand=True)
        
        # Generated SQL
        gen_label = tk.Label(
            result_frame,
            text="🤖 Generated SQL (from LLM)",
            font=("Segoe UI", 10, "bold"),
            fg="#00ff88",
            bg="#0f0f1a",
            anchor="w"
        )
        gen_label.pack(fill=tk.X)
        
        self.result_text = scrolledtext.ScrolledText(
            result_frame,
            height=4,
            font=("Consolas", 12),
            bg="#0d1117",
            fg="#00ff88",
            insertbackground="white",
            relief="flat",
            padx=12,
            pady=10
        )
        self.result_text.pack(fill=tk.X, pady=(5, 10))
        
        # Reference SQL (for comparison only - not used by model)
        ref_label = tk.Label(
            result_frame,
            text="📚 Reference SQL (for comparison only - not sent to LLM)",
            font=("Segoe UI", 9),
            fg="#5a5a6a",
            bg="#0f0f1a",
            anchor="w"
        )
        ref_label.pack(fill=tk.X)
        
        self.ref_text = scrolledtext.ScrolledText(
            result_frame,
            height=2,
            font=("Consolas", 10),
            bg="#15151a",
            fg="#666",
            insertbackground="white",
            relief="flat",
            padx=12,
            pady=8
        )
        self.ref_text.pack(fill=tk.X, pady=(3, 0))
        
        # =====================================================================
        # STATUS BAR
        # =====================================================================
        status_frame = tk.Frame(main_frame, bg="#0f0f1a")
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_label = tk.Label(
            status_frame,
            text="Initializing...",
            font=("Segoe UI", 9),
            fg="#5a6a8a",
            bg="#0f0f1a",
            anchor="w"
        )
        self.status_label.pack(side=tk.LEFT)
        
        self.example_label = tk.Label(
            status_frame,
            text="",
            font=("Segoe UI", 9),
            fg="#5a6a8a",
            bg="#0f0f1a",
            anchor="e"
        )
        self.example_label.pack(side=tk.RIGHT)
    
    def load_dataset(self):
        """Load WikiSQL dataset."""
        try:
            self.status_label.config(text="Loading WikiSQL dataset...")
            self.root.update()
            
            self.loader = WikiSQLLoader()
            examples = self.loader.load_jsonl("train")
            
            self.status_label.config(text=f"Dataset loaded: {len(examples):,} examples")
            self.load_example(0)
            
        except Exception as e:
            self.status_label.config(text=f"Dataset load failed: {str(e)[:40]}")
    
    def load_example(self, index):
        """Load a specific example from the dataset."""
        if not self.loader:
            return
        
        try:
            self.current_example = self.loader.get_example(index, "train")
            self.example_index = index
            
            # Clear and fill inputs
            self.question_entry.delete("1.0", tk.END)
            self.question_entry.insert("1.0", self.current_example["question"])
            
            self.columns_entry.delete(0, tk.END)
            self.columns_entry.insert(0, get_schema_string(self.current_example["table_schema"]))
            
            self.table_entry.delete(0, tk.END)
            self.table_entry.insert(0, self.current_example["table_id"])
            
            # Show SQL structure
            sql = self.current_example["sql"]
            agg_str = AGG_OPS[sql.get("agg", 0)] or "None"
            conds = sql.get("conds", [])
            conds_str = f"{len(conds)} condition(s)" if conds else "None"
            self.struct_text.config(
                text=f"sel: {sql.get('sel', '-')} | agg: {agg_str} | conds: {conds_str}"
            )
            
            # Show reference SQL
            self.ref_text.delete("1.0", tk.END)
            self.ref_text.insert("1.0", self.current_example["sql_readable"])
            
            # Clear generated result
            self.result_text.delete("1.0", tk.END)
            
            self.example_label.config(text=f"Example #{index + 1}")
            
        except Exception as e:
            self.status_label.config(text=f"Error loading example: {e}")
    
    def load_next_example(self):
        """Load the next example from dataset."""
        self.example_index += 1
        if self.loader and self.example_index >= len(self.loader.examples.get("train", [])):
            self.example_index = 0
        self.load_example(self.example_index)
    
    def clear_all(self):
        """Clear all inputs and outputs."""
        self.question_entry.delete("1.0", tk.END)
        self.columns_entry.delete(0, tk.END)
        self.table_entry.delete(0, tk.END)
        self.table_entry.insert(0, "table")
        self.result_text.delete("1.0", tk.END)
        self.ref_text.delete("1.0", tk.END)
        self.struct_text.config(text="sel: - | agg: - | conds: -")
        self.status_label.config(text="Cleared")
    
    def generate_sql(self):
        """Generate SQL from the input using LLM."""
        question = self.question_entry.get("1.0", tk.END).strip()
        columns = self.columns_entry.get().strip()
        table_name = self.table_entry.get().strip() or "table"
        
        if not question:
            messagebox.showwarning("Input Required", "Please enter a question.")
            return
        
        if not columns:
            messagebox.showwarning("Input Required", "Please enter column names.")
            return
        
        # Disable button
        self.generate_btn.config(state=tk.DISABLED, text="Generating...")
        self.status_label.config(text="Sending to LLM...")
        self.result_text.delete("1.0", tk.END)
        self.root.update()
        
        # Run in thread
        thread = threading.Thread(
            target=self._generate_sql_thread,
            args=(question, columns, table_name)
        )
        thread.start()
    
    def _generate_sql_thread(self, question, columns, table_name):
        """Background thread for SQL generation."""
        try:
            column_list = [c.strip() for c in columns.split(",") if c.strip()]
            prompt = build_sql_prompt(question, column_list, table_name)
            
            if self.llm_client is None:
                self.llm_client = LLMClient()
            
            sql = self.llm_client.generate_sql(prompt)
            self.root.after(0, lambda: self._show_result(sql))
            
        except ValueError as e:
            self.root.after(0, lambda: self._show_error(str(e)))
        except Exception as e:
            self.root.after(0, lambda: self._show_error(f"Error: {str(e)}"))
    
    def _show_result(self, sql):
        """Display generated SQL."""
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", sql)
        self.generate_btn.config(state=tk.NORMAL, text="⚡ Generate SQL")
        self.status_label.config(text="✅ SQL generated successfully!")
    
    def _show_error(self, error_msg):
        """Display error message."""
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", f"Error: {error_msg}")
        self.generate_btn.config(state=tk.NORMAL, text="⚡ Generate SQL")
        self.status_label.config(text="❌ Generation failed")
        
        if "API key" in error_msg:
            messagebox.showerror(
                "API Key Required",
                "Create a .env file with:\nGROQ_API_KEY=your_key\n\n"
                "Get free key: console.groq.com"
            )


def main():
    """Launch the NL to SQL application."""
    print("=" * 50)
    print("  NL to SQL - Phase 1")
    print("  Starting GUI...")
    print("=" * 50)
    
    root = tk.Tk()
    app = NLtoSQLApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
