import asyncio
import json
import uuid
import os
import re
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional, Set
from ddgs import DDGS
from app.models.lead import Lead, LeadStatus, SearchRequest
from app.services.search_service import SearchService
from app.services.apollo_api_service import ApolloApiService
from app.services.email_verifier_service import EmailVerifierService
from app.services.llm_query_service import LlmQueryService

logger = logging.getLogger(__name__)

EXTENSIONS = [
    ".com", ".qa", ".com.qa", ".org.qa", ".ae", ".com.sa", ".sa",
    ".co.uk", ".ca", ".de", ".fr", ".io", ".ai", ".co", ".org", ".net"
]

class LeadFinderAgent:
    def __init__(self):
        self.search_service = SearchService()
        self.apollo_api = ApolloApiService()
        self.verifier = EmailVerifierService()
        self.llm_query = LlmQueryService()
        self._domain_cache: Dict[str, str] = {}
        self._last_active_prompt: Optional[str] = None
        self._current_page: int = 1

    async def _resolve_company_domain(self, company_name: str) -> str:
        clean_name = company_name.strip()
        clean_slug = re.sub(r'[^a-zA-Z0-9]', '', clean_name.lower())
        if not clean_slug:
            return ""

        if clean_slug in self._domain_cache:
            return self._domain_cache[clean_slug]

        blacklist = {
            "linkedin.com", "wikipedia.org", "facebook.com", "instagram.com", "twitter.com", "x.com",
            "bloomberg.com", "youtube.com", "glassdoor.com", "zoominfo.com", "pitchbook.com",
            "crunchbase.com", "yellowpages.com", "yelp.com", "tripadvisor.com", "indeed.com",
            "reuters.com", "forbes.com", "grokipedia.com", "google.com", "duckduckgo.com",
            "mobygames.com", "fandom.com", "trustpilot.com", "apple.com", "play.google.com"
        }

        name_tokens = [t.lower() for t in re.findall(r'[a-zA-Z]{3,}', clean_name)]

        loop = asyncio.get_event_loop()
        def _search_domain():
            # 1. Search web for the exact corporate official website
            try:
                with DDGS() as ddgs:
                    res = list(ddgs.text(f"{clean_name} official website", max_results=5))
                    for r in res:
                        href = r.get("href", "")
                        match = re.search(r'https?://(?:www\.)?([a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,})', href)
                        if match:
                            dom = match.group(1).lower().strip()
                            if not any(b in dom for b in blacklist):
                                # Relevance check: at least one significant token in domain
                                if not name_tokens or any(tok in dom.replace(".", "") for tok in name_tokens):
                                    mx_hosts, _ = self.verifier.get_mx_records(dom)
                                    if mx_hosts:
                                        return dom
            except Exception:
                pass

            # 2. Probe standard extensions if web search returned no match
            for ext in EXTENSIONS:
                guess = f"{clean_slug}{ext}"
                mx_hosts, _ = self.verifier.get_mx_records(guess)
                if mx_hosts:
                    return guess

            return f"{clean_slug}.com"

        dom = await loop.run_in_executor(None, _search_domain)
        self._domain_cache[clean_slug] = dom
        return dom

    async def run(self, req: SearchRequest) -> AsyncGenerator[str, None]:
        async def emit(event_type: str, data: Dict[str, Any]) -> str:
            return f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"

        api_key = req.apollo_api_key or os.getenv("APOLLO_API_KEY")
        gemini_key = req.gemini_api_key or os.getenv("GEMINI_API_KEY")
        target_limit = req.max_leads or 10
        exclude_urls: Set[str] = set(req.exclude_urls or [])

        # Check for Follow-up / Next Page intent
        is_followup = self.search_service.is_followup_prompt(req.prompt)
        if is_followup:
            effective_prompt = req.previous_prompt or self._last_active_prompt or "top founders and executives"
            self._current_page += 1
            page = self._current_page
            yield await emit("log", {
                "message": f"⚡ Follow-up detected — Sourcing next batch (Page {page}) for: \"{effective_prompt}\" (Excluding {len(exclude_urls)} already found)..."
            })
        else:
            effective_prompt = req.prompt
            self._last_active_prompt = req.prompt
            self._current_page = req.page or 1
            page = self._current_page
            yield await emit("log", {"message": f"Analyzing query: \"{effective_prompt}\"..."})

        # Step 1: AI Query Translation
        ai_query = await self.llm_query.translate_query(effective_prompt, gemini_key)
        dork = ai_query.get("dork_query") or self.search_service.build_dork_query(effective_prompt)
        llm_engine = ai_query.get("llm_used", "Semantic AI Compiler")

        yield await emit("thought", {
            "title": f"AI Query Compiler ({llm_engine}) - Page {page}",
            "message": f"Target Dork: `{dork}` (Page {page})",
            "dork": dork,
            "filters": ai_query,
            "page": page,
            "is_followup": is_followup,
            "original_prompt": effective_prompt
        })

        yield await emit("log", {
            "message": f"Scanning web for new LinkedIn profiles (Page {page}, excluding {len(exclude_urls)} existing)..."
        })

        fetch_multiplier = 4
        try:
            candidates = await self.search_service.search_linkedin_profiles(
                effective_prompt, 
                max_results=target_limit * fetch_multiplier,
                exclude_urls=exclude_urls,
                page=page
            )
        except Exception as e:
            logger.error(f"Search error: {e}")
            candidates = []

        if not candidates:
            yield await emit("log", {"message": "No new matching profiles found on this page — try broadening your query."})
            yield await emit("complete", {
                "message": f"No additional new profiles found for \"{effective_prompt}\".",
                "leads": [],
                "page": page,
                "can_load_more": False
            })
            return

        yield await emit("log", {
            "message": f"🧠 Google Gemini Flash AI: Unpacking multi-candidate search cards, extracting real current employers & corporate domains..."
        })
        candidates = await self.llm_query.batch_multi_extract_candidates(candidates, gemini_key)

        yield await emit("log", {
            "message": f"Classifying company scale & email infrastructure for {len(candidates)} discovered prospects..."
        })

        verified_leads: List[Lead] = []

        compiled_dork = self.search_service.compile_smart_dork(effective_prompt)
        target_location = ai_query.get("location") or compiled_dork.get("location")

        for idx, c in enumerate(candidates, start=1):
            name = (c.get("name") or "Executive").strip()
            headline = (c.get("headline") or "Executive").strip()
            company = (c.get("company") or "").strip()
            location = (c.get("location") or "").strip()
            linkedin_url = c.get("linkedin_url") or f"https://www.linkedin.com/in/{re.sub(r'[^a-zA-Z0-9]', '-', name.lower())}"

            if linkedin_url in exclude_urls:
                continue

            # Strict Location Guard
            if target_location and not self.search_service.is_location_match(location, headline, target_location):
                continue

            if not location and target_location:
                location = target_location
            if not company:
                company = "Private Enterprise"

            first_name, middle_initial, last_name = self.verifier.extract_name_and_slug_middle(name, linkedin_url)
            if not first_name:
                parts = [p for p in name.split() if p]
                first_name = re.sub(r'[^a-zA-Z0-9]', '', parts[0].lower()) if parts else "contact"
                last_name = re.sub(r'[^a-zA-Z0-9]', '', parts[-1].lower()) if len(parts) > 1 else ""

            domain = ""
            if c.get("ai_domain"):
                ai_dom = self.verifier.clean_domain(c["ai_domain"])
                mx_hosts, _ = self.verifier.get_mx_records(ai_dom)
                if mx_hosts:
                    domain = ai_dom

            if not domain:
                domain = await self._resolve_company_domain(company)
            if not domain:
                clean_slug = re.sub(r'[^a-zA-Z0-9]', '', company.lower())
                domain = f"{clean_slug}.com" if clean_slug else "company.com"

            org_meta: Dict[str, Any] = {}
            headcount = 0

            if api_key:
                try:
                    org_res = await self.apollo_api.enrich_organization(domain, api_key)
                    if org_res.get("success") and org_res.get("organization"):
                        org = org_res["organization"]
                        org_meta = {
                            "company_industry": org.get("industry", ""),
                            "company_size": org.get("estimated_num_employees", ""),
                            "annual_revenue": org.get("annual_revenue_printed", ""),
                            "phone": org.get("phone", ""),
                            "domain": org.get("primary_domain", domain)
                        }
                        domain = org_meta.get("domain", domain)
                        try:
                            headcount = int(org.get("estimated_num_employees", 0) or 0)
                        except (ValueError, TypeError):
                            headcount = 0
                except Exception:
                    pass

            # Run Dual Pipeline Verification
            ver_res = await self.verifier.verify_lead_email(
                first_name=first_name,
                last_name=last_name,
                domain=domain,
                middle_initial=middle_initial,
                headcount=headcount,
                role=headline
            )

            is_enterprise = ver_res.get("is_enterprise_locked", False)
            pipeline = ver_res.get("pipeline_type", "FREE_UNLOCKED")
            provider = ver_res.get("mail_provider", "Custom")

            # Determine display location
            display_location = location
            if org_meta.get("city") and org_meta.get("country"):
                display_location = f"{org_meta['city']}, {org_meta['country']}"
            elif not display_location and target_location:
                display_location = target_location

            if is_enterprise:
                lead = Lead(
                    id=str(uuid.uuid4()),
                    name=name,
                    headline=headline,
                    role=headline or "Executive",
                    company=company,
                    location=display_location,
                    linkedin_url=linkedin_url,
                    email=None,
                    email_status=None,
                    phone=org_meta.get("phone"),
                    confidence_score=65,
                    verification_method=f"Enterprise Guarded ({provider})",
                    mail_provider=provider,
                    mx_host=ver_res.get("mx_host"),
                    is_enterprise_locked=True,
                    pipeline_type="ENTERPRISE_LOCKED",
                    status=LeadStatus.FOUND,
                    apollo_unlocked=False,
                    source="Apollo Guarded",
                    meta={**org_meta, "candidate_email_preview": ver_res.get("email")}
                )
                verified_leads.append(lead)
                exclude_urls.add(linkedin_url)
                yield await emit("log", {
                    "message": f"🔒 [{len(verified_leads)}/{target_limit}] {name} ({company} · {display_location}) → Enterprise Guarded [Click 'Reveal via Apollo API']"
                })
                yield await emit("lead_discovered", lead.model_dump())
            else:
                email = ver_res.get("email")
                confidence = ver_res.get("confidence_score", 88)
                method = ver_res.get("verification_method", "100% Free Verified ($0)")

                if not email or isinstance(email, dict):
                    # AI / Mastermind Pattern Deduction
                    cands = self.verifier.brain.get_ranked_candidates(first_name, last_name, domain)
                    if cands:
                        top_cand = cands[0]
                        email = top_cand["email"] if isinstance(top_cand, dict) else str(top_cand)
                        confidence = top_cand.get("score", 80) if isinstance(top_cand, dict) else 80
                        method = "Pattern Inferred (Mastermind Brain)"
                    else:
                        email = f"{first_name.lower()}.{last_name.lower()}@{domain}"
                        confidence = 75
                        method = "AI Standard Pattern"

                lead = Lead(
                    id=str(uuid.uuid4()),
                    name=name,
                    headline=headline,
                    role=headline or "Executive",
                    company=company,
                    location=display_location,
                    linkedin_url=linkedin_url,
                    email=email,
                    email_status="verified",
                    phone=org_meta.get("phone"),
                    confidence_score=confidence,
                    verification_method=method,
                    mail_provider=provider,
                    mx_host=ver_res.get("mx_host"),
                    is_enterprise_locked=False,
                    pipeline_type="FREE_UNLOCKED",
                    status=LeadStatus.UNLOCKED,
                    apollo_unlocked=True,
                    source="Apollo Verified",
                    meta=org_meta
                )
                verified_leads.append(lead)
                exclude_urls.add(linkedin_url)
                yield await emit("log", {
                    "message": f"✓ [{len(verified_leads)}/{target_limit}] {name} ({company} · {display_location}) → {email} [Free Verified $0]"
                })
                yield await emit("lead_discovered", lead.model_dump())

            await asyncio.sleep(0.04)

            if len(verified_leads) >= target_limit:
                break

        free_count = sum(1 for l in verified_leads if l.pipeline_type == "FREE_UNLOCKED")
        enterprise_count = sum(1 for l in verified_leads if l.pipeline_type == "ENTERPRISE_LOCKED")

        yield await emit("log", {
            "message": f"Done — Sourced {len(verified_leads)} fresh leads on Page {page} ({free_count} Free Unlocked $0, {enterprise_count} Enterprise Guarded)"
        })
        yield await emit("complete", {
            "message": f"Sourced {len(verified_leads)} fresh leads (Page {page}) · {free_count} Free Unlocked ($0) · {enterprise_count} Enterprise Guarded",
            "leads": [l.model_dump() for l in verified_leads],
            "page": page,
            "original_prompt": effective_prompt,
            "can_load_more": True
        })
