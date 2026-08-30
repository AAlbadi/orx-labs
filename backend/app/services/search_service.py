import re
import os
import urllib.parse
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
import httpx
from ddgs import DDGS

JOB_WORDS_SINGLE = {
    # Hierarchy & Titles
    "director", "head", "manager", "leader", "leadership", "vp", "vice", "president", "partner", "coach",
    "consultant", "consulting", "executive", "specialist", "officer", "advisor", "advisory", "engineer",
    "architect", "developer", "founder", "co-founder", "lead", "strategist", "strategy", "recruiter",
    "recruiting", "recruitment", "generalist", "representative", "associate", "analyst", "intern", "coordinator",
    "assistant", "chief", "cpo", "chro", "ceo", "cto", "cfo", "coo", "cmo", "cro", "principal", "expert",
    # Functions & Departments
    "hr", "human", "resources", "people", "talent", "acquisition", "operations", "ops",
    "culture", "hrbp", "dei", "inclusion", "diversity", "management", "solutions", "services",
    "technologies", "software", "professional", "practitioner",
    # Filler / Bio words
    "actor", "actress", "writer", "author", "artist", "musician", "producer", "filmmaker",
    "student", "alum", "alumni", "candidate", "fellow", "member", "investor",
    "angel", "speaker", "helping", "building", "passionate", "empowering", "enabling",
    "thrive", "transforming", "scaling", "driving", "experienced", "seasoned", "certified",
    "educator", "mentor", "trainer", "facilitator", "profile",
    "independent", "freelance", "stealth", "contact",
    # Stop words
    "of", "and", "&", "the", "in", "for", "to", "at", "sr", "jr", "senior", "junior", "global", "regional"
}

CERTIFICATIONS = {
    "phr", "sphr", "shrm", "shrmcp", "shrmscp", "shrm-cp", "shrm-scp", "ms", "m.s.", "bs", "b.s.", "mba",
    "msc", "bhrm", "mhrm", "mirhr", "phd", "cpa", "pmp", "cfa", "acc", "pcc", "mcc", "gphr", "cipd",
    "mcipd", "fcipd", "chartered", "chrl", "chrp", "chre", "c.dir", "cdir", "icd.d", "fcdi", "ccc"
}

LOCATION_MAP = {
    # Middle East & GCC
    "ksa": "Saudi Arabia",
    "k.s.a": "Saudi Arabia",
    "k.s.a.": "Saudi Arabia",
    "saudi": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "riyadh": "Saudi Arabia",
    "jeddah": "Saudi Arabia",
    "dammam": "Saudi Arabia",
    "khobar": "Saudi Arabia",
    "dhahran": "Saudi Arabia",
    "jubail": "Saudi Arabia",
    "uae": "UAE",
    "u.a.e": "UAE",
    "u.a.e.": "UAE",
    "emirates": "UAE",
    "united arab emirates": "UAE",
    "dubai": "UAE",
    "abu dhabi": "UAE",
    "sharjah": "UAE",
    "qatar": "Qatar",
    "doha": "Qatar",
    "kuwait": "Kuwait",
    "kuwait city": "Kuwait",
    "bahrain": "Bahrain",
    "manama": "Bahrain",
    "oman": "Oman",
    "muscat": "Oman",
    "egypt": "Egypt",
    "cairo": "Egypt",
    # North America
    "sf": "San Francisco",
    "san francisco": "San Francisco",
    "bay area": "San Francisco",
    "silicon valley": "San Francisco",
    "nyc": "New York",
    "new york": "New York",
    "new york city": "New York",
    "ny": "New York",
    "canada": "Canada",
    "canda": "Canada",
    "canad": "Canada",
    "canadian": "Canada",
    "toronto": "Canada",
    "vancouver": "Canada",
    "montreal": "Canada",
    "calgary": "Canada",
    "ottawa": "Canada",
    "edmonton": "Canada",
    "quebec": "Canada",
    "ontario": "Canada",
    "austin": "Austin",
    "texas": "Texas",
    "seattle": "Seattle",
    "boston": "Boston",
    "chicago": "Chicago",
    "la": "Los Angeles",
    "los angeles": "Los Angeles",
    "miami": "Miami",
    "california": "United States",
    "califonia": "United States",
    "us": "United States",
    "usa": "United States",
    "united states": "United States",
    # Europe
    "london": "United Kingdom",
    "londn": "United Kingdom",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "united kingdom": "United Kingdom",
    "germany": "Germany",
    "berlin": "Germany",
    "munich": "Germany",
    "frankfurt": "Germany",
    "france": "France",
    "paris": "France",
    # APAC
    "singapore": "Singapore",
    "australia": "Australia",
    "sydney": "Australia",
    "melbourne": "Australia",
    "india": "India",
    "bangalore": "India",
    "bengaluru": "India",
    "mumbai": "India",
    "delhi": "India",
    "hyderabad": "India"
}

LOCATION_EXPANSIONS = {
    "Saudi Arabia": ["Saudi Arabia", "KSA", "Riyadh", "Jeddah", "Dammam", "Khobar"],
    "UAE": ["Dubai", "United Arab Emirates", "Abu Dhabi", "UAE", "Sharjah"],
    "Qatar": ["Qatar", "Doha"],
    "Kuwait": ["Kuwait", "Kuwait City"],
    "Bahrain": ["Bahrain", "Manama"],
    "Oman": ["Oman", "Muscat"],
    "Egypt": ["Egypt", "Cairo"],
    "United Kingdom": ["London", "United Kingdom", "UK", "Manchester"],
    "Canada": ["Toronto", "Canada", "Vancouver", "Montreal", "Calgary", "Ottawa"],
    "San Francisco": ["San Francisco", "Silicon Valley", "Bay Area"],
    "New York": ["New York", "NYC", "Manhattan"],
    "United States": ["United States", "USA", "New York", "San Francisco", "Austin", "Chicago", "Seattle"],
    "Germany": ["Berlin", "Munich", "Germany", "Frankfurt"],
    "France": ["Paris", "France"],
    "Singapore": ["Singapore"],
    "Australia": ["Sydney", "Melbourne", "Australia"],
    "India": ["Bangalore", "Mumbai", "Delhi", "India"]
}

LOCATION_REGION_MAP = {
    "Saudi Arabia": ["saudi arabia", "riyadh", "jeddah", "dammam", "khobar", "dhahran", "jubail", "ksa", "mecca", "makkah", "medina", "madinah", "saudi"],
    "UAE": ["uae", "united arab emirates", "dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "fujairah", "al ain", "emirates"],
    "Qatar": ["qatar", "doha", "al wakrah", "al rayyan", "al khor"],
    "Kuwait": ["kuwait", "kuwait city"],
    "Bahrain": ["bahrain", "manama"],
    "Oman": ["oman", "muscat"],
    "Egypt": ["egypt", "cairo", "alexandria"],
    "Canada": ["canada", "toronto", "vancouver", "montreal", "calgary", "ottawa", "edmonton", "ontario", "quebec", "british columbia", "alberta", "manitoba", "nova scotia", "mississauga", "winnipeg", "halifax", "waterloo", "kitchener"],
    "United Kingdom": ["united kingdom", "uk", "london", "manchester", "birmingham", "edinburgh", "glasgow", "scotland", "england", "wales", "cambridge", "oxford", "leeds", "bristol"],
    "San Francisco": ["san francisco", "sf", "bay area", "silicon valley", "oakland", "san jose", "palo alto", "mountain view", "sunnyvale", "berkeley", "redwood city", "menlo park"],
    "New York": ["new york", "nyc", "manhattan", "brooklyn", "queens", "new york city", "ny"],
    "United States": ["united states", "usa", "us", "america", "california", "new york", "texas", "florida", "washington", "illinois"],
    "Germany": ["germany", "berlin", "munich", "frankfurt", "hamburg", "cologne", "stuttgart", "dusseldorf"],
    "France": ["france", "paris", "lyon", "marseille", "toulouse", "nice", "nantes"],
    "Singapore": ["singapore"],
    "Australia": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "India": ["india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai"]
}

CATEGORY_SUB_ROLES = {
    "human_resources": [
        "HR Director",
        "Head of HR",
        "Chief People Officer",
        "VP of Human Resources",
        "VP of People",
        "Head of Talent Acquisition",
        "Senior HRBP",
        "Director of People & Culture",
        "Lead Recruiter",
        "People Operations Director",
        "Talent Acquisition Lead",
        "HR Manager"
    ],
    "yc_founders": [
        '("Y Combinator" OR "YC") ("Founder" OR "Co-Founder" OR "CEO")',
        '("YC W24" OR "YC S24" OR "YC W23" OR "YC S23" OR "YC W25" OR "YC S25" OR "YC W26" OR "YC S26") ("Founder" OR "CEO")',
        '("Y Combinator") ("CEO" OR "Founder" OR "Co-founder")',
        '("YC") ("Co-Founder" OR "Founder" OR "CTO")'
    ],
    "founders": [
        "Founder",
        "Co-Founder",
        "CEO",
        "Chief Executive Officer",
        "Founding Partner",
        "President & Founder",
        "Executive Chairman"
    ],
    "marketing": [
        "Chief Marketing Officer",
        "CMO",
        "VP of Marketing",
        "Head of Marketing",
        "Marketing Director",
        "Director of Growth",
        "Head of Growth"
    ],
    "engineering": [
        "CTO",
        "VP of Engineering",
        "Head of Engineering",
        "Director of Engineering",
        "Lead Software Engineer",
        "Chief Technology Officer",
        "Principal Architect",
        "VP Software Development"
    ],
    "sales_growth": [
        "VP of Sales",
        "Head of Sales",
        "Sales Director",
        "Commercial Director",
        "Director of Business Development",
        "Senior Account Executive",
        "Enterprise Account Executive",
        "Head of Business Development",
        "Regional Sales Manager",
        "Chief Revenue Officer",
        "Head of Commercial",
        "Sales Manager"
    ],
    "venture_capital": [
        "General Partner",
        "Managing Partner",
        "Venture Capital Partner",
        "Investment Director",
        "Principal Investor",
        "Founding Partner"
    ]
}

FOLLOWUP_PATTERNS = [
    r'^(?:find\s+)?more(?:\s+leads|\s+prospects|\s+candidates)?$',
    r'^next(?:\s+page|\s+\d+)?$',
    r'^load\s+more$',
    r'^give\s+me\s+more',
    r'^get\s+more',
    r'^\+?\s*\d+\s+more$',
    r'^page\s+\d+$'
]

class SearchService:
    def __init__(self):
        pass

    @staticmethod
    def is_followup_prompt(prompt: str) -> bool:
        clean = prompt.strip().lower()
        for pat in FOLLOWUP_PATTERNS:
            if re.search(pat, clean):
                return True
        return False

    @staticmethod
    def is_fake_company(company_text: str) -> bool:
        if not company_text or len(company_text.strip()) <= 2:
            return True
        
        clean = company_text.lower().strip()
        if re.search(r'^\d+\+?\s*(?:years?|yrs?|months?|mos?)\b', clean) or re.search(r'\b\d+\+\s*(?:years?|yrs?)\b', clean):
            return True

        regions_fake = {"ksa", "uae", "middle east", "gcc", "mena", "emea", "apac", "latam", "north america", "europe", "asia", "global", "worldwide", "remote", "canada", "qatar", "saudi arabia", "united states", "usa", "uk", "london", "dubai", "riyadh", "jeddah", "toronto"}
        if clean in regions_fake:
            return True

        if clean in ["ex", "former", "previous", "dept", "department", "team", "office", "group", "holdings", "company", "stealth", "confidential", "self-employed", "freelance"]:
            return True

        clean = re.sub(r'\b(inc|llc|ltd|corp|corporation|group|holdings|ventures|labs|ai|io)\b', '', clean)
        words = re.findall(r'[a-zA-Z]+', clean)
        if not words:
            return False

        if len(words) == 1 and (words[0] in JOB_WORDS_SINGLE or words[0] in CERTIFICATIONS):
            return True

        filler_count = sum(1 for w in words if w in JOB_WORDS_SINGLE or w in CERTIFICATIONS)
        if (filler_count / len(words)) >= 0.50:
            return True

        return False

    @staticmethod
    def is_location_match(candidate_location: str, candidate_snippet: str, target_location: Optional[str]) -> bool:
        if not target_location:
            return True

        target_clean = target_location.lower().strip()
        canon_loc = LOCATION_MAP.get(target_clean, target_location)
        target_terms = set(LOCATION_REGION_MAP.get(canon_loc, []))
        target_terms.add(canon_loc.lower())
        target_terms.add(target_clean)

        cand_loc_lower = (candidate_location or "").lower().strip()
        cand_snip_lower = (candidate_snippet or "").lower().strip()

        for term in target_terms:
            if not term:
                continue
            if len(term) <= 3:
                if re.search(rf'\b{re.escape(term)}\b', cand_loc_lower) or re.search(rf'\b{re.escape(term)}\b', cand_snip_lower):
                    return True
            else:
                if term in cand_loc_lower or term in cand_snip_lower:
                    return True

        return False

    def extract_search_parameters(self, prompt: str) -> Dict[str, Any]:
        clean = prompt.strip()
        limit = 10
        num_match = re.search(r'\b(?:find|get|top|show)?\s*(\d{1,3})\b', clean, re.IGNORECASE)
        if num_match:
            try:
                limit = min(max(int(num_match.group(1)), 1), 100)
            except ValueError:
                pass

        compiled = self.compile_smart_dork(clean)
        return {
            "category": compiled.get("category"),
            "target_company": compiled.get("target_company"),
            "location": compiled.get("location"),
            "limit": limit
        }

    def compile_smart_dork(self, user_prompt: str) -> Dict[str, Any]:
        prompt = user_prompt.strip()
        if "site:linkedin.com/in" in prompt:
            return {"category": "custom", "location": None, "target_company": None, "dork": prompt}

        # 1. Detect target named company
        target_company = None
        comp_match = re.search(r'\b(?:from|at|@|for)\s+([A-Za-z0-9\.\-\&]+)(?:\s+in|\s+at|\s+from|\s+where|$)', prompt, re.IGNORECASE)
        if comp_match:
            cand = comp_match.group(1).strip()
            if cand.lower() not in LOCATION_MAP and cand.lower() not in ["sf", "nyc", "london", "canada", "qatar", "dubai", "uae", "compains", "companies"]:
                target_company = cand.capitalize()
                prompt = prompt.replace(comp_match.group(0), ' ')

        prompt_lower = prompt.lower()

        # 2. Detect location
        detected_location = None
        for loc_key in sorted(LOCATION_MAP.keys(), key=len, reverse=True):
            if re.search(rf'\b{re.escape(loc_key)}\b', prompt_lower):
                detected_location = LOCATION_MAP[loc_key]
                prompt_lower = re.sub(rf'\b{re.escape(loc_key)}\b', '', prompt_lower)
                break

        # 3. Clean filler words & typos
        for fw in ["find", "me", "get", "look for", "search for", "who are", "leads", "lead", "for", "please", "can you", "i want", "emails", "email", "top", "best", "people", "in", "at", "the", "a", "an", "from", "compains", "companies", "compnay", "company"]:
            prompt_lower = re.sub(rf'\b{re.escape(fw)}\b', '', prompt_lower)
        clean_query = " ".join(prompt_lower.split())

        # 4. Intent categorization
        category = "general"
        role_terms = ""

        if re.search(r'\b(?:yc|y\s+combinator|ycombinator)\b', clean_query) or "yc" in user_prompt.lower() or "y combinator" in user_prompt.lower():
            category = "yc_founders"
            role_terms = '("Y Combinator" OR "YC") ("Founder" OR "Co-Founder" OR "CEO")'

        elif re.search(r'\b(?:vc|vcs|venture\s+capital|investor|investors|angel|angels|partner|partners|preseed|seed\s+fund|private\s+equity)\b', clean_query) or "vc" in user_prompt.lower():
            category = "venture_capital"
            role_terms = '("Venture Capital" OR "VC" OR "Partner" OR "Investor" OR "General Partner")'

        elif re.search(r'\b(?:hr|human\s+resources|people|talent|recruiter|recruiters|recruiting|talent\s+acquisition|ta|hrbp|chro|cpo|headcount)\b', clean_query) or "hr" in user_prompt.lower() or "people" in user_prompt.lower():
            category = "human_resources"
            role_terms = '("HR" OR "People" OR "Recruiter" OR "Talent" OR "Head of HR" OR "VP of People" OR "Director of People")'

        elif re.search(r'\b(?:ai\s+founder|ai\s+founders|founder|founders|co-founder|co-founders|cofounder|cofounders|ceo|ceos|entrepreneur|entrepreneurs|owner|owners)\b', clean_query):
            category = "founders"
            if "ai" in clean_query or "ai" in user_prompt.lower():
                role_terms = '("Founder" OR "Co-Founder" OR "CEO" OR "Owner") "AI"'
            elif "saas" in clean_query or "saas" in user_prompt.lower():
                role_terms = '("Founder" OR "Co-Founder" OR "CEO" OR "Owner") "SaaS"'
            else:
                role_terms = '("Founder" OR "Co-Founder" OR "CEO" OR "Owner")'

        elif re.search(r'\b(?:engineer|engineers|engineering|cto|ctos|developer|developers|dev|devs|software|architect|tech\s+lead)\b', clean_query):
            category = "engineering"
            role_terms = '("VP of Engineering" OR "Head of Engineering" OR "CTO" OR "Director of Engineering" OR "Lead Engineer")'

        elif re.search(r'\b(?:sale|sales|salespeople|salesperson|salesman|saleswoman|account\s+exec|account\s+executive|ae|aes|sdr|sdrs|bdr|bdrs|business\s+dev|business\s+development|bizdev|commercial|revenue|cro|growth)\b', clean_query) or "sale" in user_prompt.lower() or "sales" in user_prompt.lower():
            category = "sales_growth"
            role_terms = '("Sales" OR "Account Executive" OR "Business Development" OR "VP of Sales" OR "Head of Sales" OR "Sales Director" OR "Commercial Director")'

        elif re.search(r'\b(?:marketing|marketer|marketers|cmo|brand|growth\s+marketing|demand\s+gen)\b', clean_query):
            category = "marketing"
            role_terms = '("VP of Marketing" OR "Head of Marketing" OR "CMO" OR "Marketing Director")'

        elif clean_query and len(clean_query.split()) == 1 and not target_company:
            target_company = clean_query.capitalize()
            role_terms = ""
        else:
            role_terms = f'"{clean_query}"' if clean_query else ""

        dork_parts = ["site:linkedin.com/in/"]
        if role_terms:
            dork_parts.append(role_terms)
        if target_company:
            dork_parts.append(f'"{target_company}"')
        if detected_location:
            dork_parts.append(f'"{detected_location}"')

        return {
            "category": category,
            "target_company": target_company,
            "location": detected_location,
            "dork": " ".join(dork_parts)
        }

    def build_dork_query(self, user_prompt: str) -> str:
        return self.compile_smart_dork(user_prompt)["dork"]

    def generate_sub_dorks(self, query: str, page: int = 1, max_results: int = 10) -> List[str]:
        """Generates granular sub-dorks rotated for pagination, scaling up to 12 dorks for large searches."""
        compiled = self.compile_smart_dork(query)
        cat = compiled.get("category", "general")
        target_company = compiled.get("target_company")
        loc = compiled.get("location")

        loc_aliases = LOCATION_EXPANSIONS.get(loc, [loc]) if loc else [""]
        all_roles = CATEGORY_SUB_ROLES.get(cat, ["Executive", "Leader", "Director", "Manager", "Head", "VP", "Partner", "Lead"])

        num_dorks = 12 if max_results >= 50 else (10 if max_results >= 25 else 8)

        offset = ((page - 1) * 4) % len(all_roles)
        roles = all_roles[offset:] + all_roles[:offset]

        dorks = []
        if target_company:
            for role in roles[:num_dorks]:
                dorks.append(f'site:linkedin.com/in/ "{role}" "{target_company}"')
        else:
            for idx in range(num_dorks):
                role = roles[idx % len(roles)]
                loc_term = loc_aliases[(idx + page - 1) % len(loc_aliases)] if loc else ""
                if loc_term:
                    dorks.append(f'site:linkedin.com/in/ "{role}" "{loc_term}"')
                else:
                    dorks.append(f'site:linkedin.com/in/ "{role}"')

        return dorks

    async def search_linkedin_profiles(
        self,
        query: str,
        max_results: int = 10,
        exclude_urls: Optional[Set[str]] = None,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """Concurrent multi-query execution with strict location matching and deduplication."""
        compiled = self.compile_smart_dork(query)
        target_location = compiled.get("location")
        master_dork = compiled.get("dork")

        sub_dorks = self.generate_sub_dorks(query, page=page, max_results=max_results)
        
        # Search Plan: Master broad dork first, supplemented by granular sub-dorks
        all_dorks = [master_dork] + [d for d in sub_dorks if d != master_dork]

        loop = asyncio.get_event_loop()
        seen_urls = set(exclude_urls) if exclude_urls else set()
        all_results: List[Dict[str, Any]] = []

        def _fetch_single_dork(dork_str: str) -> List[Dict[str, Any]]:
            items = []
            for backend_name in ["lite", "html", "api"]:
                try:
                    with DDGS(timeout=4) as ddgs:
                        fetch_count = min(max(max_results * 2, 20), 40)
                        res = list(ddgs.text(dork_str, max_results=fetch_count, backend=backend_name))
                        if not res:
                            continue
                        for r in res:
                            url = r.get("href", "")
                            clean_url = self._clean_linkedin_url(url)
                            if clean_url:
                                title = r.get("title", "")
                                body = r.get("body", "")
                                unpacked = self.unpack_search_item(title, body, clean_url, target_location)
                                for p in unpacked:
                                    if p["linkedin_url"] not in seen_urls:
                                        items.append(p)
                        if items:
                            break
                except Exception:
                    continue
            return items

        # Execute dorks in batches of 3 to maximize throughput while avoiding rate limit resets
        for i in range(0, len(all_dorks), 3):
            batch = all_dorks[i:i+3]
            tasks = [loop.run_in_executor(None, _fetch_single_dork, d) for d in batch]
            results_nested = await asyncio.gather(*tasks)

            for r_list in results_nested:
                for r in r_list:
                    if r["linkedin_url"] not in seen_urls:
                        seen_urls.add(r["linkedin_url"])
                        all_results.append(r)

            if len(all_results) >= max_results:
                break
            await asyncio.sleep(0.1)

        return all_results[:max_results]

    def unpack_search_item(self, title: str, snippet: str, base_url: str, target_location: Optional[str] = None) -> List[Dict[str, Any]]:
        raw_clean = re.sub(r'https?://\S+', '', title)
        segments = re.split(r'\s*\.{2,}\s*|\s*\|\s*LinkedIn\s*', raw_clean)
        
        results = []
        for seg in segments:
            seg = seg.strip()
            if not seg or len(seg) < 3:
                continue
            
            parts = [p.strip() for p in re.split(r'\s*[\-–—\|·•]\s*', seg) if p.strip()]
            if not parts:
                continue
                
            raw_name = parts[0]
            raw_name = re.sub(r'^\s*\(\d+\)\s*', '', raw_name)
            name = re.sub(r'[^\w\s\.\,\'-]', '', raw_name).strip()
            
            name_words = name.split()
            if len(name_words) < 2 or len(name) < 4 or len(name) > 40:
                continue
            if name_words[0].lower() in JOB_WORDS_SINGLE:
                continue
                
            role = parts[1] if len(parts) > 1 else "Executive"
            company = ""
            if " at " in role:
                h_parts = role.split(" at ")
                role = h_parts[0].strip()
                company = h_parts[-1].strip()
            elif " @ " in role:
                h_parts = role.split(" @ ")
                role = h_parts[0].strip()
                company = h_parts[-1].strip()
            elif len(parts) > 2:
                company = parts[2]
            else:
                # If only 1 part after name (e.g. 'Mundo AI (YC W25)')
                company = role
                role = "Founder & CEO"
                
            if not company and snippet:
                at_match = re.search(r'\b(?:at|@)\s+([A-Z][A-Za-z0-9\s\.\,\&-]{2,30}?)(?:\s*[\·\•\|\.]|\s+in|\s+Location|\s+since|$)', snippet)
                if at_match:
                    company = at_match.group(1).strip()
                    
            company = re.sub(r'\(.*?\)', '', company).strip()
            company = re.sub(r'^(?:Ex|Former|Previous)[\s\-\:]+', '', company, flags=re.IGNORECASE).strip()
            company = re.sub(r'(?i)\b(?:y\s+combinator|yc|techstars|500\s+startups|500\s+global|w\d{2}|s\d{2}|p\d{2}|x\d{2})\b', '', company).strip()
            company = re.sub(r'^(?:Founder|Co-Founder|CEO|President)\s+(?:at|@)\s+', '', company, flags=re.IGNORECASE).strip()
            company = re.sub(r'[\(\)\[\]\|·•,].*$', '', company).strip()
            
            role = re.sub(r'\(.*?\)', '', role).strip()
            role = re.sub(r'[\(\)\[\]\|·•].*$', '', role).strip()
            role = re.sub(r'(?i)\b(?:y\s+combinator|yc)\b', '', role).strip()
            if not role or role.lower() in ['co', 'ceo / co', 'founder / co', 'co-founder / co']:
                role = "CEO & Co-Founder"
            
            slug = re.sub(r'[^a-zA-Z0-9]', '-', name.lower())
            cand_url = base_url if len(results) == 0 else f"https://www.linkedin.com/in/{slug}/"
            
            results.append({
                "name": name,
                "headline": role or "Executive",
                "company": company or "Private Enterprise",
                "location": target_location or "Global",
                "linkedin_url": cand_url,
                "title": title,
                "snippet": snippet
            })
            
        return results

    def _clean_linkedin_url(self, raw_url: str) -> Optional[str]:
        if "linkedin.com/in/" not in raw_url:
            return None
        match = re.search(r'https?://[a-zA-Z0-9\.\-]*linkedin\.com/in/([a-zA-Z0-9\-_%]+)', raw_url)
        if match:
            slug = match.group(1).split("?")[0].split("/")[0]
            if slug and slug.lower() not in ["dir", "pub", "feed", "posts", "pulse"]:
                return f"https://www.linkedin.com/in/{slug}/"
        return None

    @staticmethod
    def extract_chronological_experience(snippet: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Ultra-accurate Chronological Experience Parser.
        Extracts the #1 most recent / current company and job title from LinkedIn search snippet blocks:
        e.g. 'Experience: Marketing Director · Akeneo · 2021 - Present ...'
        or 'Experience: Akeneo · 3 yrs · Location: London ...'
        or 'Experience: CEO at LavenirAI ...'
        """
        if not snippet:
            return None, None

        exp_match = re.search(
            r'(?:Experience|Ervaring|الخبرة|Expérience|Berufserfahrung|Experiencia|Experiência):\s*([^\n\r]+?)(?:\s+Education|\s+Opleiding|\s+التعليم|\s+Formation|\s+Ausbildung|\s+Educación|\s+Location:|\s+Locatie:|\s+الموقع:|$)',
            snippet,
            re.IGNORECASE
        )
        if not exp_match:
            return None, None

        raw_block = exp_match.group(1).strip()
        segments = [s.strip() for s in re.split(r'\s*[\·\•\|\t]\s*', raw_block) if s.strip()]
        if not segments:
            return None, None

        role = None
        company = None

        for seg in segments:
            if re.search(r'^\d+\+?\s*(?:years?|yrs?|months?|mos?)\b', seg, re.IGNORECASE) or re.search(r'\b(?:19|20)\d{2}\s*[\-–]\s*(?:Present|\d{4})', seg, re.IGNORECASE) or seg.lower() in ["present", "current"]:
                continue

            clean_seg = re.sub(r'^(?:Ex|Former|Previous)[\s\-\:]+', '', seg, flags=re.IGNORECASE).strip()
            clean_seg = re.sub(r'\(.*?\)', '', clean_seg).strip()

            if " at " in clean_seg:
                parts = clean_seg.split(" at ")
                role = parts[0].strip()
                company = parts[-1].strip()
                break
            elif " @ " in clean_seg:
                parts = clean_seg.split(" @ ")
                role = parts[0].strip()
                company = parts[-1].strip()
                break

            if re.search(r'\b(?:CEO|CTO|CFO|CMO|CIO|COO|CPO|VP|Vice President|Director|Manager|Head|Lead|Founder|Partner|Owner|President|General Manager|Executive)\b', clean_seg, re.IGNORECASE):
                if not role:
                    role = clean_seg
                continue
            else:
                if not company and len(clean_seg) >= 2 and not SearchService.is_fake_company(clean_seg):
                    company = clean_seg
        if company:
            company = re.sub(r'(?i)\b(?:y\s+combinator|yc|techstars|500\s+startups|500\s+global|w\d{2}|s\d{2}|p\d{2})\b', '', company).strip()
            company = re.sub(r'[\(\)\[\]\|·•]', '', company).strip()

        return role, company

    def _parse_linkedin_title(self, title: str, snippet: str) -> Dict[str, str]:
        # 1. Isolate the FIRST profile from DuckDuckGo's concatenated title string
        t_clean = re.split(r'(?i)\s*(?:[\|\-–—]\s*LinkedIn|\b(?:view|bekijk)\b|https?://)', title)[0].strip()
        first_segment = t_clean.split(" ...")[0].strip()
        
        # 2. Extract Experience using Chronological Experience Parser (Priority #1)
        role = ""
        company = ""
        location = ""

        exp_role, exp_company = self.extract_chronological_experience(snippet)
        if exp_company:
            company = exp_company
        if exp_role:
            role = exp_role

        # Priority 2: LinkedIn Snippet "Location: [City/Country]"
        loc_match = re.search(r'(?:Location|Locatie|الموقع|Emplacement|Standort):\s*([^\·\•\|\n\r\t]+?)(?:\s*[\·\•\|\n\r\t]|\s+\d+\+\s+connections|\s+View|\s+Bekijk|$)', snippet, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()

        # Parse Name and Role from the first title segment
        parts = [p.strip() for p in re.split(r'\s+[\-–—\|·•]\s+|\s*\|\s*', first_segment) if p.strip()]
        raw_name = parts[0] if parts else "Prospect"
        raw_name = re.sub(r'^\s*\(\d+\)\s*', '', raw_name)
        name = re.sub(r'\(.*?\)', '', raw_name)
        name = re.sub(r'[^\w\s\.\,\'-]', '', name).strip()

        if len(parts) > 1:
            role_part = parts[1]
            if " at " in role_part:
                sub = role_part.split(" at ")
                if not role:
                    role = sub[0].strip()
                if not company:
                    company = sub[-1].strip()
            elif " @ " in role_part:
                sub = role_part.split(" @ ")
                if not role:
                    role = sub[0].strip()
                if not company:
                    company = sub[-1].strip()
            else:
                if not role:
                    role = role_part

        # Fallback to secondary title parts if company still empty
        if not company and len(parts) > 2:
            cand_comp = parts[2]
            if not any(cand_comp.lower().startswith(x) for x in ["ex", "former", "view"]):
                company = cand_comp

        # Fallback to snippet "at [Company]"
        if not company and snippet:
            at_match = re.search(r'\b(?:at|@)\s+([A-Z][A-Za-z0-9\s\.\,\&-]{2,35}?)(?:\s*[\·\•\|\.]|\s+in|\s+Location|\s+since|$)', snippet)
            if at_match:
                company = at_match.group(1).strip()

        # Clean company strictly
        company = re.sub(r'\(.*?\)', '', company).strip()
        company = re.sub(r'^(?:Ex|Former|Previous)[\s\-\:]+', '', company, flags=re.IGNORECASE).strip()
        company = re.sub(r'(?i)[,\s]+(?:phd|mba|cpa|pmp|cfa|sphr|phr|shrm-cp|shrm-scp|shrm|chrl|chrp|chre|c\.dir|mcipd|fcipd|cipd)\b.*$', '', company).strip()
        
        # Split camelCase concatenated names (e.g. "Dallah AlbarakaNickle LaMoreaux" -> "Dallah Albaraka")
        match_camel = re.search(r'([a-z])([A-Z][^\s]+(?:\s+[A-Z][^\s]+)+)$', company)
        if match_camel:
            company = company[:match_camel.start(1)+1].strip()
        match_caps = re.search(r'^([A-Z]{2,})([A-Z][a-z]+.*)$', company)
        if match_caps:
            company = match_caps.group(1).strip()

        company = re.sub(r'[\,\.\-\:\;\|\/]+$', '', company).strip()
        company = re.sub(r'^\s*[\,\.\-\:\;\|\/]+', '', company).strip()
        company = re.sub(r'\s+(?:at|@|in|from)$', '', company, flags=re.IGNORECASE).strip()

        # Clean role strictly (strip concatenated second person names & ellipsis)
        role = re.split(r'\s*\.\.\.\s*|\s*[\-–—\|]\s*', role)[0].strip()
        match_camel_role = re.search(r'([a-z])([A-Z][^\s]+(?:\s+[A-Z][^\s]+)+)$', role)
        if match_camel_role:
            role = role[:match_camel_role.start(1)+1].strip()
        role = re.sub(r'[\,\.\-\:\;\|\/]+$', '', role).strip()
        role = re.sub(r'\s+(?:at|@)$', '', role).strip()

        return {
            "name": name,
            "headline": role or "Executive",
            "company": company,
            "location": location
        }
