import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)

class ScrapeGraphService:
    """Intelligent Web & Company Leadership Scraper using ScrapeGraphAI & Gemini."""

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")

    async def scrape_company_leadership(self, domain: str, company_name: str, gemini_key: Optional[str] = None) -> Dict[str, Any]:
        """Scrapes the company official website / about page to verify active executives and company profile."""
        api_key = gemini_key or self.gemini_key or os.getenv("GEMINI_API_KEY")
        clean_dom = re.sub(r'^https?://', '', domain).split('/')[0].strip()
        
        target_urls = [
            f"https://{clean_dom}/about",
            f"https://{clean_dom}/team",
            f"https://{clean_dom}/leadership",
            f"https://{clean_dom}/about-us",
            f"https://{clean_dom}"
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        html_content = ""
        resolved_url = ""

        # Fetch HTML asynchronously with low latency
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True, verify=False, http2=False) as client:
            for url in target_urls:
                try:
                    res = await client.get(url, headers=headers)
                    if res.status_code == 200 and len(res.text) > 500:
                        html_content = res.text[:30000] # Take first 30KB
                        resolved_url = str(res.url)
                        break
                except Exception:
                    continue

        if not html_content or not api_key:
            return {"executives": [], "company_name": company_name, "domain": clean_dom}

        # Use Gemini to extract leadership team from HTML
        prompt = (
            f"Analyze the HTML from {resolved_url} ({company_name}) and extract:\n"
            "1. 'executives': A list of active leadership team members (name, title, role).\n"
            "2. 'company_description': 1-sentence company summary.\n"
            "3. 'industry': Target industry.\n"
            "Output JSON format: {\"executives\": [{\"name\": \"...\", \"title\": \"...\"}], \"company_description\": \"...\", \"industry\": \"...\"}"
        )

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": f"{prompt}\n\nHTML CONTENT:\n{html_content}"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}
            }
            async with httpx.AsyncClient(timeout=4.0, http2=False) as client:
                res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(raw_text)
                    parsed["source_url"] = resolved_url
                    parsed["domain"] = clean_dom
                    return parsed
        except Exception as e:
            logger.warning(f"ScrapeGraph company leadership extraction error: {e}")

        return {"executives": [], "company_name": company_name, "domain": clean_dom}

    async def verify_executive_at_company(self, executive_name: str, company_name: str, domain: str, gemini_key: Optional[str] = None) -> bool:
        """Verifies if an executive is listed on the official company website."""
        data = await self.scrape_company_leadership(domain, company_name, gemini_key)
        execs = data.get("executives", [])
        norm_name = executive_name.lower().strip()
        for e in execs:
            e_name = e.get("name", "").lower().strip()
            if norm_name in e_name or e_name in norm_name:
                return True
        return False
