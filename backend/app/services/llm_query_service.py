import os
import json
import re
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
import httpx
from dotenv import load_dotenv
load_dotenv()
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

class LlmQueryService:
    def __init__(self):
        self.search_service = SearchService()

    async def translate_query(self, user_prompt: str, gemini_api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Translates user ICP into a high-precision search query using:
        1. Google Gemini Flash API (gemini-flash-lite-latest / gemini-flash-latest)
        2. Fast Groq / OpenAI (if key provided)
        3. Built-in Semantic AI Query Compiler (Fallback)
        """
        api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
        
        if api_key:
            # 1. Try Gemini API
            if api_key.startswith("AQ.") or api_key.startswith("AIza") or "gemini" in api_key.lower() or os.getenv("GEMINI_API_KEY"):
                gemini_res = await self._call_gemini_flash(user_prompt, api_key)
                if gemini_res:
                    if gemini_res.get("dork_query"):
                        gemini_res["dork_query"] = re.sub(r'\s+AND\s+', ' ', gemini_res["dork_query"])
                    return gemini_res

            # 2. Try OpenAI / Groq API
            openai_res = await self._call_openai_compatible(user_prompt, api_key)
            if openai_res:
                return openai_res

        # 3. Fallback: High-precision deterministic Semantic Compiler
        compiled = self.search_service.compile_smart_dork(user_prompt)
        return {
            "dork_query": compiled["dork"],
            "category": compiled.get("category", "general"),
            "target_company": compiled.get("target_company"),
            "location": compiled.get("location"),
            "llm_used": "Semantic AI Compiler (Built-in)"
        }

    async def _call_gemini_flash(self, prompt: str, api_key: str) -> Optional[Dict[str, Any]]:
        """Calls Google Gemini Cloud API endpoint with ultra-fast models."""
        models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        
        system_instruction = (
            "You are the master AI Lead Intelligence Architect. "
            "Analyze the user's natural language target prompt and autonomously decide the optimal search strategy, boolean dorks, sub-queries, and ICP parameters.\n\n"
            "Decision Requirements:\n"
            "1. 'dork_query': The #1 primary high-yield Google/LinkedIn dork starting with `site:linkedin.com/in/`.\n"
            "2. 'sub_dorks': A list of 4-8 distinct sub-dorks with varied boolean angles, sub-titles, and location expansions for comprehensive multi-page discovery.\n"
            "3. 'target_company': Named target corporate company if specified, else null.\n"
            "4. 'target_roles': List of canonical professional titles.\n"
            "5. 'location': Standard canonical geographic region (e.g. 'San Francisco', 'New York', 'London', 'Dubai') if specified, else null.\n"
            "6. 'icp_industry': Inferred target industry (e.g. 'Fintech', 'Enterprise SaaS', 'Healthcare AI', 'Venture Capital').\n"
            "7. 'search_strategy': 1-sentence explanation of the autonomous search approach.\n\n"
            "JSON Output Schema:\n"
            "{\n"
            "  \"dork_query\": \"site:linkedin.com/in/ ...\",\n"
            "  \"sub_dorks\": [\"site:linkedin.com/in/ ...\", \"site:linkedin.com/in/ ...\"],\n"
            "  \"target_company\": null,\n"
            "  \"target_roles\": [\"Title 1\", \"Title 2\"],\n"
            "  \"location\": \"Location Name\",\n"
            "  \"icp_industry\": \"Industry Name\",\n"
            "  \"search_strategy\": \"Strategy explanation\"\n"
            "}\n"
            "Output ONLY valid JSON."
        )

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_instruction}\n\nUser Query: {prompt}"}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }

        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                async with httpx.AsyncClient(timeout=8.0, http2=False) as client:
                    res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                    if res.status_code == 200:
                        data = res.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(raw_text)
                        parsed["llm_used"] = f"Google Gemini Flash ({model})"
                        return parsed
            except Exception as e:
                logger.warning(f"Gemini {model} error: {e}")
        return None

    async def batch_multi_extract_candidates(self, search_items: List[Dict[str, Any]], gemini_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Uses Gemini AI to intelligently unpack, verify current active roles, and predict official domains."""
        api_key = gemini_key or os.getenv("GEMINI_API_KEY")
        if not api_key or not search_items:
            return search_items

        models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        system_instruction = (
            "You are an expert AI Lead Intelligence Engine. "
            "The input is a list of LinkedIn search results (some results contain MULTIPLE professionals combined). "
            "Extract EVERY unique professional mentioned into a flat JSON array.\n"
            "For each professional, dynamically decide their CURRENT active employment and corporate domain:\n"
            "1. 'company': The CURRENT / ACTIVE corporate employer where they currently work TODAY (e.g. 'Bombas', 'OpenRouter', 'Maximum New York', 'New York Road Runners', 'Coinrule', 'Akeneo').\n"
            "   - In LinkedIn headlines ('[Name] - [Title] at [Company] | LinkedIn'), the phrase after 'at ' or '@ ' or 'of ' is their CURRENT company.\n"
            "   - In snippets with 'Experience: [Role] · [Company] · [Dates/Present]', the FIRST listed company (or the one with 'Present') is their CURRENT company.\n"
            "   - NEVER extract past/former companies (e.g. ignore companies preceded by 'Ex-', 'Former', 'Past', 'Previously at').\n"
            "   - NEVER output cities, states, or locations (e.g. NEVER output 'New York', 'San Francisco', 'Manhattan', 'California', 'London') as company names.\n"
            "   - Strip accelerator tags (e.g. 'YC W24', 'Y Combinator', 'Techstars') from company name to keep the true startup name.\n"
            "2. 'name': Clean human full name ONLY (e.g. 'David Heath', 'Alex Atallah', 'Daniel Golliher').\n"
            "3. 'headline': Current professional job title (e.g. 'Founder & CEO', 'Cofounder & CEO', 'President').\n"
            "4. 'domain': Predicted official corporate domain (e.g. 'bombas.com', 'openrouter.ai', 'maximumnewyork.com', 'nyrr.org', 'coinrule.com'), else null.\n"
            "5. 'seniority': Dynamic seniority level ('Founder', 'C-Level', 'VP', 'Director', 'Manager', 'Lead').\n"
            "6. 'location': City and country.\n"
            "7. 'linkedin_url': Retain URL.\n"
            "Output ONLY a valid JSON array."
        )

        async def _extract_chunk(chunk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            input_data = [
                {"title": c.get("title", ""), "snippet": c.get("snippet", "") or c.get("body", ""), "url": c.get("linkedin_url", "") or c.get("href", "")}
                for c in chunk
            ]
            payload = {
                "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\nSearch Results:\n{json.dumps(input_data)}"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}
            }
            for model in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                try:
                    async with httpx.AsyncClient(timeout=4.0, http2=False) as client:
                        res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                        if res.status_code == 200:
                            parsed = json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
                            if isinstance(parsed, list):
                                return parsed
                        elif res.status_code in [429, 403, 404]:
                            break
                except Exception as e:
                    logger.warning(f"Gemini multi-extract chunk error ({model}): {e}")
            return chunk

        chunk_size = 6
        chunks = [search_items[i:i + chunk_size] for i in range(0, len(search_items), chunk_size)]
        tasks = [_extract_chunk(ch) for ch in chunks]
        results_nested = await asyncio.gather(*tasks)

        all_extracted: List[Dict[str, Any]] = []
        seen_names = set()
        for r_list in results_nested:
            for item in r_list:
                name = item.get("name", "").strip()
                if name and name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    if not item.get("linkedin_url"):
                        slug = re.sub(r'[^a-zA-Z0-9]', '-', name.lower())
                        item["linkedin_url"] = f"https://www.linkedin.com/in/{slug}"
                    all_extracted.append(item)

        return all_extracted if all_extracted else search_items

    async def _call_openai_compatible(self, prompt: str, api_key: str) -> Optional[Dict[str, Any]]:
        """Calls Groq or OpenAI compatible JSON chat endpoint."""
        is_groq = "gsk_" in api_key
        url = "https://api.groq.com/openai/v1/chat/completions" if is_groq else "https://api.openai.com/v1/chat/completions"
        model = "llama-3.3-70b-versatile" if is_groq else "gpt-4o-mini"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a LinkedIn boolean search compiler. Output JSON with 'dork_query', 'target_company', 'location', 'is_enterprise'."
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["choices"][0]["message"]["content"]
                    parsed = json.loads(raw_text)
                    parsed["llm_used"] = f"{'Groq Llama 3.3' if is_groq else 'OpenAI'} (Cloud AI)"
                    return parsed
        except Exception as e:
            logger.warning(f"LLM chat error: {e}")
        return None
