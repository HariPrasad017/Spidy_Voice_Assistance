"""
S.P.I.D.Y v6.1 — Tool Registry
Source-aware web search, weather, and system tools.
All tool inputs are validated; no arbitrary shell execution is permitted.

Web search strategy (no API keys required):
  1. Google News RSS  — real current articles for news/current-events queries
  2. DuckDuckGo HTML  — real web results for factual/person/company queries
  3. Wikipedia REST   — encyclopaedic summary for stable knowledge
  4. Wikipedia Search — additional context fallback
"""

import sys
import os
import re
import requests
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTES_FILE, REMINDERS_FILE, GROQ_MODEL, GROQ_API_KEY, logger
from commands import take_screenshot, control_volume, open_app, load_json, save_json

# Common browser-like headers to avoid bot blocks
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}
_WIKI_HEADERS = {'User-Agent': 'SpidyAssistant/6.1 (educational; https://github.com/spidy)'}


# ─── Freshness classification ────────────────────────────────────────────────────

_NEWS_TRIGGERS = {
    'news', 'latest', 'recent', 'breaking', 'today', 'update', 'announce',
    'release', 'new model', 'just', 'this week', 'this month',
}
_CURRENT_PERSON_TRIGGERS = {
    'current', 'who is', 'present', 'incumbent', 'ceo', 'pm', 'cm',
    'prime minister', 'chief minister', 'president', 'governor',
    'secretary', 'head of', 'leader',
}
_FINANCE_TRIGGERS = {
    'gold price', 'silver price', 'gold rate', 'silver rate', 'market rate',
    'market price', 'per gram', 'share price', 'stock rate', 'stock price',
    'revenue of', 'current revenue', 'winner of', 'who won', 'price of gold',
    'price of silver', 'rate of gold', 'rate of silver', 'crypto price',
    'bitcoin price'
}

def _classify_query(query: str) -> str:
    """Return 'finance', 'news', 'current_person', or 'stable'."""
    q = query.lower()
    if any(t in q for t in _FINANCE_TRIGGERS):
        return 'finance'
    if any(w in q for w in ['price', 'rate', 'revenue', 'winner']) and any(w in q for w in ['current', 'latest', 'today', 'now', 'per gram', 'in india']):
        return 'finance'
    if any(t in q for t in _NEWS_TRIGGERS):
        return 'news'
    if any(t in q for t in _CURRENT_PERSON_TRIGGERS):
        return 'current_person'
    return 'stable'



# ─── Provider 1: Google News RSS (live articles with real URLs) ──────────────────

def search_google_news_rss(query: str, max_results: int = 5) -> dict:
    """
    Fetch current news articles via Google News RSS.
    Returns real article URLs, publication dates, and source names.
    No authentication required.
    """
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        # Parse RSS items — avoid dependency on xml libs
        items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
        if not items:
            return {"text": "", "sources": []}

        sources = []
        snippets = []
        for item in items[:max_results]:
            title_m = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item)
            if not title_m:
                title_m = re.search(r'<title>(.*?)</title>', item)
            link_m  = re.search(r'<link>(https?://[^\s<]+)', item)
            if not link_m:
                # Some RSS feeds put the link after </link> with CDATA
                link_m = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
            pub_m   = re.search(r'<pubDate>(.*?)</pubDate>', item)
            src_m   = re.search(r'<source[^>]*>(.*?)</source>', item)
            desc_m  = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item, re.DOTALL)
            if not desc_m:
                desc_m = re.search(r'<description>(.*?)</description>', item, re.DOTALL)

            if not title_m:
                continue

            title   = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            link    = link_m.group(1).strip() if link_m else ''
            pub     = pub_m.group(1).strip() if pub_m else ''
            src     = re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+>', '', src_m.group(1)).strip() if src_m else 'Google News'
            desc    = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()[:150] if desc_m else ''

            # Skip Google News redirect URLs — only keep direct article links
            if 'news.google.com' in link:
                # Can't resolve the redirect without following it; keep with note
                link_display = link
            else:
                link_display = link

            if title:
                snippets.append(f"• **{title}** ({src}, {pub[:16]})\n  {desc}")
                sources.append({
                    "title": title,
                    "url": link_display,
                    "source": src,
                    "published": pub,
                })

        if not sources:
            return {"text": "", "sources": []}

        return {
            "text": f"Latest news results:\n" + "\n".join(snippets),
            "sources": sources,
            "retrieved_at": datetime.now().isoformat(),
            "provider": "Google News RSS"
        }
    except Exception as e:
        return {"text": "", "sources": [], "error": str(e)}


# ─── Provider 2: DuckDuckGo HTML (real web results for factual queries) ──────────

def search_duckduckgo_html(query: str, max_results: int = 5) -> dict:
    """
    Scrape DuckDuckGo HTML results page for real web result titles, URLs, snippets.
    No API key required. Returns actual result URLs (not DDG redirect links).
    """
    encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=us-en"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()

        # Extract result blocks
        # DDG HTML structure: <div class="result results_links...">
        #   <a class="result__a" href="...">Title</a>
        #   <a class="result__snippet">snippet</a>
        result_blocks = re.findall(
            r'<div class="result[^"]*".*?</div>\s*</div>',
            resp.text, re.DOTALL
        )

        # Fallback: extract titles + URL redirects + snippets separately
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', resp.text)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        # DDG encodes actual URLs in uddg= query param
        raw_uddg = re.findall(r'uddg=([^&">\s]+)', resp.text)
        decoded_urls = [urllib.parse.unquote(u) for u in raw_uddg]

        titles_clean   = [re.sub(r'<[^>]+>', '', t).strip() for t in titles]
        snippets_clean = [re.sub(r'<[^>]+>', '', s).strip()[:200] for s in snippets]

        # Deduplicate URLs while preserving order
        seen = set()
        sources = []
        snippets_out = []
        for i, (t, u) in enumerate(zip(titles_clean, decoded_urls)):
            if not t or not u:
                continue
            if u in seen:
                continue
            seen.add(u)
            # Infer domain as source name
            try:
                domain = urllib.parse.urlparse(u).netloc.replace('www.', '')
            except Exception:
                domain = 'Web'
            snip = snippets_clean[i] if i < len(snippets_clean) else ''
            sources.append({"title": t, "url": u, "source": domain})
            snippets_out.append(f"• **{t}** ({domain})\n  {snip}")
            if len(sources) >= max_results:
                break

        if not sources:
            return {"text": "", "sources": []}

        return {
            "text": "Web search results:\n" + "\n".join(snippets_out),
            "sources": sources,
            "retrieved_at": datetime.now().isoformat(),
            "provider": "DuckDuckGo"
        }
    except Exception as e:
        return {"text": "", "sources": [], "error": str(e)}


# ─── Provider 3: Wikipedia REST Summary (authoritative stable knowledge) ─────────

def search_wikipedia_summary(title_query: str) -> dict:
    """
    Wikipedia REST API page summary — returns a clean extract and canonical URL.
    Best for stable encyclopaedic knowledge (not current officeholders).
    """
    encoded = urllib.parse.quote(title_query.replace(' ', '_'))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        resp = requests.get(url, headers=_WIKI_HEADERS, timeout=8)
        if resp.status_code == 404:
            return {"text": "", "sources": []}
        resp.raise_for_status()
        data = resp.json()
        extract = data.get('extract', '').strip()
        if not extract:
            return {"text": "", "sources": []}
        page_url = data.get('content_urls', {}).get('desktop', {}).get('page', '')
        title    = data.get('title', title_query)
        return {
            "text": f"**{title}** (Wikipedia)\n{extract[:600]}",
            "sources": [{"title": title, "url": page_url, "source": "Wikipedia"}],
            "retrieved_at": datetime.now().isoformat(),
            "provider": "Wikipedia REST"
        }
    except Exception as e:
        return {"text": "", "sources": [], "error": str(e)}


# ─── Provider 4: Wikipedia Search (multi-result fallback) ────────────────────────

def _clean_wiki_snippet(raw: str) -> str:
    return (raw.replace('<span class="searchmatch">', '')
               .replace('</span>', '')
               .replace('&quot;', '"')
               .replace('&#039;', "'")
               .replace('&amp;', '&')
               .replace('&lt;', '<')
               .replace('&gt;', '>'))


def search_wikipedia(query: str) -> dict:
    """Search Wikipedia and return structured results with sources."""
    url = (f"https://en.wikipedia.org/w/api.php?action=query&list=search"
           f"&srsearch={urllib.parse.quote(query)}&utf8=&format=json&srlimit=3")
    try:
        resp = requests.get(url, headers=_WIKI_HEADERS, timeout=7)
        resp.raise_for_status()
        data  = resp.json()
        results = data.get('query', {}).get('search', [])
        if not results:
            return {"text": f"No Wikipedia results found for: {query}", "sources": []}

        sources  = []
        snippets = []
        for r in results:
            clean    = _clean_wiki_snippet(r['snippet'])
            title    = r['title']
            wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            snippets.append(f"• **{title}**: {clean}...")
            sources.append({"title": title, "url": wiki_url, "source": "Wikipedia"})

        return {
            "text": "Wikipedia Search Results:\n" + "\n".join(snippets),
            "sources": sources,
            "retrieved_at": datetime.now().isoformat(),
            "provider": "Wikipedia Search"
        }
    except Exception as e:
        return {"text": f"Wikipedia search failed: {e}", "sources": []}


# ─── Deprecated compatibility stub ───────────────────────────────────────────────

def search_duckduckgo_instant(query: str) -> dict:
    """
    DEPRECATED: DDG Instant Answer API — left for backward compatibility only.
    Returns empty for current-person queries. Use search_duckduckgo_html instead.
    """
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=7)
        resp.raise_for_status()
        data = resp.json()
        abstract     = data.get('AbstractText', '').strip()
        abstract_url = data.get('AbstractURL', '')
        abstract_src = data.get('AbstractSource', 'DuckDuckGo')
        answer       = data.get('Answer', '').strip()
        if answer:
            return {
                "text": f"Answer: {answer}",
                "sources": [{"title": abstract_src, "url": abstract_url or "https://duckduckgo.com", "source": "DuckDuckGo"}],
                "retrieved_at": datetime.now().isoformat()
            }
        if abstract:
            return {
                "text": abstract,
                "sources": [{"title": abstract_src, "url": abstract_url or "https://duckduckgo.com", "source": abstract_src}],
                "retrieved_at": datetime.now().isoformat()
            }
    except Exception:
        pass
    return {"text": "", "sources": []}


# ─── Main web_search dispatcher ──────────────────────────────────────────────────

def web_search(query: str, prefer_current: bool = False) -> dict:
    """
    Source-aware web search with live retrieval for freshness-triggered queries.

    Strategy:
      - 'news' queries       → Google News RSS (live articles) + DDG HTML fallback
      - 'current_person'     → DDG HTML (real web results) + Google News RSS + Wikipedia summary
      - 'stable' knowledge   → Wikipedia REST summary + Wikipedia search
      - All paths            → truthful failure if no retrieval succeeds

    Returns:
      { 'text': str, 'sources': list[{title, url, source}], 'retrieved_at': str }
    Sources are ONLY from actual retrieval — never fabricated.
    """
    if not query or not query.strip():
        return {"text": "No search query provided.", "sources": []}

    q_type = _classify_query(query)

    # ── Financial / live rate queries: DDG HTML primary (never Wikipedia) ──────
    if q_type == 'finance':
        combined_sources = []
        combined_text_parts = []

        try:
            ddg = search_duckduckgo_html(query, max_results=4)
            if ddg.get("text") and ddg.get("sources"):
                combined_text_parts.append(ddg["text"])
                combined_sources.extend(ddg["sources"])
        except Exception:
            pass

        try:
            rss = search_google_news_rss(query, max_results=3)
            if rss.get("sources"):
                seen_urls = {s['url'] for s in combined_sources}
                extra = [s for s in rss["sources"] if s['url'] not in seen_urls]
                if extra:
                    combined_text_parts.append("Recent news:\n" + rss["text"])
                    combined_sources.extend(extra[:2])
        except Exception:
            pass

        if combined_sources:
            return {
                "text": "\n\n".join(combined_text_parts),
                "sources": combined_sources,
                "retrieved_at": datetime.now().isoformat(),
                "provider": "DuckDuckGo + Google News RSS"
            }

        # Truthful failure — never fabricate financial prices or fall back to Wikipedia
        return {
            "text": (
                f"Live market rate could not be retrieved for: '{query}'. "
                "Verified real-time financial sources are currently unreachable or rate-limited. "
                "I will not fabricate prices or quotes."
            ),
            "sources": []
        }

    # ── News queries: Google News RSS primary ────────────────────────────────────
    if q_type == 'news':
        try:
            rss = search_google_news_rss(query)
            if rss.get("text") and rss.get("sources"):
                # Also try DDG HTML for additional web context
                try:
                    ddg = search_duckduckgo_html(query, max_results=3)
                    if ddg.get("sources"):
                        # Prepend news, append web sources (deduplicated)
                        seen_urls = {s['url'] for s in rss['sources']}
                        extra = [s for s in ddg['sources'] if s['url'] not in seen_urls]
                        return {
                            "text": rss["text"] + (
                                "\n\nRelated web results:\n" + ddg["text"] if ddg.get("text") else ""
                            ),
                            "sources": rss["sources"] + extra[:2],
                            "retrieved_at": datetime.now().isoformat(),
                            "provider": "Google News RSS + DuckDuckGo"
                        }
                except Exception:
                    pass
                return rss
        except Exception:
            pass
        # Fallback to DDG HTML
        try:
            ddg = search_duckduckgo_html(query)
            if ddg.get("text") and ddg.get("sources"):
                return ddg
        except Exception:
            pass
        # Last resort: Wikipedia
        try:
            return search_wikipedia(query)
        except Exception as e:
            return {"text": f"Live search failed — could not retrieve current information for: {query}", "sources": []}

    # ── Current-person / office-holder queries: DDG HTML primary ────────────────
    if q_type == 'current_person':
        combined_sources = []
        combined_text_parts = []

        # DDG HTML for real web results
        try:
            ddg = search_duckduckgo_html(query, max_results=4)
            if ddg.get("text") and ddg.get("sources"):
                combined_text_parts.append(ddg["text"])
                combined_sources.extend(ddg["sources"])
        except Exception:
            pass

        # Google News RSS for current context
        try:
            rss = search_google_news_rss(query, max_results=3)
            if rss.get("sources"):
                seen_urls = {s['url'] for s in combined_sources}
                extra_sources = [s for s in rss["sources"] if s['url'] not in seen_urls]
                if extra_sources:
                    combined_text_parts.append("Recent news:\n" + rss["text"])
                    combined_sources.extend(extra_sources[:2])
        except Exception:
            pass

        # Wikipedia REST summary for authoritative context
        try:
            wiki_rest = search_wikipedia_summary(query)
            if wiki_rest.get("text") and wiki_rest.get("sources"):
                seen_urls = {s['url'] for s in combined_sources}
                extra_sources = [s for s in wiki_rest["sources"] if s['url'] not in seen_urls]
                if extra_sources:
                    combined_text_parts.append("Reference:\n" + wiki_rest["text"])
                    combined_sources.extend(extra_sources)
        except Exception:
            pass

        if combined_sources:
            return {
                "text": "\n\n".join(combined_text_parts),
                "sources": combined_sources,
                "retrieved_at": datetime.now().isoformat(),
                "provider": "DuckDuckGo + Google News RSS + Wikipedia"
            }

        # Hard failure — truthful
        return {
            "text": (
                f"Live web search could not retrieve current information for: '{query}'. "
                "I will not fabricate facts or sources. Please check a search engine directly."
            ),
            "sources": []
        }

    # ── Stable knowledge queries: Wikipedia primary ──────────────────────────────
    # Try REST summary first (clean single article)
    try:
        wiki_rest = search_wikipedia_summary(query)
        if wiki_rest.get("text") and wiki_rest.get("sources"):
            # Also get multi-result search for breadth
            try:
                wiki_search = search_wikipedia(query)
                if wiki_search.get("sources"):
                    seen_urls = {s['url'] for s in wiki_rest["sources"]}
                    extra = [s for s in wiki_search["sources"] if s['url'] not in seen_urls]
                    return {
                        "text": wiki_rest["text"] + "\n\nRelated articles:\n" + wiki_search["text"],
                        "sources": wiki_rest["sources"] + extra[:2],
                        "retrieved_at": datetime.now().isoformat(),
                        "provider": "Wikipedia"
                    }
            except Exception:
                pass
            return wiki_rest
    except Exception:
        pass

    # Fallback: Wikipedia search
    try:
        return search_wikipedia(query)
    except Exception as e:
        return {
            "text": f"Search failed — could not retrieve information for: '{query}'. Error: {e}",
            "sources": []
        }


def get_weather(city: str = 'Chennai') -> dict:
    """Fetch current weather from wttr.in."""
    if not city or not city.strip():
        city = 'Chennai'
    try:
        r = requests.get(f'https://wttr.in/{urllib.parse.quote(city)}?format=j1', timeout=7)
        r.raise_for_status()
        data = r.json()
        curr = data['current_condition'][0]
        desc = curr['weatherDesc'][0]['value']
        text = (f"Weather in {city}: {curr['temp_C']}°C ({curr['temp_F']}°F), "
                f"{desc}. Feels like {curr['FeelsLikeC']}°C. "
                f"Humidity: {curr['humidity']}%. Wind: {curr['windspeedKmph']} km/h.")
        return {
            "text": text,
            "sources": [{"title": f"Weather for {city}", "url": f"https://wttr.in/{city}", "source": "wttr.in"}],
            "retrieved_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {"text": f"Failed to get weather for {city}: {e}", "sources": []}


# ─── Tool Wrappers ───────────────────────────────────────────────────────────────

# Shared mutable dict for last tool metadata (cleared per request in router)
_last_tool_result: dict = {"sources": [], "retrieved_at": ""}


def get_last_sources() -> list:
    """Return sources from the most recent tool call."""
    return _last_tool_result.get('sources', [])


def clear_last_sources():
    _last_tool_result['sources'] = []
    _last_tool_result['retrieved_at'] = ''


def _web_search(args: dict) -> str:
    result = web_search(args.get('query', ''), prefer_current=args.get('prefer_current', False))
    _last_tool_result['sources'] = result.get('sources', [])
    _last_tool_result['retrieved_at'] = result.get('retrieved_at', '')
    return result.get('text', 'No results found.')


def _get_weather(args: dict) -> str:
    result = get_weather(args.get('city', 'Chennai'))
    _last_tool_result['sources'] = result.get('sources', [])
    _last_tool_result['retrieved_at'] = result.get('retrieved_at', '')
    return result.get('text', 'Weather unavailable.')


def _open_application(args: dict) -> str:
    app_name = args.get('app_name', '').strip()
    if not app_name:
        return "No application name provided."
    return open_app(app_name)


def _control_volume(args: dict) -> str:
    action = args.get('action', 'up').lower().strip()
    allowed_actions = {'up', 'down', 'mute', 'unmute'}
    if action not in allowed_actions:
        return f"Unknown volume action '{action}'. Use: up, down, mute, or unmute."
    return control_volume(action)


def _take_screenshot(args: dict) -> str:
    return take_screenshot()


def _save_note(args: dict) -> str:
    text = args.get('text', '') or args.get('content', '')
    text = str(text).strip()
    if not text:
        return "Failed to save note: text is empty."
    try:
        notes = load_json(NOTES_FILE)
        notes.append({'text': text, 'time': datetime.now().isoformat()})
        save_json(NOTES_FILE, notes)
        return f"Note saved successfully: '{text[:80]}{'...' if len(text) > 80 else ''}'"
    except Exception as e:
        return f"Failed to save note: {e}"


def _get_notes(args: dict = None) -> str:
    try:
        notes = load_json(NOTES_FILE)
        if not notes:
            return "No notes found."
        recent = notes[-5:]
        lines = [f"{i+1}. {n['text']}" for i, n in enumerate(recent)]
        return f"Found {len(notes)} notes. Recent notes:\n" + "\n".join(lines)
    except Exception as e:
        return f"Failed to retrieve notes: {e}"


def _set_reminder(args: dict) -> str:
    text = args.get('text', '') or args.get('description', '') or "General Reminder"
    time_str = args.get('time', '') or args.get('time_str', '')
    try:
        reminders = load_json(REMINDERS_FILE)
        reminders.append({
            'text': str(text).strip(),
            'time': str(time_str).strip() or datetime.now().strftime('%Y-%m-%d %H:%M'),
            'fired': False
        })
        save_json(REMINDERS_FILE, reminders)
        return f"Reminder set: '{text}' at {time_str or 'specified time'}."
    except Exception as e:
        return f"Failed to set reminder: {e}"


def _summarize(args: dict) -> str:
    text = args.get('text', '') or args.get('content', '') or args.get('input', '')
    text = str(text).strip()
    if not text:
        return "Failed to summarize: input text is empty."

    focus = args.get('focus', '') or "important points and key takeaways"

    # If Groq is available and circuit is closed, generate a clean structured summary
    from config import groq_circuit_breaker
    is_blocked, _ = groq_circuit_breaker.check_circuit()
    if GROQ_API_KEY and not is_blocked:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                f"Summarize the following information concisely, focusing on {focus}:\n\n"
                f"{text[:3000]}\n\n"
                f"Summary (concise bullet points or 2-3 sentences):"
            )
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
                temperature=0.3
            )
            summary = (resp.choices[0].message.content or "").strip()
            if summary:
                return summary
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                groq_circuit_breaker.record_429(e)
            logger.debug(f"[tools._summarize] Groq synthesis note: {e}")

    # Deterministic extractive summary fallback (if offline / no Groq key)
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("http")]
    bullets = []
    for l in lines:
        cleaned = re.sub(r'^[•\-\*]\s*', '', l)
        if len(cleaned) > 25 and cleaned not in bullets:
            bullets.append(f"• {cleaned}")
            if len(bullets) >= 4:
                break
    if bullets:
        return "Summary of key points:\n" + "\n".join(bullets)
    return f"Summary: {text[:300]}..."


def _unsupported_desktop_action(args: dict = None) -> str:
    app = "Notepad"
    if args and isinstance(args, dict):
        app = args.get('app_name', 'Notepad') or "Notepad"
    return f"I can open {app.title()}, but arbitrary desktop typing and file saving are not currently supported."


# ─── Tool Registry ─────────────────────────────────────────────────────────────
AVAILABLE_TOOLS = {
    "web_search": {
        "description": (
            "Search the web for current facts, people, events, or information. "
            "ALWAYS use this for: current office holders (PM, CM, CEO, President), "
            "recent news, latest product releases, current prices, job openings, "
            "company information, or any query where freshness matters. "
            "Arguments: {'query': 'search terms'}."
        ),
        "func": _web_search
    },
    "get_weather": {
        "description": (
            "Get current weather conditions for a city. "
            "ALWAYS use this for weather-related questions. Arguments: {'city': 'city name'}."
        ),
        "func": _get_weather
    },
    "take_screenshot": {
        "description": "Capture a screenshot of the user's screen and save it to the Desktop.",
        "func": _take_screenshot
    },
    "open_application": {
        "description": (
            "Open a whitelisted application such as notepad, calculator, chrome, vscode. "
            "Arguments: {'app_name': 'application name'}."
        ),
        "func": _open_application
    },
    "control_volume": {
        "description": (
            "Adjust system volume. Actions: 'up', 'down', 'mute', 'unmute'. "
            "Arguments: {'action': 'up|down|mute|unmute'}."
        ),
        "func": _control_volume
    },
    "save_note": {
        "description": (
            "Save a text note to the user's persistent notes collection. "
            "Arguments: {'text': 'content of the note'}."
        ),
        "func": _save_note
    },
    "get_notes": {
        "description": "Retrieve recent saved notes from the user's notes collection.",
        "func": _get_notes
    },
    "set_reminder": {
        "description": (
            "Set a reminder with a description and time. "
            "Arguments: {'text': 'reminder description', 'time': 'time or delta'}."
        ),
        "func": _set_reminder
    },
    "summarize": {
        "description": (
            "Summarize a block of text or search findings into key points. "
            "Arguments: {'text': 'text to summarize', 'focus': 'optional focus area'}."
        ),
        "func": _summarize
    },
    "unsupported_desktop_action": {
        "description": "Truthfully reports that arbitrary desktop keystrokes and file saving are not supported.",
        "func": _unsupported_desktop_action
    }
}


def get_tool_schemas() -> list:
    """Return Groq-compatible tool schema list."""
    schemas = []
    for name, info in AVAILABLE_TOOLS.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query":    {"type": "string", "description": "Search query (for web_search)"},
                        "city":     {"type": "string", "description": "City name (for get_weather)"},
                        "app_name": {"type": "string", "description": "Application name (for open_application)"},
                        "action":   {"type": "string", "description": "Volume action: up|down|mute|unmute"},
                        "text":     {"type": "string", "description": "Text content (for save_note, summarize, set_reminder)"},
                        "content":  {"type": "string", "description": "Alternative text content"},
                        "time":     {"type": "string", "description": "Time string or description (for set_reminder)"},
                        "focus":    {"type": "string", "description": "Focus area for summary"}
                    }
                }
            }
        })
    return schemas
