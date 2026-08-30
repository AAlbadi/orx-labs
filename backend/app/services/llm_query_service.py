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
        models = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-lite-latest"]
        
        system_instruction = (
            "You are an expert LinkedIn OSINT Boolean Search Engineer. "
            "Convert the user's lead search query into a precision Google/LinkedIn search dork. "
            "Output JSON with keys:\n"
            "- 'dork_query': site:linkedin.com/in/ ...\n"
            "- 'target_company': target company name if mentioned, else null\n"
            "- 'target_roles': list of titles\n"
            "- 'location': location name if mentioned, else null\n"
            "- 'is_enterprise': boolean (true if giant company like Apple, Tesla, Amazon, Microsoft, Walmart)\n"
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
                async with httpx.AsyncClient(timeout=8.0) as client:
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
        """Uses Gemini AI to unpack individual and multi-person search result cards into individual clean leads."""
        api_key = gemini_key or os.getenv("GEMINI_API_KEY")
        if not api_key or not search_items:
            return search_items

        models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        system_instruction = (
            "You are an expert AI Lead Intelligence Engine. "
            "The input is a list of LinkedIn search results (some results contain MULTIPLE professionals combined). "
            "Extract EVERY unique professional mentioned into a flat JSON array.\n"
            "For each professional, identify their CURRENT / MOST RECENT company using these strict rules:\n"
            "1. 'company': The CURRENT / ACTIVE corporate employer where they currently work TODAY (e.g. 'Akeneo', 'Centene Corporation', 'DAZN Group', 'Pax8', 'LavenirAI', 'Mott MacDonald').\n"
            "   - In LinkedIn headlines ('[Name] - [Title] at [Company] | LinkedIn'), the phrase after 'at ' or '@ ' is ALWAYS their CURRENT company.\n"
            "   - In snippets with 'Experience: [Role] · [Company] · [Dates/Present]', the FIRST listed company (or the one with 'Present') is their CURRENT company.\n"
            "   - NEVER extract past/former companies (e.g. ignore companies preceded by 'Ex-', 'Former', 'Past', 'Previously at').\n"
            "   - NEVER use bio taglines, skills, or industries (e.g. NEVER output 'Strategist', 'Sports & Entertainment', 'Executive search', 'Private Equity', 'Tech Staffing', 'Consultant', 'Leader').\n"
            "   - If their current employer is genuinely unknown, set 'company' to null.\n"
            "2. 'name': Clean human full name ONLY (e.g. 'Sarah Assous', 'Ruth Duston', 'Rob Pope'). MUST NOT start with 'LinkedIn' or contain credentials.\n"
            "3. 'headline': Real current professional job title (e.g. 'Chief Marketing Officer', 'Digital Marketing Director', 'VP Strategic Development').\n"
            "4. 'domain': Expected primary official corporate domain if confident (e.g. 'akeneo.com', 'dazngroup.com', 'lavenirai.com', 'pax8.com'), else null.\n"
            "5. 'location': City and country\n"
            "6. 'linkedin_url': Retain URL\n"
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
                    async with httpx.AsyncClient(timeout=3.0) as client:
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
