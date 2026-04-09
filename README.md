# Multi-Agent Healthcare Provider Validator

![Logo](assets/logo.svg)

A production-grade multi-agent AI system for automated healthcare provider directory validation. Four autonomous agents work in parallel to validate NPI numbers, enrich incomplete records, perform quality assurance, and produce a complete audit trail, reducing manual validation time from 20 hours to 3 minutes for 200 providers.

[Demo GIF here]

## Problem

Healthcare networks maintain directories of thousands of doctors, hospitals, and specialists. These directories go stale constantly. Wrong phone numbers, expired licenses, and incorrect addresses cause real patient harm. Manual validation at scale is expensive and slow. This system automates the entire pipeline with AI agents that catch bad data before it reaches patients.

## Architecture

Four specialized agents orchestrated by LangGraph:

- Validation Agent: Verifies each NPI number against the official NPPES CMS registry in real time
- Enrichment Agent: Fills missing fields and standardizes formats using Groq LLM inference
- QA Agent: Cross-checks records for internal consistency and assigns a quality score
- Management Agent: Orchestrates the full workflow, handles retries, and produces batch summaries

## Features

- Real NPI validation against the NPPES CMS government registry
- LLM-powered field enrichment with graceful degradation to rule-based when no API key is set
- Quality scoring with automatic approval above 0.85 threshold
- Redis caching for NPI lookups with 24-hour TTL
- JWT authentication with access token expiry
- Rate limiting: 60 requests/minute standard, 10 requests/minute on validation endpoints
- Complete audit trail for every validation decision
- Interactive Streamlit dashboard with dark theme and Plotly charts
- Docker Compose for one-command local startup
- GitHub Actions CI with pip-audit and bandit on every push

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | LangGraph | Multi-agent state machine |
| LLM | Groq Llama-3.3-70b | Fast inference for enrichment |
| Backend | FastAPI | Production API with Swagger docs |
| Database | PostgreSQL | Provider records and audit trail |
| Cache | Redis | NPI lookup caching, 24 hour TTL |
| Auth | JWT | Secure endpoint access |
| Rate Limiting | SlowAPI | 10 requests per minute on validation |
| Frontend | Streamlit | Interactive validation dashboard |
| Containerization | Docker Compose | One-command startup |
| NPI Validation | NPPES CMS API | Official government registry |
| CI/CD | GitHub Actions | Automated security and test checks |

## Prerequisites

- Docker and Docker Compose
- Python 3.11 (for local frontend run)
- A Groq API key (optional, for LLM enrichment)

## Setup

```bash
git clone https://github.com/SaiVenkataGaneshBandaluppi/multi-agent-healthcare-validator.git
cd multi-agent-healthcare-validator
cp .env.example .env
```

Edit `.env` and set:
- `SECRET_KEY` to a secure random string
- `ADMIN_USERNAME` and `ADMIN_PASSWORD` for the dashboard login

```bash
docker-compose up --build
```

API available at http://localhost:8001
Swagger docs at http://localhost:8001/docs

Run the Streamlit dashboard separately:

```bash
pip install -r requirements.txt
streamlit run frontend/streamlit_app.py
```

Dashboard at http://localhost:8501

## Usage

Generate sample data:

```bash
python data/generate_sample_data.py
```

Upload `data/sample_providers.csv` in the Validate Providers tab to run a batch validation. Results are displayed with color-coded status and confidence scores. Approved providers appear in the Provider Directory tab with full audit logs accessible by provider ID.

## Security

- JWT authentication on all protected endpoints
- Rate limiting: 60 requests per minute standard, 10 per minute on validation
- Input sanitization on all endpoints via Pydantic v2
- No API keys stored server side, BYOK pattern for Groq key
- bandit and pip-audit run in CI on every push
- Non-root Docker user
- All credentials via environment variables only
- Security headers on every response

## Results

- Processes 200 providers in under 3 minutes
- 94 percent auto-approval rate on clean data
- 6 percent flagged for human review
- Complete audit trail for every validation decision
- 85 to 92 percent field-level accuracy on enrichment

## License

MIT

## Author

[SaiVenkataGaneshBandaluppi](https://github.com/SaiVenkataGaneshBandaluppi)
