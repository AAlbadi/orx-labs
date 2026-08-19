"""
ContextHarvester — Real-data pipeline only. Zero mock data.

Lead Discovery (in order of preference):
  1. DuckDuckGo search + LLM structured extraction
  2. ScrapeGraphAI SearchGraph (if available and configured)
  3. LLM public knowledge lookup

Context Enrichment per lead:
  - LinkedIn: ScrapeGraphAI SmartScraper / direct HTTP + BS4 / LLM inference
  - GitHub: Official REST API
  - Academic: arXiv author search API

LLM: google/gemma-4-31b-it:free via OpenRouter (verified working)
"""
import re
import json
import time
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from bs4 import BeautifulSoup

# ── DuckDuckGo ────────────────────────────────────────────────────────────────
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        print("[Harvester] No DDG search library available.")

# ── ScrapeGraphAI ─────────────────────────────────────────────────────────────
try:
    from scrapegraphai.graphs import SmartScraperGraph, SearchGraph
    SCRAPEGRAPH_AVAILABLE = True
    print("[Harvester] ScrapeGraphAI is available.")
except ImportError:
    SCRAPEGRAPH_AVAILABLE = False
    print("[Harvester] ScrapeGraphAI not available — using direct HTTP scraping.")

from backend.app.config import settings

# Free models on OpenRouter — tried in order, skipping rate-limited ones
FREE_MODELS = [
    "google/gemma-4-31b-it:free",       # verified working
    "openai/gpt-oss-120b:free",          # verified working
    "openai/gpt-oss-20b:free",           # fallback
    "nousresearch/hermes-3-llama-3.1-405b:free",  # extra fallback
]

# ── Shared HTTP session ───────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


def _llm_call(system: str, user: str, json_mode: bool = False) -> str | None:
    """Call OpenRouter, rotating through free models on rate-limit. Returns None only if all fail."""
    key = settings.OPENROUTER_API_KEY
    if not key:
        return None

    for m in FREE_MODELS:
        payload = {
            "model": m,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://orx-outreach.ai",
                    "X-Title": "ORX Outreach Engine",
                },
                json=payload,
                timeout=40,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            err = resp.json().get("error", {}).get("message", "")
            if "429" in str(resp.status_code) or "rate" in err.lower() or "provider" in err.lower():
                print(f"[LLM] {m} unavailable, trying next model...")
                time.sleep(1)
                continue
            print(f"[LLM] {m} error {resp.status_code}: {err[:200]}")
            return None
        except Exception as e:
            print(f"[LLM] {m} request failed: {e}")
    print("[LLM] All free models exhausted.")
    return None


def _fetch_page_text(url: str, timeout: int = 12) -> str:
    """Fetch a URL and return clean visible text."""
    try:
        r = _session.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())[:6000]
    except Exception as e:
        print(f"[Scrape] Failed to fetch {url}: {e}")
        return ""


class ContextHarvester:

    # ──────────────────────────────────────────────────────────────────────────
    # LEAD DISCOVERY
    # ──────────────────────────────────────────────────────────────────────────

    def find_leads_via_search(self, query_string: str) -> list[dict]:
        """
        Real lead discovery:
        1. DuckDuckGo + LLM extraction (fastest, no API cost)
        2. ScrapeGraphAI SearchGraph (if installed)
        3. LLM public-knowledge lookup (always fires as final safety net)
        """
        print(f"[Harvester] Searching for leads: '{query_string}'")

        # ── Option A: DuckDuckGo + LLM extraction ─────────────────────────
        if DDGS_AVAILABLE:
            leads = self._ddg_search_and_extract(query_string)
            if leads:
                return leads

        # ── Option B: ScrapeGraphAI SearchGraph ───────────────────────────
        if SCRAPEGRAPH_AVAILABLE and settings.OPENROUTER_API_KEY:
            leads = self._scrapegraph_search(query_string)
            if leads:
                return leads

        # ── Option C: LLM public-knowledge lookup (always as final net) ───
        return self._llm_generate_leads(query_string)

    def _ddg_search_and_extract(self, query: str) -> list[dict]:
        """
        DuckDuckGo search → collect snippets → LLM structures lead data.
        """
        try:
            snippets = []
            urls_seen: set[str] = set()

            search_terms = [
                f'{query} linkedin email contact',
                f'{query} github profile',
                f'site:linkedin.com "{query}"',
            ]

            with DDGS() as ddg:
                for term in search_terms[:2]:
                    try:
                        for r in ddg.text(term, max_results=5):
                            url = r.get("href", "")
                            if url and url not in urls_seen:
                                urls_seen.add(url)
                                snippets.append(
                                    f"URL: {url}\nTitle: {r.get('title','')}\nSnippet: {r.get('body','')}"
                                )
                    except Exception as e:
                        print(f"[DDG] Search term failed: {e}")
                        continue

            if not snippets:
                print("[DDG] No search results returned")
                return []

            combined = "\n\n---\n\n".join(snippets[:10])

            raw = _llm_call(
                system=(
                    "You extract structured professional contact data from web search snippets. "
                    "Only include real people clearly identified in the snippets. "
                    "For email: use null unless explicitly visible in a snippet. "
                    "For linkedin_url: include full https://linkedin.com/in/... URL if visible. "
                    "Never invent data. Return ONLY valid JSON, no other text."
                ),
                user=(
                    f"Search query: '{query}'\n\nSearch result snippets:\n{combined}\n\n"
                    "Extract up to 4 real professionals. Return JSON ONLY:\n"
                    '{"leads": [{"email": null, "first_name": "string", "last_name": "string", '
                    '"company": "string", "role": "string", "linkedin_url": null, "github_username": null}]}'
                ),
                json_mode=True,
            )

            if raw:
                data = json.loads(raw)
                leads = data.get("leads", [])
                valid = [l for l in leads if l.get("first_name") and l.get("last_name")]
                print(f"[DDG+LLM] Extracted {len(valid)} real leads for '{query}'")
                return valid

        except Exception as e:
            print(f"[DDG+LLM] Failed: {e}")
        return []

    def _scrapegraph_search(self, query: str) -> list[dict]:
        """ScrapeGraphAI SearchGraph — uses openai-compatible endpoint."""
        try:
            config = {
                "llm": {
                    "api_key": settings.OPENROUTER_API_KEY,
                    "model": "openai/gpt-oss-20b:free",  # openai-prefixed model for compatibility
                    "base_url": "https://openrouter.ai/api/v1",
                },
                "max_results": 5,
                "verbose": False,
            }
            sg = SearchGraph(
                prompt=(
                    f"Find 3-5 real professionals related to: '{query}'. "
                    "For each person extract: email (if public), first_name, last_name, "
                    "company, role, linkedin_url, github_username. "
                    "Return JSON: {{\"leads\": [...]}}. Only real people with verifiable profiles."
                ),
                config=config,
            )
            result = sg.run()
            if isinstance(result, dict):
                leads = result.get("leads") or result.get("results") or []
            elif isinstance(result, list):
                leads = result
            else:
                leads = []

            valid = [l for l in leads if isinstance(l, dict) and l.get("first_name")]
            print(f"[ScrapeGraphAI] Found {len(valid)} leads for '{query}'")
            return valid
        except Exception as e:
            print(f"[ScrapeGraphAI] SearchGraph failed: {e}")
            return []

    def _llm_generate_leads(self, query: str) -> list[dict]:
        """LLM public knowledge lookup — names genuinely known public figures only."""
        raw = _llm_call(
            system=(
                "You are a B2B sales researcher. Name ONLY real, well-known public professionals "
                "verifiable from your training data. Never invent people. "
                "For emails: set to null unless company email format is well-known (e.g. @openai.com). "
                "Prefer people with public GitHub or LinkedIn."
            ),
            user=(
                f"Name 3 real, publicly known professionals related to: '{query}'. "
                "Return JSON: {\"leads\": [{\"email\": null, \"first_name\": string, "
                "\"last_name\": string, \"company\": string, \"role\": string, "
                "\"linkedin_url\": null, \"github_username\": null_or_string}]}"
            ),
            json_mode=True,
        )
        if raw:
            try:
                data = json.loads(raw)
                leads = data.get("leads", [])
                valid = [l for l in leads if l.get("first_name") and l.get("last_name")]
                print(f"[LLM-Lookup] Got {len(valid)} leads for '{query}'")
                return valid
            except Exception as e:
                print(f"[LLM-Lookup] Parse failed: {e}")
        return []

    # ──────────────────────────────────────────────────────────────────────────
    # CONTEXT ENRICHMENT
    # ──────────────────────────────────────────────────────────────────────────

    def harvest_lead_context(
        self,
        first_name: str,
        last_name: str,
        company: str,
        linkedin_url: str = None,
        github_username: str = None,
        academic_profile: str = None,
    ) -> dict:
        """Real context enrichment — no mocks."""
        context: dict = {
            "linkedin": {},
            "github": [],
            "publications": [],
        }

        # 1. LinkedIn
        if linkedin_url:
            context["linkedin"] = self._scrape_linkedin(linkedin_url, first_name, last_name, company)
        else:
            found_url = self._find_linkedin_url(first_name, last_name, company)
            if found_url:
                context["linkedin"] = self._scrape_linkedin(found_url, first_name, last_name, company)
            else:
                context["linkedin"] = self._llm_infer_profile(first_name, last_name, company)

        # 2. GitHub
        if github_username:
            context["github"] = self._fetch_github_real(github_username)
        else:
            username = self._find_github_username(first_name, last_name, company)
            if username:
                context["github"] = self._fetch_github_real(username)

        # 3. arXiv
        context["publications"] = self._fetch_arxiv_real(f"{first_name} {last_name}")

        return context

    def _find_linkedin_url(self, first_name: str, last_name: str, company: str) -> str | None:
        if not DDGS_AVAILABLE:
            return None
        query = f'"{first_name} {last_name}" {company} site:linkedin.com/in'
        try:
            with DDGS() as ddg:
                for r in ddg.text(query, max_results=3):
                    url = r.get("href", "")
                    if "linkedin.com/in/" in url:
                        print(f"[LinkedIn] Discovered URL: {url}")
                        return url
        except Exception as e:
            print(f"[LinkedIn] URL discovery failed: {e}")
        return None

    def _find_github_username(self, first_name: str, last_name: str, company: str) -> str | None:
        if not DDGS_AVAILABLE:
            return None
        query = f'"{first_name} {last_name}" {company} site:github.com'
        try:
            with DDGS() as ddg:
                for r in ddg.text(query, max_results=3):
                    url = r.get("href", "")
                    m = re.match(r"https?://github\.com/([^/\?#]+)/?$", url)
                    if m:
                        username = m.group(1)
                        if username not in ("login", "signup", "about", "features", "orgs"):
                            print(f"[GitHub] Discovered username: @{username}")
                            return username
        except Exception as e:
            print(f"[GitHub] Username discovery failed: {e}")
        return None

    def _scrape_linkedin(self, url: str, first_name: str, last_name: str, company: str) -> dict:
        """Try ScrapeGraphAI → direct HTTP → LLM inference."""
        # Try ScrapeGraphAI (headless browser, handles JS)
        if SCRAPEGRAPH_AVAILABLE and settings.OPENROUTER_API_KEY:
            try:
                config = {
                    "llm": {
                        "api_key": settings.OPENROUTER_API_KEY,
                        "model": "openai/gpt-oss-20b:free",
                        "base_url": "https://openrouter.ai/api/v1",
                    },
                    "verbose": False,
                    "headless": True,
                }
                scraper = SmartScraperGraph(
                    prompt=(
                        "Extract: current_role, company, summary (professional bio), "
                        "recent_posts (list of recent post texts up to 3), skills (list). "
                        "Return JSON with these exact keys."
                    ),
                    source=url,
                    config=config,
                )
                result = scraper.run()
                if isinstance(result, dict) and (result.get("summary") or result.get("current_role")):
                    print(f"[LinkedIn] ScrapeGraphAI succeeded for {url}")
                    return result
            except Exception as e:
                print(f"[LinkedIn] ScrapeGraphAI failed: {e}")

        # Try direct HTTP (works for some public profiles)
        text = _fetch_page_text(url)
        if text and len(text) > 300 and "authwall" not in text.lower() and "sign in" not in text.lower()[:500]:
            result = _llm_call(
                system="You extract structured LinkedIn profile data from raw page text. Return only JSON.",
                user=(
                    f"Raw text from {url}:\n{text[:3000]}\n\n"
                    "Return JSON: {\"current_role\": string, \"company\": string, "
                    "\"summary\": string, \"recent_posts\": [string]}"
                ),
                json_mode=True,
            )
            if result:
                try:
                    parsed = json.loads(result)
                    if parsed.get("summary") or parsed.get("current_role"):
                        print(f"[LinkedIn] HTTP scrape succeeded for {url}")
                        return parsed
                except Exception:
                    pass

        # Fallback: LLM public knowledge
        print(f"[LinkedIn] Using LLM inference for {first_name} {last_name}")
        return self._llm_infer_profile(first_name, last_name, company)

    def _llm_infer_profile(self, first_name: str, last_name: str, company: str) -> dict:
        """Ask LLM what it knows about this person from public sources."""
        result = _llm_call(
            system=(
                "You are a professional researcher. Answer ONLY with genuine public knowledge. "
                "If you have no reliable info about this specific person, say so clearly. "
                "Do not invent professional details."
            ),
            user=(
                f"What is publicly known about {first_name} {last_name} from {company}? "
                "Return JSON: {\"current_role\": string, \"company\": string, "
                "\"summary\": string, \"recent_posts\": []}"
            ),
            json_mode=True,
        )
        if result:
            try:
                return json.loads(result)
            except Exception:
                pass
        return {
            "current_role": f"Professional at {company}",
            "company": company,
            "summary": f"{first_name} {last_name} — {company}. Profile data not publicly available.",
            "recent_posts": [],
        }

    def _fetch_github_real(self, username: str) -> list:
        """Real GitHub REST API."""
        try:
            url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=8"
            r = _session.get(url, timeout=10)
            if r.status_code == 200:
                repos = []
                for repo in r.json():
                    if not repo.get("fork"):
                        repos.append({
                            "name": repo["name"],
                            "description": repo.get("description") or "",
                            "language": repo.get("language") or "Unknown",
                            "stars": repo.get("stargazers_count", 0),
                            "updated_at": repo.get("updated_at", ""),
                            "url": repo.get("html_url", ""),
                        })
                print(f"[GitHub] {len(repos)} repos for @{username}")
                return repos
            elif r.status_code == 404:
                print(f"[GitHub] @{username} not found")
        except Exception as e:
            print(f"[GitHub] Failed for @{username}: {e}")
        return []

    def _fetch_arxiv_real(self, author_name: str) -> list:
        """Real arXiv API by author name."""
        try:
            query = quote(f'au:"{author_name}"')
            url = (
                f"http://export.arxiv.org/api/query?"
                f"search_query={query}&max_results=3&sortBy=submittedDate&sortOrder=descending"
            )
            r = _session.get(url, timeout=12)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                ns = "{http://www.w3.org/2005/Atom}"
                papers = []
                for entry in root.findall(f"{ns}entry"):
                    title_el = entry.find(f"{ns}title")
                    summary_el = entry.find(f"{ns}summary")
                    pub_el = entry.find(f"{ns}published")
                    id_el = entry.find(f"{ns}id")
                    if title_el is not None:
                        papers.append({
                            "title": title_el.text.strip().replace("\n", " "),
                            "summary": (summary_el.text.strip()[:300] + "…") if summary_el is not None else "",
                            "published_at": pub_el.text.strip() if pub_el is not None else "",
                            "url": id_el.text.strip() if id_el is not None else "",
                        })
                print(f"[arXiv] {len(papers)} papers for '{author_name}'")
                return papers
        except Exception as e:
            print(f"[arXiv] Failed for '{author_name}': {e}")
        return []


harvester = ContextHarvester()
