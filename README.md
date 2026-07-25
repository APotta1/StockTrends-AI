# StockTrends-AI

A full-stack stock research tool built from an **AI-engineering** point of view.
It shows price trends, quarterly earnings, and news — but the part that carries
the project is a **filing-extraction pipeline graded by an evaluation harness**,
and an honest "when to pay attention" feature that is a transparent context
engine, **not** a fabricated buy/sell signal.

> **Live demo:** enable GitHub Pages (Settings → Pages → Deploy from branch →
> `main` → `/docs`) to serve the dashboard at
> `https://<user>.github.io/StockTrends-AI/`. The Pages build has data inlined,
> so the link can't break from an API outage or an expired key.

---

## Why this isn't another stock dashboard

A React app that draws a price line off a public API is an afternoon of glue,
and an interviewer recognizes it instantly. The hard, interview-relevant parts
of *this* problem are:

1. **Reading numbers out of filings is genuinely error-prone**, and the errors
   have *structure* — a revenue figure off by 1,000,000× (scale error), the
   column next door (adjacent-column read), or a value that isn't in the filing
   at all (hallucination). A single accuracy number hides all three.
2. **You can grade it automatically.** SEC XBRL is machine-readable truth, so
   every LLM extraction is checked against what the company actually filed —
   **no manual labeling.** That's the whole trick that makes the eval cheap.
3. **The "when to buy" trap.** Ship a predictive signal and you'll get exactly
   one interview question about look-ahead bias, and the answer defines the rest
   of the conversation. This project **deliberately refuses to predict** and
   explains why — a stronger position than defending a leaky backtest.

---

## Architecture

```
┌──────────────┐   XBRL (truth)     ┌─────────────────────┐
│  SEC EDGAR   │───────────────────▶│  Eval harness        │
│  (free)      │                    │  metrics.py (taxonomy)
└──────────────┘                    │  harness.py (labels) │
        │ filing text                └─────────▲───────────┘
        ▼                                      │ grade
┌──────────────┐  cheap→strong router  ┌───────┴───────────┐
│ AI extract   │──────────────────────▶│ InstrumentedClient │
│ extract.py   │  confidence-gated     │ cost/latency/tokens│
└──────────────┘                        └───────────────────┘
        │ structured figures
        ▼
┌──────────────┐   ┌──────────────┐   ┌────────────────────┐
│ FastAPI      │──▶│ Context flags│   │ Frontend dashboard │
│ app/main.py  │   │ signals/     │   │ docs/index.html    │
└──────────────┘   └──────────────┘   └────────────────────┘
```

| Layer | What's interesting |
|---|---|
| [`evals/metrics.py`](backend/app/evals/metrics.py) | **Failure taxonomy.** Scale error, adjacent-column, hallucination, and abstention are classified distinctly and scored in a defensible order — abstaining (0) beats hallucinating (−0.5) because a blank field is recoverable and a fabricated revenue number isn't. |
| [`evals/harness.py`](backend/app/evals/harness.py) | Builds a labeled dataset from XBRL with **zero manual annotation**. |
| [`ai/extract.py`](backend/app/ai/extract.py) | Confidence-gated **escalation router** (cheap model first, strong model only on low-confidence fields) + document-order HTML parsing (see note below). |
| [`ai/client.py`](backend/app/ai/client.py) | Every model call records **tokens, latency, and estimated cost** — you can't route on cost without measuring it. |
| [`signals/context.py`](backend/app/signals/context.py) | Transparent context flags. Each carries its raw inputs *and* a caveat naming what it doesn't tell you. No directional output anywhere. |

### A real bug worth telling in an interview

Financial filings put a units header — `(in millions)` — **above** the table it
governs. An early version of [`html_to_text`](backend/app/ai/extract.py) grouped
all tables and all paragraphs separately, which silently separated that header
from its figures. No exception, no error — just quietly worse extraction (every
number read at the wrong scale). The fix was to **traverse the HTML in strict
document order** so the header stays adjacent to its table. It wasn't prompt
engineering, and that's the point.

---

## Quick start

### Option A — the dashboard only (no backend)

Open [`docs/index.html`](docs/index.html) in a browser, or host it on GitHub
Pages. Data is inlined; nothing to install.

### Option B — the API in demo mode (no keys)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://127.0.0.1:8000/api/health  → demo_mode: true
```

### Option C — Docker (one command)

```bash
docker compose up --build
# API on http://localhost:8000, demo mode, no secrets needed
```

### Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | mode + which live sources are configured |
| GET | `/api/stocks/{ticker}/overview` | name, price, change, market cap |
| GET | `/api/stocks/{ticker}/trends` | price history + 50/200-day SMA + 52w range |
| GET | `/api/stocks/{ticker}/news` | headlines with sentiment |
| GET | `/api/stocks/{ticker}/earnings` | quarterly revenue / net income / EPS |
| GET | `/api/stocks/{ticker}/signals` | transparent context flags |

Demo mode knows `AAPL`, `MSFT`, `NVDA`.

---

## The eval harness

```bash
cd backend

# Offline sanity check — proves the taxonomy classifier end-to-end, no API key:
python -m app.evals.run_eval grade-demo

# Build labels from live EDGAR XBRL (needs a real SEC_USER_AGENT):
python -m app.evals.run_eval build --tickers AAPL,MSFT,NVDA,COST,JPM,PG

# Run the extraction pipeline over the dataset and grade it (needs ANTHROPIC_API_KEY):
python -m app.evals.run_eval sweep
```

`sweep` writes `data/sweep_results.md` with the **failure taxonomy** — *how* the
prompt fails, not just how often.

### Tests

```bash
cd backend && python -m pytest -q
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the grader
tests, the offline eval, and an API import smoke test on every push.

---

## Going live

Copy [`.env.example`](.env.example) to `backend/.env` and set `DEMO_MODE=false`.

- **SEC EDGAR** — free, no key, but **requires** `SEC_USER_AGENT` naming a real
  email or it returns 403 and blocks your IP ~10 min. Rate limit ~10 req/s.
- **Finnhub** — free tier, 60 req/min, for quotes + news.
- **Anthropic** — only needed for real extraction and the eval sweep.

Design intent: treat these as **backfill sources into your own store**, not live
per-request dependencies. A closed fiscal quarter never changes, so it should be
fetched once and cached forever.

---

## Honest disclaimers (read before putting this on a résumé)

- **The numbers in the dashboard and any benchmark table are demo fixtures**,
  not measured results. Run `build` then `sweep` against real filings and
  replace them with *your* numbers. Real numbers you can defend beat impressive
  numbers you can't — 84% you can explain beats 92% you can't.
- **Model pricing** in [`ai/client.py`](backend/app/ai/client.py) changes; verify
  it before quoting cost-per-filing anywhere.
- **This is not investment advice.** The context flags describe observable
  conditions and explicitly do not predict prices.

---

## License

MIT — see [LICENSE](LICENSE).
