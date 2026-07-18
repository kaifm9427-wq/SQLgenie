<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/SQL-Genie-7c3aed?style=for-the-badge&logo=python&logoColor=white&labelColor=1a1a2e">
    <img alt="SQL Genie" src="https://img.shields.io/badge/SQL-Genie-7c3aed?style=for-the-badge&logo=python&logoColor=white&labelColor=f0f0f0">
  </picture>
</p>

<p align="center">
  <b>Natural language to SQL, powered by a self-correcting multi-agent AI pipeline.</b><br>
  Built by <a href="https://github.com/kaifm9427-wq">Mohammed Kaif</a>
</p>

<p align="center">
  <a href="#-features"><img src="https://img.shields.io/badge/features-✓-22c55e?style=flat-square" alt="Features"></a>
  <a href="#-architecture"><img src="https://img.shields.io/badge/architecture-→-3b82f6?style=flat-square" alt="Architecture"></a>
  <a href="#-quick-start"><img src="https://img.shields.io/badge/quick_start-→-f59e0b?style=flat-square" alt="Quick Start"></a>
  <a href="#-tech-stack"><img src="https://img.shields.io/badge/stack-→-ef4444?style=flat-square" alt="Tech Stack"></a>
</p>

<br>

---

https://github.com/user-attachments/assets/03ca49ff-fe9b-4ae0-8f55-fa0e88ed38a8

## ✦ Features

<table>
<tr>
<td width="50%">

**🧠 Multi-Agent Pipeline**  
Five specialised LLM agents collaborate — guardrail, generator, explainer, critic/fixer, and formatter — to produce accurate, safe SQL every time.

**🔒 Security-First**  
Two-layer guardrail: static keyword detection blocks destructive intent, followed by an LLM semantic check. Immutable read-only execution.

</td>
<td width="50%">

**🔄 Self-Correcting Loop**  
When SQL execution fails, the critic agent diagnoses the issue and the fixer agent repairs it — no manual intervention needed.

**📊 Rich Results**  
Conversational answers, auto-generated charts (Chart.js), downloadable CSV/JSON, explanation panel, and full query history.

</td>
</tr>
<tr>
<td width="50%">

**🌐 Multi-DB Support**  
SQLite, PostgreSQL, and MySQL — connect to any database with live schema introspection and RAG-powered vector indexing.

**☁️ Flexible LLM Providers**  
Choose between local Ollama models (qwen2.5-coder) or cloud Groq (llama-3.3-70b) — zero code changes.

</td>
<td width="50%">

**💬 Conversation Threading**  
Multi-turn conversations with context memory — ask follow-up questions naturally.

**🔐 Auth Built-In**  
JWT-based authentication with API key management, Neon PostgreSQL persistence, and email notifications.

</td>
</tr>
</table>

## ✦ Architecture

```
User Query
    │
    ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Guardrail   │────▶│   Generator   │────▶│  Explainer   │
│  (LLM + regex)│     │  (SQL writer) │     │ (translator) │
└─────────────┘     └──────────────┘     └─────────────┘
                                              │
                                              ▼
                                      ┌──────────────┐
                                      │  Execute SQL  │
                                      │  (read-only)  │
                                      └──────┬───────┘
                                             │
                                    ┌────────┴────────┐
                                    ▼                 ▼
                              ┌──────────┐     ┌────────────┐
                              │  Success  │     │  Failure    │
                              │          │     │            │
                              ▼          │     ▼            │
                       ┌──────────┐      │  ┌──────────┐    │
                       │ Formatter │      │  │  Critic   │    │
                       │ (LLM)    │      │  │ (auditor) │    │
                       └──────────┘      │  └────┬─────┘    │
                              │          │       │          │
                              │          │  ┌────▼─────┐    │
                              │          │  │  Fixer    │────│
                              │          │  │ (repair)  │    │
                              │          │  └──────────┘    │
                              ▼          ▼                  ▼
                        ┌───────────────────────────────────┐
                        │       Answer + SQL + Chart         │
                        └───────────────────────────────────┘
```

## ✦ Quick Start

```bash
# Clone
git clone https://github.com/kaifm9427-wq/SQLgenie.git
cd SQLgenie

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env   # add your GROQ_API_KEY and AUTH_DATABASE_URL

# Run
python3 main.py
# → http://localhost:8000
```

**Connect a database** → click the **Connect** button → enter PostgreSQL/SQLite/MySQL credentials → ask anything in plain English.

### Example Queries

| You ask | SQL Genie generates |
|---|---|
| "how many products" | `SELECT COUNT(*) FROM products` |
| "top 5 customers by spend" | `SELECT ... JOIN ... GROUP BY ... ORDER BY ... LIMIT 5` |
| "monthly sales trend" | `SELECT strftime(...), SUM(...) FROM orders GROUP BY ...` |

## ✦ Tech Stack

<p>
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangChain-1C3C3C?style=flat-square&logo=langchain&logoColor=white" alt="LangChain">
  <img src="https://img.shields.io/badge/Groq-FF6600?style=flat-square&logo=groq&logoColor=white" alt="Groq">
  <img src="https://img.shields.io/badge/Ollama-000000?style=flat-square&logo=ollama&logoColor=white" alt="Ollama">
  <img src="https://img.shields.io/badge/ChromaDB-5A67D8?style=flat-square&logo=chromadb&logoColor=white" alt="ChromaDB">
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy">
  <img src="https://img.shields.io/badge/JWT-000000?style=flat-square&logo=jsonwebtokens&logoColor=white" alt="JWT">
</p>

## ✦ Deploy

**One-click deploy to Koyeb:**

[![Deploy to Koyeb](https://img.shields.io/badge/Deploy_to_Koyeb-121212?style=for-the-badge&logo=koyeb&logoColor=white)](https://app.koyeb.com)

Set environment variables:
- `GROQ_API_KEY` — your Groq API key
- `AUTH_DATABASE_URL` — your Neon PostgreSQL connection string

---

<p align="center">
  <sub>Built by <a href="https://github.com/kaifm9427-wq"><b>Mohammed Kaif</b></a></sub>
  <br>
  <sub>SQL Genie — Natural Language to SQL</sub>
</p>
