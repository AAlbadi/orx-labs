import logging
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/v1"

class ApolloApiService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    async def verify_api_key(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Validates the Apollo API key using Apollo's official health endpoint."""
        key = api_key or self.api_key
        if not key:
            return {"valid": False, "error": "No Apollo API key provided."}

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": key
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{APOLLO_BASE_URL}/auth/health", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("healthy") or data.get("is_logged_in"):
                        return {
                            "valid": True,
                            "message": "Apollo API key is active & connected!",
                            "details": data
                        }
                return {
                    "valid": False,
                    "error": f"Invalid Apollo Key (HTTP {res.status_code}): {res.text}"
                }
        except Exception as e:
            return {"valid": False, "error": f"Connection to Apollo API failed: {str(e)}"}

    async def enrich_organization(self, domain: str, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Enriches organization firmographics via Apollo API."""
        key = api_key or self.api_key
        if not key:
            return {}

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": key
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{APOLLO_BASE_URL}/organizations/enrich?domain={domain}", headers=headers)
                if res.status_code == 200:
                    return res.json().get("organization", {})
        except Exception as e:
            logger.debug(f"Org enrichment error: {e}")
        return {}

    async def search_and_enrich_people(
        self,
        query: str,
        titles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        limit: int = 5,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Searches Apollo people endpoint with fallback for Free plans."""
        key = api_key or self.api_key
        if not key:
            return {"success": False, "error": "Missing Apollo API Key", "leads": []}

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": key
        }

        payload: Dict[str, Any] = {
            "page": 1,
            "per_page": min(limit, 25),
        }
        if titles:
            payload["person_titles"] = titles
        if locations:
            payload["person_locations"] = locations
        if domains:
            payload["q_organization_domains"] = "\n".join(domains)
        if query:
            payload["q_keywords"] = query

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(f"{APOLLO_BASE_URL}/mixed_people/search", json=payload, headers=headers)
                
                if res.status_code == 200:
                    data = res.json()
                    people = data.get("people", [])
                    leads = []
                    for p in people:
                        first_name = p.get("first_name", "")
                        last_name = p.get("last_name", "")
                        name = p.get("name") or f"{first_name} {last_name}".strip()
                        title = p.get("title", "")
                        org = p.get("organization") or {}
                        company_name = org.get("name") or p.get("organization_name", "")
                        location = f"{p.get('city', '')}, {p.get('state', '')} {p.get('country', '')}".strip(" ,")
                        email = p.get("email")
                        linkedin_url = p.get("linkedin_url") or f"https://www.linkedin.com/search/results/all/?keywords={name}"

                        leads.append({
                            "id": p.get("id") or str(len(leads) + 1),
                            "name": name,
                            "headline": p.get("headline") or f"{title} at {company_name}",
                            "role": title,
                            "company": company_name,
                            "location": location,
                            "linkedin_url": linkedin_url,
                            "email": email,
                            "email_status": "verified" if email else "unavailable",
                            "phone": p.get("phone_numbers", [{}])[0].get("sanitized_number") if p.get("phone_numbers") else None,
                            "photo_url": p.get("photo_url"),
                            "status": "Unlocked" if email else "Found",
                            "apollo_unlocked": bool(email),
                            "meta": {
                                "company_industry": org.get("industry", ""),
                                "company_size": org.get("estimated_num_employees", ""),
                                "annual_revenue": org.get("annual_revenue_printed", ""),
                                "seniority": p.get("seniority", ""),
                            }
                        })

                    return {"success": True, "leads": leads}
                elif res.status_code == 403:
                    # Free plan API restriction - indicate fallback to Chrome Extension
                    return {
                        "success": False,
                        "free_tier_restricted": True,
                        "error": "Apollo Free Plan API restriction. Using Chrome Extension to unlock emails for free!",
                        "leads": []
                    }
                else:
                    return {"success": False, "error": res.text, "leads": []}
        except Exception as e:
            return {"success": False, "error": str(e), "leads": []}

    async def match_and_enrich_single(
        self,
        name: Optional[str] = None,
        domain: Optional[str] = None,
        company_name: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Direct Person Match endpoint."""
        key = api_key or self.api_key
        if not key:
            return {"error": "Missing Apollo API Key"}

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": key
        }

        payload: Dict[str, Any] = {"reveal_personal_emails": False}
        if name:
            parts = name.split()
            payload["first_name"] = parts[0]
            if len(parts) > 1:
                payload["last_name"] = " ".join(parts[1:])
        if domain:
            payload["domain"] = domain
        if company_name:
            payload["organization_name"] = company_name
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(f"{APOLLO_BASE_URL}/people/match", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    person = data.get("person") or {}
                    return {
                        "success": True,
                        "email": person.get("email"),
                        "phone": person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                        "title": person.get("title"),
                    }
        except Exception:
            pass
        return {"success": False}
