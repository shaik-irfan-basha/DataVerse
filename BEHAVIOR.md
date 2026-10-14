# DataVerse — Current Behavior & Limitations

This document captures the exact behavior, supported workflows, and known limitations of the DataVerse application as of Phase 2, prior to any structural refactoring.

## Workflows & Current Functionality

### 1. Application Startup
- **Behavior**: The application launches as a desktop GUI using `customtkinter`. 
- **State Initialization**: Upon startup, a `DataConnector` instance is created, which provisions a shared, thread-safe (via `threading.Lock`) in-memory SQLite database (`:memory:`).

### 2. File Loading
- **Behavior**: The user clicks "Upload Data File", triggering a file picker dialog. The loading process runs in a background thread (`_load_file_thread`) to prevent freezing the UI.
- **Data Connector Pipelines**:
  - **CSV Loading**: Reads the file via `pandas.read_csv`, replacing non-alphanumeric characters in the filename to generate a safe SQL table name, and writes it to the in-memory SQLite database.
  - **JSON Loading**: Reads the JSON file. If it contains a list of objects, it maps them directly to rows. If it contains a nested dictionary, it attempts to find the first list of dictionaries to convert into a table.
  - **Excel (Multi-sheet) Loading**: Reads the workbook via `pandas.read_excel(sheet_name=None)`. Iterates over all sheets, creating a separate SQLite table for each sheet (named `filename_sheetname`).
  - **SQLite Loading**: Reads an external `.db` or `.sqlite` file. It queries `sqlite_master` for all tables, loads them sequentially into Pandas DataFrames, and writes them into the shared in-memory database.

### 3. Schema Display
- **Behavior**: After a file is loaded, the application retrieves the table schemas by querying `PRAGMA table_info` for all active tables.
- **UI Update**: The schema is displayed as formatted text (`TABLE: name (col1 type, col2 type)`) in the right-hand sidebar. The file label updates to show the total number of tables and rows loaded.

### 4. Natural Language Question Flow
- **Behavior**: The user enters a question in the text box and clicks "Ask / Generate SQL". The UI displays a "Thinking..." status and disables the button. The request is dispatched to a background thread (`_generate_and_run_thread`).

### 5. Ambiguity Detection and Clarification
- **Behavior**: The system always passes the user's question, the database schema, and a 3-row sample of the data to the `Clarification Engine`.
- **LLM Prompting**: It uses a Pydantic-based JSON schema to force the LLM to output a structured analysis (whether the question is ambiguous, clarification questions, options, and SQL if clear).
- **Interactive Flow**: If the LLM returns `is_ambiguous: True`, a modal `ClarificationDialog` appears over the main UI. The user must select an option or type a custom clarification. This loop continues, appending the history, until the LLM resolves the ambiguity (`is_ambiguous: False`).

### 6. SQL Generation & Editing
- **Behavior**: Once the question is deemed clear, the LLM provides a SQL query. 
- **UI Display**: The query is cleaned (Markdown formatting removed, truncated at the first semicolon) and injected into the editable "Generated SQL" text box. The user can manually review and edit this SQL before execution.

### 7. SQL Execution & Result Display
- **Behavior**: Clicking "Run SQL" executes the query currently in the text box via the `SQLExecutor`.
- **Safety**: The `SQLExecutor` performs basic string-prefix validation. If the query string begins with prohibited keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `REPLACE`), it blocks execution and returns an error dictionary.
- **Results**: If execution succeeds, the results (columns and rows) are rendered in a `ttk.Treeview` widget. The columns automatically size themselves based on the headers.

### 8. Error Handling
- **Behavior**: 
  - File loading errors show a message box and turn the file label red (`❌ Error: ...`).
  - LLM API errors or JSON parsing failures display red text in the application status label.
  - SQL execution errors (syntax errors, blocked queries) highlight the text in red inside the Results tab.

---

## Known Limitations (Phase 2 Snapshot)

1. **Architecture**: The `main.py` file is a monolithic GUI script mixed with business logic (e.g., prompt dispatching, thread management, and UI updates).
2. **SQL Safety**: The `SQLExecutor` blocks destructive operations using simple case-insensitive string matching. This is easily bypassed by advanced SQL injection or subqueries (e.g., `WITH x AS (...) UPDATE ...`).
3. **LLM Error Recovery**: There is no retry loop if the LLM fails to return valid JSON or if the generated SQL is invalid. The process simply stops and displays the error to the user.
4. **Data Persistence**: Because the database is `:memory:`, all data and state are lost when the application closes.
5. **Analytics/Evaluation**: There is no history tracking, logging, or mechanism to benchmark LLM accuracy.
6. **Dead Code**: The `data_loader.py` file (WikiSQL support) is present in the codebase but entirely unused by the current application workflows.
