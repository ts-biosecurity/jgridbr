"""
fetch_brazil_infectious disease.py
BlueDot API + Google News RSSからブラジルの感染症関連記事を取得し、
州別に分類してJSONで保存する

環境変数:
    BLUEDOT_API_KEY: BlueDot APIキー

使い方:
    python "fetch_brazil_infectious disease.py"
"""

import calendar
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
import requests
from deep_translator import GoogleTranslator
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 翻訳ヘルパー (ポルトガル語 → 英語)
# ============================================================

_translator_en = GoogleTranslator(source="pt", target="en")
_translator_ja = GoogleTranslator(source="pt", target="ja")


def _translate(text, translator):
    """テキストを翻訳する。失敗時は空文字を返す。"""
    if not text or not text.strip():
        return ""
    try:
        result = translator.translate(text)
        return result if result else ""
    except Exception as e:
        print(f"  [WARN] 翻訳失敗: {e}", file=sys.stderr)
        return ""


def translate_articles(articles):
    """記事リストの headline を英訳・日本語訳し格納する。"""
    total = len(articles)
    translated_en = 0
    translated_ja = 0
    for i, a in enumerate(articles):
        headline = a.get("headline", "")
        if not headline:
            continue

        # 英訳
        if not a.get("headlineTranslated"):
            en = _translate(headline, _translator_en)
            if en and en != headline:
                a["headlineTranslated"] = en
                translated_en += 1

        # 日本語訳
        if not a.get("headlineJa"):
            ja = _translate(headline, _translator_ja)
            if ja and ja != headline:
                a["headlineJa"] = ja
                translated_ja += 1

        # レート制限回避
        if (i + 1) % 10 == 0:
            time.sleep(1)

    print(f"[translate] EN: {translated_en}/{total} 件, JA: {translated_ja}/{total} 件")
    return articles


# ============================================================
# BlueDot API 設定
# ============================================================

BASE_URL = "https://developer.bluedot.global/daas/articles/infectious-diseases/"
BRAZIL_GEONAMES_ID = "3469034"

# ============================================================
# ブラジル州マッピング (26州 + 連邦直轄区)
# ============================================================

STATE_MAP = {
    "Acre": "Acre", "Alagoas": "Alagoas", "Amapá": "Amapá", "Amapa": "Amapá",
    "Amazonas": "Amazonas", "Bahia": "Bahia", "Ceará": "Ceará", "Ceara": "Ceará",
    "Distrito Federal": "Distrito Federal", "Espírito Santo": "Espírito Santo",
    "Espirito Santo": "Espírito Santo", "Goiás": "Goiás", "Goias": "Goiás",
    "Maranhão": "Maranhão", "Maranhao": "Maranhão", "Mato Grosso": "Mato Grosso",
    "Mato Grosso do Sul": "Mato Grosso do Sul", "Minas Gerais": "Minas Gerais",
    "Pará": "Pará", "Para": "Pará", "Paraíba": "Paraíba", "Paraiba": "Paraíba",
    "Paraná": "Paraná", "Parana": "Paraná", "Pernambuco": "Pernambuco",
    "Piauí": "Piauí", "Piaui": "Piauí", "Rio de Janeiro": "Rio de Janeiro",
    "Rio Grande do Norte": "Rio Grande do Norte", "Rio Grande do Sul": "Rio Grande do Sul",
    "Rondônia": "Rondônia", "Rondonia": "Rondônia", "Roraima": "Roraima",
    "Santa Catarina": "Santa Catarina", "São Paulo": "São Paulo", "Sao Paulo": "São Paulo",
    "Sergipe": "Sergipe", "Tocantins": "Tocantins",
}

# ブラジルの主要都市 → 州マッピング
CITY_TO_STATE = {
    "São Paulo": "São Paulo", "Sao Paulo": "São Paulo", "Guarulhos": "São Paulo",
    "Campinas": "São Paulo", "Santos": "São Paulo", "Osasco": "São Paulo",
    "Rio de Janeiro": "Rio de Janeiro", "Niterói": "Rio de Janeiro", "Niteroi": "Rio de Janeiro",
    "Brasília": "Distrito Federal", "Brasilia": "Distrito Federal",
    "Salvador": "Bahia", "Feira de Santana": "Bahia",
    "Fortaleza": "Ceará", "Juazeiro do Norte": "Ceará",
    "Belo Horizonte": "Minas Gerais", "Uberlândia": "Minas Gerais", "Uberaba": "Minas Gerais",
    "Manaus": "Amazonas",
    "Curitiba": "Paraná", "Londrina": "Paraná", "Maringá": "Paraná",
    "Recife": "Pernambuco", "Olinda": "Pernambuco", "Caruaru": "Pernambuco",
    "Porto Alegre": "Rio Grande do Sul", "Caxias do Sul": "Rio Grande do Sul",
    "Belém": "Pará", "Belem": "Pará", "Ananindeua": "Pará",
    "Goiânia": "Goiás", "Goiania": "Goiás", "Aparecida de Goiânia": "Goiás",
    "São Luís": "Maranhão", "Sao Luis": "Maranhão",
    "Maceió": "Alagoas", "Maceio": "Alagoas",
    "Natal": "Rio Grande do Norte", "Mossoró": "Rio Grande do Norte",
    "Campo Grande": "Mato Grosso do Sul", "Dourados": "Mato Grosso do Sul",
    "Teresina": "Piauí",
    "João Pessoa": "Paraíba", "Joao Pessoa": "Paraíba",
    "Cuiabá": "Mato Grosso", "Cuiaba": "Mato Grosso",
    "Aracaju": "Sergipe",
    "Florianópolis": "Santa Catarina", "Florianopolis": "Santa Catarina",
    "Joinville": "Santa Catarina", "Blumenau": "Santa Catarina",
    "Vitória": "Espírito Santo", "Vitoria": "Espírito Santo",
    "Porto Velho": "Rondônia",
    "Macapá": "Amapá", "Macapa": "Amapá",
    "Rio Branco": "Acre",
    "Boa Vista": "Roraima",
    "Palmas": "Tocantins",
    "São José dos Campos": "São Paulo", "Ribeirão Preto": "São Paulo",
    "Sorocaba": "São Paulo",
}

# ポルトガル語テキストから州を抽出するためのキーワード
STATE_KEYWORDS_PT = {
    "Acre": ["Acre", "Rio Branco"],
    "Alagoas": ["Alagoas", "Maceió", "Maceio"],
    "Amapá": ["Amapá", "Amapa", "Macapá", "Macapa"],
    "Amazonas": ["Amazonas", "Manaus"],
    "Bahia": ["Bahia", "Salvador", "Feira de Santana"],
    "Ceará": ["Ceará", "Ceara", "Fortaleza"],
    "Distrito Federal": ["Distrito Federal", "Brasília", "Brasilia", "DF"],
    "Espírito Santo": ["Espírito Santo", "Espirito Santo", "Vitória", "Vitoria"],
    "Goiás": ["Goiás", "Goias", "Goiânia", "Goiania"],
    "Maranhão": ["Maranhão", "Maranhao", "São Luís", "Sao Luis"],
    "Mato Grosso": ["Mato Grosso", "Cuiabá", "Cuiaba"],
    "Mato Grosso do Sul": ["Mato Grosso do Sul", "Campo Grande", "Dourados"],
    "Minas Gerais": ["Minas Gerais", "Belo Horizonte", "Uberlândia", "Uberaba"],
    "Pará": ["Pará", "Para", "Belém", "Belem"],
    "Paraíba": ["Paraíba", "Paraiba", "João Pessoa", "Joao Pessoa"],
    "Paraná": ["Paraná", "Parana", "Curitiba", "Londrina", "Maringá"],
    "Pernambuco": ["Pernambuco", "Recife", "Olinda", "Caruaru"],
    "Piauí": ["Piauí", "Piaui", "Teresina"],
    "Rio de Janeiro": ["Rio de Janeiro", "Niterói", "Niteroi"],
    "Rio Grande do Norte": ["Rio Grande do Norte", "Natal", "Mossoró"],
    "Rio Grande do Sul": ["Rio Grande do Sul", "Porto Alegre", "Caxias do Sul"],
    "Rondônia": ["Rondônia", "Rondonia", "Porto Velho"],
    "Roraima": ["Roraima", "Boa Vista"],
    "Santa Catarina": ["Santa Catarina", "Florianópolis", "Florianopolis", "Joinville"],
    "São Paulo": ["São Paulo", "Sao Paulo", "Campinas", "Guarulhos", "Santos"],
    "Sergipe": ["Sergipe", "Aracaju"],
    "Tocantins": ["Tocantins", "Palmas"],
}

# 州の中心座標
STATE_CENTERS = {
    "Acre": (-9.97, -67.81), "Alagoas": (-9.57, -36.78),
    "Amapá": (1.41, -51.77), "Amazonas": (-3.07, -61.66),
    "Bahia": (-12.97, -38.51), "Ceará": (-3.72, -38.53),
    "Distrito Federal": (-15.78, -47.93), "Espírito Santo": (-20.32, -40.34),
    "Goiás": (-16.64, -49.31), "Maranhão": (-2.53, -44.28),
    "Mato Grosso": (-15.60, -56.10), "Mato Grosso do Sul": (-20.44, -54.65),
    "Minas Gerais": (-19.92, -43.94), "Pará": (-1.46, -48.50),
    "Paraíba": (-7.12, -34.86), "Paraná": (-25.43, -49.27),
    "Pernambuco": (-8.05, -34.87), "Piauí": (-5.09, -42.80),
    "Rio de Janeiro": (-22.91, -43.17), "Rio Grande do Norte": (-5.79, -35.21),
    "Rio Grande do Sul": (-30.03, -51.23), "Rondônia": (-8.76, -63.90),
    "Roraima": (2.82, -60.67), "Santa Catarina": (-27.59, -48.55),
    "São Paulo": (-23.55, -46.63), "Sergipe": (-10.91, -37.07),
    "Tocantins": (-10.18, -48.33),
}

# 主要な感染症キーワード（ポルトガル語・英語）
DISEASE_KEYWORDS = {
    "Dengue": ["dengue", "dengue fever"],
    "Zika": ["zika", "zika vírus", "zika virus"],
    "Chikungunya": ["chikungunya"],
    "Malaria": ["malária", "malaria"],
    "Yellow Fever": ["febre amarela", "yellow fever"],
    "Measles": ["sarampo", "measles"],
    "COVID-19": ["covid", "covid-19", "coronavírus", "coronavirus", "sars-cov-2"],
    "Influenza": ["influenza", "gripe", "h1n1", "h3n2"],
    "Tuberculosis": ["tuberculose", "tuberculosis"],
    "Hepatitis": ["hepatite", "hepatitis"],
    "Leptospirosis": ["leptospirose", "leptospirosis"],
    "Leishmaniasis": ["leishmaniose", "leishmaniasis"],
    "Chagas": ["chagas", "doença de chagas"],
    "Meningitis": ["meningite", "meningitis"],
    "Rabies": ["raiva", "rabies"],
    "Oropouche": ["oropouche"],
    "Mpox": ["mpox", "varíola dos macacos", "variola dos macacos", "monkeypox"],
    "Cholera": ["cólera", "colera", "cholera"],
    "Whooping Cough": ["coqueluche", "pertussis", "whooping cough"],
    "Typhoid": ["febre tifoide", "typhoid"],
    "HIV/AIDS": ["hiv", "aids"],
    "Syphilis": ["sífilis", "sifilis", "syphilis"],
    "Ebola": ["ebola"],
    "Marburg": ["marburg"],
    "Avian Influenza": ["gripe aviária", "gripe aviaria", "avian influenza", "bird flu", "h5n1"],
}


def _find_nearest_state(lat, lon):
    """座標から最も近い州を返す"""
    min_dist = float("inf")
    nearest = None
    for state, (slat, slon) in STATE_CENTERS.items():
        dist = (lat - slat) ** 2 + (lon - slon) ** 2
        if dist < min_dist:
            min_dist = dist
            nearest = state
    return nearest


def classify_state(locations):
    """記事のlocationsから州を特定する"""
    states = set()

    for loc in locations:
        name = loc.get("name", "")
        matched = False

        # 1. 州名の直接マッチ
        if name in STATE_MAP:
            states.add(STATE_MAP[name])
            matched = True

        # 2. 都市名マッチ
        if not matched and name in CITY_TO_STATE:
            states.add(CITY_TO_STATE[name])
            matched = True

        # 3. 部分文字列マッチ
        if not matched:
            name_lower = name.lower()
            for key, val in STATE_MAP.items():
                if key.lower() in name_lower:
                    states.add(val)
                    matched = True
                    break
            if not matched:
                for city, state in CITY_TO_STATE.items():
                    if city.lower() in name_lower:
                        states.add(state)
                        matched = True
                        break

        # 4. 座標ベースマッチ（ブラジル国内の場合のみ）
        if not matched:
            lat = loc.get("coordinate_lat")
            lon = loc.get("coordinate_lon")
            if lat is not None and lon is not None:
                if -34.0 <= lat <= 6.0 and -74.0 <= lon <= -35.0:
                    nearest = _find_nearest_state(lat, lon)
                    if nearest:
                        states.add(nearest)

    if not states:
        states.add("Brasil (estado não identificado)")

    return list(states)


def classify_state_from_text(text):
    """テキストから州を特定する"""
    states = set()
    text_check = text
    for state, keywords in STATE_KEYWORDS_PT.items():
        for kw in keywords:
            if kw.lower() in text_check.lower():
                states.add(state)
                break
    if not states:
        states.add("Brasil (estado não identificado)")
    return list(states)


def classify_diseases_from_text(text):
    """テキストから感染症を特定する"""
    diseases = set()
    text_lower = text.lower()
    for disease, keywords in DISEASE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                diseases.add(disease)
                break
    if not diseases:
        diseases.add("Doença infecciosa (não especificada)")
    return list(diseases)


# ============================================================
# Google News RSS 収集
# ============================================================

GNEWS_RSS_BASE = "https://news.google.com/rss/search"
GNEWS_QUERIES = [
    "doença infecciosa Brasil",
    "dengue Brasil",
    "surto epidemia Brasil",
    "infectious disease Brazil",
    "febre amarela OR chikungunya OR zika Brasil",
    "sarampo OR meningite OR leptospirose Brasil",
    "gripe aviária OR oropouche OR mpox Brasil",
    "covid OR influenza OR gripe Brasil surto",
]
GNEWS_PARAMS_PT = {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
GNEWS_PARAMS_EN = {"hl": "en", "gl": "BR", "ceid": "BR:en"}
GNEWS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_google_news(hours=48):
    """Google News RSSからブラジルの感染症関連ニュースを収集する"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen_ids = set()
    articles = []

    query_param_pairs = []
    for query in GNEWS_QUERIES:
        # ポルトガル語クエリはpt-BRパラメータ、英語クエリはenパラメータ
        if any(w in query for w in ["infectious", "disease", "Brazil"]):
            query_param_pairs.append((query, GNEWS_PARAMS_EN))
        else:
            query_param_pairs.append((query, GNEWS_PARAMS_PT))

    for query, params in query_param_pairs:
        encoded = quote(query)
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{GNEWS_RSS_BASE}?q={encoded}&{param_str}"
        print(f"[gnews] query='{query}'")

        req = urllib.request.Request(url, headers={"User-Agent": GNEWS_USER_AGENT})
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = resp.read()
            feed = feedparser.parse(data)
        except Exception as e:
            print(f"  [WARN] フィード取得失敗: {e}", file=sys.stderr)
            continue

        print(f"  取得件数: {len(feed.entries)}")

        for entry in feed.entries:
            raw_id = f"{entry.get('title', '')}{entry.get('link', '')}"
            article_id = "gnews_" + hashlib.sha256(raw_id.encode()).hexdigest()[:16]

            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)

            pub_dt = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                ts = calendar.timegm(entry.published_parsed)
                pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            if pub_dt and pub_dt < cutoff:
                continue

            source_name = ""
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source_name = entry.source.title

            title = entry.get("title", "")
            states = classify_state_from_text(title)
            diseases = classify_diseases_from_text(title)

            articles.append({
                "articleId": article_id,
                "headline": title,
                "headlineTranslated": "",
                "summary": "",
                "summaryOriginal": "",
                "publishedTimestamp": pub_dt.isoformat() if pub_dt else "",
                "sourceUrl": entry.get("link", ""),
                "originalLanguage": "PORTUGUESE",
                "diseases": diseases,
                "locations": [],
                "states": states,
                "dataSource": "Google News",
                "sourceName": source_name,
            })

        time.sleep(2)

    articles.sort(key=lambda x: x.get("publishedTimestamp", ""), reverse=True)
    print(f"[gnews] 合計: {len(articles)}件")
    return articles


def is_infectious_disease_article(article):
    """記事が感染症関連かどうかを判定"""
    diseases = article.get("diseases", []) or []
    if diseases:
        return True

    headline = (article.get("articleHeadlineTranslated") or article.get("articleHeadline") or "").lower()
    summary = (article.get("articleSummary") or "").lower()
    text = headline + " " + summary

    for disease, keywords in DISEASE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return True

    # 一般的な感染症関連用語
    general_terms = [
        "outbreak", "epidemic", "pandemic", "surto", "epidemia", "pandemia",
        "infectious", "infecciosa", "contagious", "contagiosa",
        "cases reported", "casos confirmados", "casos notificados",
        "alerta epidemiológico", "vigilância epidemiológica",
    ]
    return any(term in text for term in general_terms)


def build_params():
    """過去48時間のAPIパラメータを構築"""
    now = datetime.now(timezone.utc)
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(hours=48)).strftime("%Y-%m-%d")
    return {
        "startDate": start_date,
        "endDate": end_date,
        "locationIds": BRAZIL_GEONAMES_ID,
        "includeBody": "true",
        "includeDuplicates": "false",
        "excludeArticlesWithoutEvents": "false",
        "limit": 1000,
        "format": "json",
        "api-version": "v1",
    }


def fetch_articles(api_key):
    """BlueDot APIから記事を取得"""
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Accept": "application/json",
    }

    params = build_params()
    print(f"[fetch] 期間: {params['startDate']} 〜 {params['endDate']}")

    response = requests.get(BASE_URL, params=params, headers=headers, timeout=60)
    response.raise_for_status()

    raw = response.json()
    if isinstance(raw, dict):
        raw = raw.get("data", raw.get("articles", []))

    print(f"[fetch] ブラジルの全記事数: {len(raw)}")

    # 48時間以内にフィルタ
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = []
    for a in raw:
        ts = a.get("publishedTimestamp", "")
        if ts:
            try:
                pub_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if pub_dt >= cutoff:
                    recent.append(a)
                    continue
            except (ValueError, TypeError):
                pass
        recent.append(a)

    print(f"[fetch] 48時間以内の記事数: {len(recent)}")

    infectious = [a for a in recent if is_infectious_disease_article(a)]
    print(f"[fetch] 感染症関連記事数: {len(infectious)}")

    return infectious


def process_articles(articles):
    """記事を州別に分類し、日付降順でソート"""
    processed = []

    for article in articles:
        locations = article.get("locations", []) or []
        states = classify_state(locations)

        headline = article.get("articleHeadline", "") or article.get("articleHeadlineTranslated", "")
        summary = article.get("articleSummaryTranslated", article.get("articleSummary", ""))
        diseases_raw = article.get("diseases", []) or []
        diseases = [
            d.get("name", str(d)) if isinstance(d, dict) else str(d)
            for d in diseases_raw
        ]
        if not diseases:
            diseases = classify_diseases_from_text(headline + " " + summary)

        processed.append({
            "articleId": article.get("articleId", article.get("id", "unknown")),
            "headline": headline,
            "headlineTranslated": article.get("articleHeadlineTranslated", ""),
            "summary": summary,
            "summaryOriginal": article.get("articleSummary", ""),
            "publishedTimestamp": article.get("publishedTimestamp", ""),
            "sourceUrl": article.get("sourceUrl", ""),
            "originalLanguage": article.get("originalLanguage", ""),
            "diseases": diseases,
            "locations": [
                {"name": loc.get("name", ""), "lat": loc.get("coordinate_lat"), "lon": loc.get("coordinate_lon")}
                for loc in locations
            ],
            "states": states,
            "dataSource": "BlueDot",
            "sourceName": "",
        })

    processed.sort(key=lambda x: x.get("publishedTimestamp", ""), reverse=True)
    return processed


def merge_and_deduplicate(bluedot_articles, gnews_articles):
    """BlueDotとGoogle Newsの記事を統合し、重複を排除する"""
    merged = list(bluedot_articles)
    existing_urls = {a.get("sourceUrl", "") for a in merged if a.get("sourceUrl")}

    added = 0
    for article in gnews_articles:
        url = article.get("sourceUrl", "")
        is_dup = False
        for existing_url in existing_urls:
            if existing_url and url and (
                existing_url in url or url in existing_url
            ):
                is_dup = True
                break
        if not is_dup:
            merged.append(article)
            existing_urls.add(url)
            added += 1

    merged.sort(key=lambda x: x.get("publishedTimestamp", ""), reverse=True)
    print(f"[merge] BlueDot: {len(bluedot_articles)}件 + Google News: {added}件 (重複除外) = 合計: {len(merged)}件")
    return merged


def save_results(articles, output_path):
    """結果をJSONに保存"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    state_summary = {}
    disease_summary = {}
    for a in articles:
        for s in a.get("states", []):
            state_summary[s] = state_summary.get(s, 0) + 1
        for d in a.get("diseases", []):
            disease_summary[d] = disease_summary.get(d, 0) + 1

    now = datetime.now(timezone.utc)
    output = {
        "generated_at": now.isoformat(),
        "date_range": {
            "start": (now - timedelta(hours=48)).isoformat(),
            "end": now.isoformat(),
        },
        "total_articles": len(articles),
        "state_summary": state_summary,
        "disease_summary": disease_summary,
        "articles": articles,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[save] {output_path} に保存しました")
    print(f"[save] 州別内訳:")
    for state, count in sorted(state_summary.items(), key=lambda x: -x[1]):
        print(f"  {state}: {count}件")
    print(f"[save] 感染症別内訳:")
    for disease, count in sorted(disease_summary.items(), key=lambda x: -x[1]):
        print(f"  {disease}: {count}件")


def main():
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "data", "brazil_infectious_diseases.json")

    # 1. BlueDot API からの取得
    bluedot_articles = []
    api_key = os.environ.get("BLUEDOT_API_KEY")
    if api_key:
        print("=" * 50)
        print("[BlueDot API]")
        print("=" * 50)
        articles = fetch_articles(api_key)
        bluedot_articles = process_articles(articles)
    else:
        print("[SKIP] BLUEDOT_API_KEY 未設定 → BlueDot APIをスキップ")

    # 2. Google News RSS からの取得
    print("\n" + "=" * 50)
    print("[Google News RSS]")
    print("=" * 50)
    gnews_articles = fetch_google_news(hours=48)

    # 3. 統合・重複排除
    print("\n" + "=" * 50)
    print("[統合]")
    print("=" * 50)
    all_articles = merge_and_deduplicate(bluedot_articles, gnews_articles)

    # 4. 見出しの英訳
    print("\n" + "=" * 50)
    print("[翻訳 PT→EN]")
    print("=" * 50)
    all_articles = translate_articles(all_articles)

    # 5. 保存
    save_results(all_articles, output_path)

    print(f"\n[完了] ダッシュボードを表示するには:")
    print(f"  cd docs && python -m http.server 8000")
    print(f"  ブラウザで http://localhost:8000 を開いてください")


if __name__ == "__main__":
    main()
