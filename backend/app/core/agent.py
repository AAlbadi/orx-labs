import asyncio
import json
import uuid
import os
import re
import urllib.parse
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional, Set
from ddgs import DDGS
from app.models.lead import Lead, LeadStatus, SearchRequest
from app.services.search_service import SearchService
from app.services.apollo_api_service import ApolloApiService
from app.services.email_verifier_service import EmailVerifierService
from app.services.llm_query_service import LlmQueryService
from app.services.scrapegraph_service import ScrapeGraphService

logger = logging.getLogger(__name__)

EXCLUDED_DIRECTORY_DOMAINS = {
    'linkedin.com', 'wikipedia.org', 'crunchbase.com', 'bloomberg.com',
    'glassdoor.com', 'zoominfo.com', 'pitchbook.com', 'twitter.com',
    'facebook.com', 'instagram.com', 'youtube.com', 'reuters.com',
    'yahoo.com', 'google.com', 'apple.com', 'forbes.com', 'sec.gov',
    'yelp.com', 'dnb.com', 'bbb.org', 'craft.co', 'owler.com', 'github.com'
}

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
        self.scrapegraph = ScrapeGraphService()
        self._domain_cache: Dict[str, str] = {}
        self._last_active_prompt: Optional[str] = None
        self._current_page: int = 1

    async def _resolve_company_domain(self, company_name: str) -> str:
        """
        Ultra-Smart 5-Layer Company Domain Discovery & Verification:
        1. Memory / Mastermind Brain cache (0.0001s)
        2. STEP 1 (First Step): Real-Time Web Search for Company's Official Public Domain
        3. STEP 2: Legal entity stripping & candidate base slug heuristics (.com, .co, .io, .ai, .org)
        4. STEP 3: Real-time DNS MX record verification with Google/Cloudflare resolvers (8.8.8.8, 1.1.1.1)
        5. Deep MX Provider validation (Google Workspace, Microsoft 365, Proofpoint, etc.)
        """
        clean_name = company_name.strip()
        if not clean_name:
            return ""

        clean_slug = re.sub(r'[^a-zA-Z0-9]', '', clean_name.lower())
        if not clean_slug:
            return ""

        if clean_slug in self._domain_cache:
            return self._domain_cache[clean_slug]

        # 1. Check Mastermind Knowledge Base
        mm = self.verifier.mastermind.get_domain_intelligence(f"{clean_slug}.com")
        if mm and mm.get("primary_pattern"):
            self._domain_cache[clean_slug] = f"{clean_slug}.com"
            return f"{clean_slug}.com"

        # STEP 1 (FIRST STEP): Real-time Web Search for Company's Official Public Domain
        try:
            loop = asyncio.get_event_loop()
            def _search_official():
                with DDGS(timeout=1.5) as ddgs:
                    return list(ddgs.text(f'"{clean_name}" official website', max_results=4))
            res = await loop.run_in_executor(None, _search_official)
            for r in res:
                href = r.get('href') or ''
                netloc = urllib.parse.urlparse(href).netloc.lower().replace('www.', '').strip()
                dom = netloc.split(':')[0]
                if dom and not any(ex in dom for ex in EXCLUDED_DIRECTORY_DOMAINS if ex != f"{clean_slug}.com"):
                    mx_hosts, _ = self.verifier.get_mx_records(dom)
                    if mx_hosts:
                        self._domain_cache[clean_slug] = dom
                        return dom
        except Exception:
            pass

        # STEP 2 (FALLBACK): Fast base slug & morphological heuristics
        clean_name_base = re.sub(
            r'(?i)\b(?:inc|llc|ltd|limited|corp|corporation|group|holdings|co|company|partners|ventures|capital|technologies|tech|solutions|services|management|global|international|lp|l\.p\.)\b\.?',
            '',
            clean_name
        ).strip()
        base_slug = re.sub(r'[^a-zA-Z0-9]', '', clean_name_base.lower()) if clean_name_base else ""

        slugs = []
        if base_slug:
            slugs.append(base_slug)
        if clean_slug and clean_slug != base_slug:
            slugs.append(clean_slug)

        if clean_slug.endswith('ai') and len(clean_slug) > 3:
            slugs.append(clean_slug[:-2])

        candidate_domains = []
        for s in slugs:
            candidate_domains.extend([
                f"{s}.com",
                f"{s}.co",
                f"{s}.io",
                f"{s}.ai",
                f"{s}.co.uk",
                f"{s}.org",
                f"{s}.net",
                f"{s}.ca"
            ])

        for dom in candidate_domains:
            mx_hosts, _ = self.verifier.get_mx_records(dom)
            if mx_hosts:
                self._domain_cache[clean_slug] = dom
                return dom

        dom = f"{slugs[0] if slugs else clean_slug}.com"
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

        verified_leads: List[Lead] = []
        seen_names: Set[str] = set()
        compiled_dork = self.search_service.compile_smart_dork(effective_prompt)
        target_location = ai_query.get("location") or compiled_dork.get("location")

        current_search_page = page
        max_search_pages = page + 4

        while len(verified_leads) < target_limit and current_search_page <= max_search_pages:
            yield await emit("log", {
                "message": f"Scanning web for verified LinkedIn profiles (Page {current_search_page}, sourced {len(verified_leads)}/{target_limit})..."
            })

            fetch_multiplier = 4
            try:
                candidates = await self.search_service.search_linkedin_profiles(
                    effective_prompt, 
                    max_results=max((target_limit - len(verified_leads)) * fetch_multiplier, 20),
                    exclude_urls=exclude_urls,
                    page=current_search_page
                )
            except Exception as e:
                logger.error(f"Search error on page {current_search_page}: {e}")
                candidates = []

            if not candidates:
                current_search_page += 1
                continue

            candidates = await self.llm_query.batch_multi_extract_candidates(candidates, gemini_key)

            for idx, c in enumerate(candidates, start=1):
                name = (c.get("name") or "Executive").strip()
                name = re.sub(r'^linkedin\s*:?\s*', '', name, flags=re.IGNORECASE).strip()

                norm_name = re.sub(r'[^a-z0-9]', '', name.lower())
                if not norm_name or norm_name in seen_names:
                    continue

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

                # If company is an accelerator name like 'Y Combinator' but they are a startup founder
                if company.lower() in ['y combinator', 'yc', 'techstars', '500 startups', '500 global'] and any(w in headline.lower() for w in ['founder', 'ceo', 'co-founder']):
                    # Look for startup name in snippet or title
                    company = ""

                # Strict validation: Reject bio taglines, skills, and industry terms parsed as companies
                is_bio_company = self.search_service.is_fake_company(company) or company.lower() in [
                    "strategist", "sports & entertainment", "executive search", "private equity leader",
                    "tech staffing solutions", "tech staffing", "consulting", "leadership", "management",
                    "leader", "specialist", "advisor", "private enterprise", "undisclosed", "experiential"
                ]
                geo_names = {'new york', 'san francisco', 'manhattan', 'london', 'united states', 'california', 'texas', 'florida', 'united kingdom', 'brooklyn', 'queens', 'ny', 'sf', 'la'}
                if is_bio_company or not company or company.lower() in geo_names:
                    company = ""

                # If company is missing, execute quick OSINT company search
                if not company and name and name != "Executive":
                    try:
                        loop = asyncio.get_event_loop()
                        def _find_company_osint():
                            with DDGS(timeout=1.5) as ddgs:
                                return list(ddgs.text(f'"{name}" CEO founder current company linkedin', max_results=2))
                        osint_hits = await loop.run_in_executor(None, _find_company_osint)
                        for oh in osint_hits:
                            body = oh.get("body", "")
                            m = re.search(r'\b(?:Co-Founder|Founder|CEO|President|Chief Executive Officer)\s+(?:and\s+CEO\s+)?(?:of|at|@)\s+([A-Z][A-Za-z0-9\s\.\,\&-]{2,30}?)(?:\s*[\,\.\·\•\|\n]|\s+a\s+|\s+in|\s+Location|\s+since|$)', body, re.IGNORECASE)
                            if m:
                                cand_c = m.group(1).strip()
                                cand_c = re.sub(r'[\(\)\[\]\|·•,].*$', '', cand_c).strip()
                                if cand_c.lower() not in geo_names and not self.search_service.is_fake_company(cand_c):
                                    company = cand_c
                                    break
                    except Exception:
                        pass

                first_name, middle_initial, last_name = self.verifier.extract_name_and_slug_middle(name, linkedin_url)
                if not first_name:
                    parts = [p for p in name.split() if p]
                    first_name = re.sub(r'[^a-zA-Z0-9]', '', parts[0].lower()) if parts else "contact"
                    last_name = re.sub(r'[^a-zA-Z0-9]', '', parts[-1].lower()) if len(parts) > 1 else ""

                domain = ""
                if company and c.get("domain"):
                    ai_dom = self.verifier.clean_domain(c["domain"])
                    mx_hosts, _ = self.verifier.get_mx_records(ai_dom)
                    if mx_hosts:
                        domain = ai_dom

                if not domain and company:
                    domain = await self._resolve_company_domain(company)

                # If company or domain is missing/fake, mark as generic
                is_generic_company = not company or not domain or domain in ["company.com", "privateenterprise.com", "none"]

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

                if domain and not org_meta.get("company_industry"):
                    try:
                        scrape_data = await self.scrapegraph.scrape_company_leadership(domain, company, gemini_key)
                        if scrape_data.get("industry"):
                            org_meta["company_industry"] = scrape_data["industry"]
                        if scrape_data.get("company_description"):
                            org_meta["company_description"] = scrape_data["company_description"]
                    except Exception:
                        pass

                generic_companies = {"private enterprise", "stealth", "self-employed", "freelance", "stealth startup", "confidential"}
                is_generic_company = not company or company.lower().strip() in generic_companies
                if is_generic_company or domain in ["privateenterprise.com", "company.com", "unknown.com", "stealth.com"]:
                    is_generic_company = True

                # Run Dual Pipeline Verification
                ver_res = await self.verifier.verify_lead_email(
                    first_name=first_name,
                    last_name=last_name,
                    domain=domain,
                    middle_initial=middle_initial,
                    headcount=headcount,
                    role=headline,
                    company_name=company
                )

                is_enterprise = bool(ver_res.get("is_enterprise_locked") or is_generic_company)
                pipeline = "ENTERPRISE_LOCKED" if is_enterprise else ver_res.get("pipeline_type", "FREE_UNLOCKED")
                provider = ver_res.get("mail_provider", "Custom")

                # Check if email is invalid or 2-letter username
                raw_email = ver_res.get("email")
                if raw_email and len(raw_email.split("@")[0]) <= 2:
                    is_enterprise = True
                    pipeline = "ENTERPRISE_LOCKED"
                    raw_email = None

                # Determine display location
                display_location = location
                if org_meta.get("city") and org_meta.get("country"):
                    display_location = f"{org_meta['city']}, {org_meta['country']}"
                elif not display_location and target_location:
                    display_location = target_location

                is_guarded_record = is_enterprise or not raw_email or is_generic_company
                if is_guarded_record or not raw_email:
                    # Guarded records are hidden per user preference
                    continue

                email = raw_email
                confidence = ver_res.get("confidence_score", 90)
                method = ver_res.get("verification_method", "Verified Direct Inbox")

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
                    source="Verified Direct",
                    meta=org_meta
                )
                verified_leads.append(lead)
                seen_names.add(norm_name)
                exclude_urls.add(linkedin_url)
                yield await emit("log", {
                    "message": f"✓ [{len(verified_leads)}/{target_limit}] {name} ({company} · {display_location}) → {email}"
                })
                yield await emit("lead_discovered", lead.model_dump())

                await asyncio.sleep(0.04)

                if len(verified_leads) >= target_limit:
                    break

            current_search_page += 1

        yield await emit("log", {
            "message": f"Done — Sourced {len(verified_leads)} verified prospects on Page {page}."
        })
        yield await emit("complete", {
            "message": f"Sourced {len(verified_leads)} verified prospects on Page {page}.",
            "leads": [l.model_dump() for l in verified_leads],
            "page": page,
            "original_prompt": effective_prompt,
            "can_load_more": True
        })
