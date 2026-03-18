# jgridbr - Brazil Infectious Disease Dashboard

Real-time monitoring dashboard for infectious disease news in Brazil, aggregating articles from multiple sources and mapping them by state.

## Features

- **Multi-source aggregation**: BlueDot API + Google News RSS
- **48-hour window**: Fetches only recent articles within the last 48 hours
- **State-level mapping**: Classifies articles to Brazil's 26 states + Distrito Federal using location names, city lookups, and coordinate matching
- **25+ diseases tracked**: Dengue, Zika, Chikungunya, Measles, COVID-19, Influenza, Yellow Fever, Malaria, Avian Influenza, Mpox, and more
- **Auto-translation**: Headlines translated from Portuguese to English and Japanese via Google Translate
- **Interactive dashboard**:
  - Leaflet heatmap with official GeoJSON state boundaries
  - Tri-lingual UI (PT / EN / JA) with persistent language preference
  - Disease, state, and keyword filters
  - Resizable split-pane layout

## Setup

### Requirements

```bash
pip install requests feedparser python-dotenv deep-translator
```

### Environment Variables (optional)

```
BLUEDOT_API_KEY=your_api_key_here
```

If not set, the script skips BlueDot API and uses Google News RSS only.

## Usage

### 1. Fetch data

```bash
python "fetch_brazil_infectious disease.py"
```

This will:
- Fetch articles from Google News RSS (8 queries in PT/EN)
- Fetch from BlueDot API (if API key is configured)
- Classify articles by Brazilian state
- Detect disease types from article content
- Translate headlines to English and Japanese
- Save results to `docs/data/brazil_infectious_diseases.json`

### 2. View dashboard

```bash
cd docs && python -m http.server 8000
```

Open http://localhost:8000 in your browser.

## Project Structure

```
├── fetch_brazil_infectious disease.py   # Data fetching & processing script
├── docs/
│   ├── index.html                       # Dashboard (single-file, no build step)
│   └── data/
│       └── brazil_infectious_diseases.json  # Generated data (gitignored)
├── .gitignore
└── README.md
```

## Data Flow

```
Google News RSS ─┐
                 ├─→ Merge & Deduplicate ─→ Translate (PT→EN, JA) ─→ JSON ─→ Dashboard
BlueDot API ─────┘
```

## License

MIT
