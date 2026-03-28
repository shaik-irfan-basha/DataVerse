# 🔮 Natural Language to SQL

**Phase 1: Data Preparation + LLM SQL Generation**

A Python project that converts natural language questions into SQL queries using WikiSQL dataset and Groq LLM API.

---

## 📁 Project Structure

```
NL_to_SQL/
├── main.py           # Python GUI (run this)
├── data_loader.py    # WikiSQL JSONL loader
├── prompt_builder.py # LLM prompt builder
├── llm_client.py     # Groq API client
├── config.py         # Configuration
├── .env              # API key
├── requirements.txt  # Dependencies
└── data/             # WikiSQL files (auto-downloaded)
```

---

## 🔧 Data Structure (WikiSQL)

```json
{
  "table_id": "1-10015132-11",
  "question": "How many episodes were there?",
  "sql": {
    "sel": 0,           // Column index
    "agg": 3,           // 0=none, 1=MAX, 2=MIN, 3=COUNT, 4=SUM, 5=AVG
    "conds": [[2, 0, "Season 1"]]  // [col, op, value], op: 0='=', 1='>', 2='<'
  }
}
```

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API key in .env
GROQ_API_KEY=your_key_here

# 3. Run
python main.py
```

Get free API key: [console.groq.com](https://console.groq.com/)

---

## 📊 Dataset

- **Source**: Salesforce WikiSQL
- **Size**: 56,355 training examples
- **Format**: JSONL with SQL structure (sel, conds, agg)

---

## ✅ Phase 1 Complete

- [x] WikiSQL JSONL loading
- [x] SQL structure parsing
- [x] Table schema extraction
- [x] LLM SQL generation
- [x] Python GUI
