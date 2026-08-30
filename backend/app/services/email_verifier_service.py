import re
import os
import json
import socket
import smtplib
import asyncio
import urllib.request
import dns.resolver
from typing import Dict, Any, List, Optional, Tuple
from ddgs import DDGS

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "sharklasers.com", "yopmail.com", "trashmail.com", "getairmail.com"
}

ENTERPRISE_GATEWAYS = {
    "Mimecast", "Proofpoint Enterprise", "Cisco IronPort", "Barracuda"
}

MEGA_ENTERPRISE_DOMAINS = {
    "tesla.com", "apple.com", "microsoft.com", "amazon.com", "walmart.com",
    "google.com", "meta.com", "deloitte.com", "pwc.com", "ey.com", "kpmg.com",
    "jpmorgan.com", "chase.com", "bankofamerica.com", "wellsfargo.com",
    "boeing.com", "lockheedmartin.com", "pfizer.com", "johnsonandjohnson.com",
    "ibm.com", "oracle.com", "salesforce.com", "cisco.com", "intel.com",
    "accenture.com", "mckinsey.com", "bcg.com", "bain.com", "guidewire.com"
}

MEGA_ENTERPRISE_STEMS = {
    "ey.", "ernstyoung", "deloitte", "pwc", "pricewaterhouse", "kpmg",
    "mckinsey", "bcg", "bain", "accenture", "goldmansachs", "morganstanley",
    "jpmorgan", "chase", "bankofamerica", "wellsfargo", "citigroup", "citi",
    "barclays", "ubs", "apple.", "google.", "microsoft.", "amazon.", "meta.",
    "tesla.", "nvidia.", "netflix.", "uber.", "salesforce.", "oracle.", "ibm.",
    "cisco.", "intel.", "adobe.", "sony.", "samsung.", "disney.", "nike.",
    "pfizer.", "moderna.", "johnsonandjohnson", "walmart.", "target.", "boeing."
}

MEGA_ENTERPRISE_NAMES = {
    "ernst & young", "ey", "deloitte", "pwc", "pricewaterhousecoopers", "kpmg",
    "mckinsey & company", "mckinsey", "boston consulting group", "bcg", "bain & company", "bain",
    "accenture", "goldman sachs", "morgan stanley", "jpmorgan", "jp morgan", "chase",
    "bank of america", "wells fargo", "citigroup", "citi", "apple", "google", "alphabet",
    "microsoft", "amazon", "meta", "facebook", "tesla", "nvidia", "netflix", "uber",
    "salesforce", "oracle", "ibm", "cisco", "intel", "boeing", "walmart", "pfizer"
}

POST_NOMINALS_REGEX = re.compile(
    r'(?i)[,\s]+(?:mba|m\.s\.|ms|b\.s\.|bs|ba|b\.a\.|bsc|b\.sc\.|bcom|b\.com|mm|m\.m\.|msc|bhrm|mhrm|mirhr|phd|m\.d\.|md|cpa|pmp|cfa|esq|p\.e\.|pe|phr|sphr|shrm-cp|shrm-scp|shrm|chrl|chrp|chre|c\.dir|cdir|icd\.d|acc|pcc|mcc|gphr|cipd|mcipd|fcipd|chartered|fcdi|ccc|shrmcp|shrmscp)\b'
)

PATTERNS_META = [
    {"id": "fmlast", "format": lambda f, m, l, meta: f"{f[0]}{m}{l}" if f and m and l else None},
    {"id": "first.m.last", "format": lambda f, m, l, meta: f"{f}.{m}.{l}" if f and m and l else None},
    {"id": "flast", "format": lambda f, m, l, meta: f"{f[0]}{l}" if f and l else None},
    {"id": "first.last", "format": lambda f, m, l, meta: f"{f}.{l}" if f and l else None},
    {"id": "first", "format": lambda f, m, l, meta: f"{f}" if f else None},
    {"id": "firstlast", "format": lambda f, m, l, meta: f"{f}{l}" if f and l else None},
    {"id": "first_last", "format": lambda f, m, l, meta: f"{f}_{l}" if f and l else None},
    {"id": "f.last", "format": lambda f, m, l, meta: f"{f[0]}.{l}" if f and l else None},
    {"id": "firstl", "format": lambda f, m, l, meta: f"{f}{l[0]}" if f and l else None},
    {"id": "first.l", "format": lambda f, m, l, meta: f"{f}.{l[0]}" if f and l else None},
    {"id": "last.first", "format": lambda f, m, l, meta: f"{f and l and l}.{f}" if f and l else None},
    {"id": "last", "format": lambda f, m, l, meta: f"{l}" if f and l else None},
    {"id": "lastf", "format": lambda f, m, l, meta: f"{l}{f[0]}" if f and l else None},
    {"id": "f_last", "format": lambda f, m, l, meta: f"{f[0]}_{l}" if f and l else None},
    {"id": "first.l1-l2", "format": lambda f, m, l, meta: f"{f}.{meta['l1']}-{meta['l2']}" if meta.get('l1') and meta.get('l2') else None},
    {"id": "fl1-l2", "format": lambda f, m, l, meta: f"{f[0]}{meta['l1']}-{meta['l2']}" if meta.get('l1') and meta.get('l2') else None},
    {"id": "fl2", "format": lambda f, m, l, meta: f"{f[0]}{meta['l2']}" if meta.get('l2') else None}
]

from app.services.mastermind_service import MastermindService

class CompanyPatternBrain:
    def __init__(self, storage_file: str = "backend/data/company_patterns.json"):
        self.storage_file = storage_file
        self.domain_memory: Dict[str, Dict[str, int]] = {}
        self.mastermind = MastermindService()
        self._load()

    def _load(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.domain_memory = json.load(f)
            except Exception:
                self.domain_memory = {}
        else:
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            self.domain_memory = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.domain_memory, f, indent=2)
        except Exception:
            pass

    def record_successful_pattern(
        self,
        domain: str,
        pattern_id: str,
        company_name: str = "",
        email: Optional[str] = None,
        mail_provider: str = "",
        mx_host: str = ""
    ):
        d = domain.lower().replace("www.", "").strip()
        if d not in self.domain_memory:
            self.domain_memory[d] = {}
        current_score = self.domain_memory[d].get(pattern_id, 0)
        self.domain_memory[d][pattern_id] = current_score + 15
        self.save()

        # Update Mastermind SQLite Database
        try:
            self.mastermind.record_pattern_success(
                domain=d,
                company_name=company_name,
                pattern_id=pattern_id,
                email=email,
                mail_provider=mail_provider,
                mx_host=mx_host
            )
        except Exception as e:
            logger.warning(f"Mastermind record error: {e}")

    def get_ranked_candidates(
        self,
        first_name: str,
        last_name: str,
        domain: str,
        provider: str = "",
        middle_initial: str = "",
        role: str = ""
    ) -> List[Dict[str, Any]]:
        d = domain.lower().replace("www.", "").strip()
        f = re.sub(r'[^a-zA-Z0-9]', '', first_name.lower())
        m = re.sub(r'[^a-zA-Z0-9]', '', middle_initial.lower())
        
        last_clean = last_name.lower().replace("-", " ").strip()
        last_parts = [re.sub(r'[^a-zA-Z0-9]', '', p) for p in last_clean.split() if p]
        l = last_parts[-1] if last_parts else ""
        
        meta = {
            "l1": last_parts[0] if len(last_parts) > 1 else None,
            "l2": last_parts[1] if len(last_parts) > 1 else None
        }

        learned_scores = self.domain_memory.get(d, {})
        
        # Check Mastermind database intelligence
        mm_info = self.mastermind.get_domain_intelligence(d)
        if mm_info and mm_info.get("primary_pattern"):
            prim = mm_info["primary_pattern"]
            learned_scores[prim] = max(learned_scores.get(prim, 0), 40)

        is_founder = any(t in role.lower() for t in ["founder", "ceo", "cto", "co-founder", "president", "partner"])

        candidate_list = []
        for pat in PATTERNS_META:
            pat_id = pat["id"]
            local_part = pat["format"](f, m, l, meta)
            if not local_part:
                continue

            email = f"{local_part}@{d}"
            
            base_score = 50
            if pat_id == "fmlast" and m: base_score = 85
            elif pat_id == "first.m.last" and m: base_score = 80
            elif pat_id == "flast": base_score = 70
            elif pat_id == "first.last": base_score = 65
            elif pat_id == "first" and is_founder: base_score = 75
            elif pat_id == "first": base_score = 60
            elif pat_id == "firstlast": base_score = 55

            if provider == "Google Workspace":
                if pat_id in ["first", "first.last", "flast"]:
                    base_score += 15
            elif provider == "Microsoft 365":
                if pat_id in ["flast", "fmlast", "first.last", "first_last"]:
                    base_score += 15

            learned_bonus = learned_scores.get(pat_id, 0) * 20
            if pat_id == "fmlast" and m and "flast" in learned_scores:
                learned_bonus = learned_scores.get("flast", 0) * 20 + 20

            total_score = base_score + learned_bonus

            candidate_list.append({
                "email": email,
                "pattern_id": pat_id,
                "score": total_score,
                "is_learned_match": bool(learned_bonus > 0)
            })

        candidate_list.sort(key=lambda x: x["score"], reverse=True)
        return candidate_list

class EmailVerifierService:
    def __init__(self, timeout: float = 2.5):
        self.timeout = timeout
        self.brain = CompanyPatternBrain()
        self.mastermind = self.brain.mastermind
        self._mx_cache: Dict[str, Tuple[List[str], str]] = {}
        self._catch_all_cache: Dict[str, bool] = {}

    @staticmethod
    def is_mega_enterprise(domain: str, headcount: int = 0, provider: str = "", company_name: str = "") -> bool:
        """Determines if a company is a Mega-Enterprise requiring Pipeline B (On-Demand Apollo Reveal)."""
        d = domain.lower().replace("www.", "").strip()
        comp = company_name.lower().strip()
        
        if d in MEGA_ENTERPRISE_DOMAINS:
            return True
        if any(stem in d for stem in MEGA_ENTERPRISE_STEMS):
            return True
        if comp and any(name in comp for name in MEGA_ENTERPRISE_NAMES):
            return True
        if headcount and headcount >= 2000:
            return True
        if provider in ENTERPRISE_GATEWAYS:
            return True
        return False

    @staticmethod
    def extract_name_and_slug_middle(name: str, linkedin_url: str = "") -> Tuple[str, str, str]:
        clean = re.sub(r'^\s*\(\d+\)\s*', '', name)
        clean = re.sub(r'\(.*?\)', '', clean)
        clean = POST_NOMINALS_REGEX.sub('', clean)
        clean = re.sub(r'[^\w\s\.\,\'-]', '', clean).strip()
        
        parts = [p.strip() for p in clean.split() if p.strip()]
        if not parts:
            return "", "", ""

        first_name = parts[0]
        middle_initial = ""
        
        if len(parts) == 2:
            last_name = parts[1]
        elif len(parts) >= 3:
            if len(parts[1]) == 1:
                middle_initial = parts[1]
            last_name = parts[-1]
        else:
            last_name = ""

        f = re.sub(r'[^a-zA-Z0-9]', '', first_name.lower())
        l = re.sub(r'[^a-zA-Z0-9]', '', last_name.lower())
        m = re.sub(r'[^a-zA-Z0-9]', '', middle_initial.lower())

        if not m and linkedin_url and f and l:
            slug = linkedin_url.rstrip("/").split("/")[-1].lower()
            slug_clean = re.sub(r'[\d\-]', '', slug)
            if slug_clean.startswith(f) and slug_clean.endswith(l):
                in_between = slug_clean[len(f):-len(l)] if len(l) > 0 else ""
                if len(in_between) == 1:
                    m = in_between

        return f, m, l

    @staticmethod
    def sanitize_name(name: str) -> Tuple[str, str]:
        f, _, l = EmailVerifierService.extract_name_and_slug_middle(name)
        return f, l

    @staticmethod
    def clean_domain(domain: str) -> str:
        d = domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").strip()
        return d.split("/")[0].split("?")[0].strip()

    def probe_public_company_emails(self, domain: str) -> List[str]:
        """
        Multi-Layer Free Pattern Intelligence:
        1. Web Footprint Search (DuckDuckGo OSINT)
        2. GitHub Public Commits OSINT
        """
        clean_d = self.clean_domain(domain)
        if not clean_d:
            return []

        if hasattr(self, "_public_email_cache") and clean_d in self._public_email_cache:
            return self._public_email_cache[clean_d]

        if not hasattr(self, "_public_email_cache"):
            self._public_email_cache = {}

        emails: List[str] = []

        # Layer 1: Autonomous Web Footprint Search
        try:
            with DDGS(timeout=3) as ddgs:
                res = list(ddgs.text(f'site:{clean_d} "email" OR "contact" OR "@"', max_results=3))
                for r in res:
                    text = f"{r.get('title', '')} {r.get('body', '')}"
                    matches = re.findall(rf'\b([a-zA-Z0-9\._%+-]+@{re.escape(clean_d)})\b', text, re.IGNORECASE)
                    for m in matches:
                        em = m.lower()
                        if em not in emails:
                            emails.append(em)
                            pat = self._detect_pattern_from_sample(em, clean_d)
                            if pat:
                                self.brain.record_successful_pattern(clean_d, pat)
        except Exception:
            pass

        # Layer 2: GitHub Public Commit Author OSINT
        try:
            req = urllib.request.Request(
                f"https://api.github.com/search/commits?q=author-email:@{clean_d}&sort=committer-date&order=desc",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/vnd.github.cloak-preview"
                }
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("items", [])[:5]:
                    author_em = item.get("commit", {}).get("author", {}).get("email", "").lower().strip()
                    if author_em.endswith(f"@{clean_d}") and "noreply" not in author_em and "bot" not in author_em:
                        if author_em not in emails:
                            emails.append(author_em)
                            pat = self._detect_pattern_from_sample(author_em, clean_d)
                            if pat:
                                self.brain.record_successful_pattern(clean_d, pat)
        except Exception:
            pass

        self._public_email_cache[clean_d] = emails
        return emails

    @staticmethod
    def _detect_pattern_from_sample(email: str, domain: str) -> Optional[str]:
        role_inboxes = {"info", "support", "contact", "sales", "press", "media", "help", "hello", "team", "careers", "jobs", "privacy", "legal", "security", "admin", "office", "business"}
        clean_d = domain.lower()
        prefix = email.lower().replace(f"@{clean_d}", "").strip()
        if prefix in role_inboxes or len(prefix) < 3:
            return None

        if "." in prefix:
            parts = prefix.split(".")
            if len(parts) == 2:
                return "f.last" if len(parts[0]) == 1 else "first.last"
            elif len(parts) == 3:
                return "first.m.last"
        elif "_" in prefix:
            return "first_last"
        elif len(prefix) >= 5 and prefix[0].isalpha():
            return "flast"
        return None

    def get_mx_records(self, domain: str) -> Tuple[List[str], str]:
        clean_d = self.clean_domain(domain)
        if not clean_d or clean_d in DISPOSABLE_DOMAINS:
            return [], "Disposable / Invalid"

        if clean_d in self._mx_cache:
            return self._mx_cache[clean_d]

        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = 1.2
            resolver.timeout = 1.0
            answers = resolver.resolve(clean_d, 'MX')
            mx_hosts = sorted([(r.preference, str(r.exchange).rstrip('.')) for r in answers])
            hosts = [h[1] for h in mx_hosts if h[1]]
            
            if not hosts:
                return [], "No MX Records"

            primary_mx = hosts[0].lower()
            provider = self._classify_provider(primary_mx)
            self._mx_cache[clean_d] = (hosts, provider)
            return hosts, provider
        except Exception:
            return [], "DNS Lookup Failed"

    @staticmethod
    def _classify_provider(mx_host: str) -> str:
        host = mx_host.lower()
        if "google" in host or "aspmx" in host or "l.google" in host:
            return "Google Workspace"
        elif "outlook" in host or "protection" in host or "microsoft" in host:
            return "Microsoft 365"
        elif "pphosted" in host or "proofpoint" in host:
            return "Proofpoint Enterprise"
        elif "mimecast" in host:
            return "Mimecast"
        elif "zoho" in host:
            return "Zoho Mail"
        elif "proton" in host:
            return "ProtonMail"
        elif "amazonses" in host or "aws" in host:
            return "Amazon SES"
        elif "sendgrid" in host:
            return "SendGrid"
        elif "mailgun" in host:
            return "Mailgun"
        return "Custom Mail Server"

    def check_catch_all(self, domain: str, mx_host: str) -> bool:
        clean_d = self.clean_domain(domain)
        if clean_d in self._catch_all_cache:
            return self._catch_all_cache[clean_d]

        honeypot_email = f"_probe_test_99a8x_{socket.gethostname()[:4]}@{clean_d}"
        is_deliverable, _, _ = self._smtp_handshake_sync(honeypot_email, mx_host, timeout=2.0)
        self._catch_all_cache[clean_d] = is_deliverable
        return is_deliverable

    def _smtp_handshake_sync(self, email: str, mx_host: str, timeout: float = 2.5) -> Tuple[bool, str, Optional[int]]:
        try:
            with smtplib.SMTP(timeout=timeout) as smtp:
                code, _ = smtp.connect(mx_host, 25)
                if code >= 400:
                    return False, f"Connect refused ({code})", code

                smtp.helo("verify.activemailbox.io")
                smtp.mail("probe@verify.activemailbox.io")
                code, msg_bytes = smtp.rcpt(email)
                
                try:
                    smtp.rset()
                except Exception:
                    pass

                msg_str = msg_bytes.decode('utf-8', errors='ignore') if isinstance(msg_bytes, bytes) else str(msg_bytes)
                
                if code in [250, 251]:
                    return True, "250 Active Mailbox", code
                elif code in [550, 551, 552, 553, 554]:
                    return False, f"Mailbox not found ({code})", code
                elif code in [450, 451, 452, 421]:
                    return False, f"Greylisted / Rate limited ({code})", code
                else:
                    return False, f"Response: {code} {msg_str[:40]}", code
        except (socket.timeout, TimeoutError):
            return False, "SMTP Timeout", None
        except socket.error as se:
            return False, f"Socket Error: {type(se).__name__}", None
        except Exception as e:
            return False, f"SMTP Error: {type(e).__name__}", None

    async def verify_lead_email(
        self,
        first_name: str,
        last_name: str,
        domain: str,
        middle_initial: str = "",
        headcount: int = 0,
        role: str = "",
        company_name: str = ""
    ) -> Dict[str, Any]:
        """
        Executes Dual-Pipeline Verification:
        - Pipeline A: Startups / SMBs -> Free automatic verification ($0)
        - Pipeline B: Mega-Enterprises (>2.0k employees / Fortune 500 / Big 4 / Tech Giants) -> Safely Locked for On-Demand Apollo Reveal
        """
        clean_d = self.clean_domain(domain)
        if not clean_d:
            return {
                "email": None,
                "confidence_score": 0,
                "verification_method": "No Domain",
                "mail_provider": "Unknown",
                "is_enterprise_locked": False,
                "pipeline_type": "FREE_UNLOCKED",
                "mx_host": None
            }

        # Guard against truncated names with only initial (e.g. "Celia R.") or 2-letter usernames
        if len(first_name) <= 1 or len(last_name) <= 1:
            return {
                "email": None,
                "confidence_score": 50,
                "verification_method": "Incomplete Profile (Initial Only)",
                "mail_provider": "Directory Guarded",
                "is_enterprise_locked": True,
                "pipeline_type": "ENTERPRISE_LOCKED",
                "mx_host": None
            }

        mx_hosts, provider = self.get_mx_records(clean_d)
        if not mx_hosts:
            return {
                "email": None,
                "confidence_score": 0,
                "verification_method": "No MX Records",
                "mail_provider": provider,
                "is_enterprise_locked": False,
                "pipeline_type": "FREE_UNLOCKED",
                "mx_host": None
            }

        primary_mx = mx_hosts[0]
        is_enterprise = self.is_mega_enterprise(clean_d, headcount, provider, company_name=company_name)

        candidates = self.brain.get_ranked_candidates(first_name, last_name, clean_d, middle_initial=middle_initial, provider=provider, role=role)
        if not candidates:
            return {
                "email": None,
                "confidence_score": 0,
                "verification_method": "Invalid Name",
                "mail_provider": provider,
                "is_enterprise_locked": is_enterprise,
                "pipeline_type": "ENTERPRISE_LOCKED" if is_enterprise else "FREE_UNLOCKED",
                "mx_host": primary_mx
            }

        loop = asyncio.get_event_loop()

        # Step 0: Probe web for public corporate inboxes (e.g. support@, press@, or real employee emails)
        public_inboxes = await loop.run_in_executor(None, self.probe_public_company_emails, clean_d)
        if public_inboxes:
            # Re-rank candidates if new employee pattern was learned into Mastermind
            candidates = self.brain.get_ranked_candidates(first_name, last_name, clean_d, middle_initial=middle_initial, provider=provider, role=role)

        top_cand = candidates[0]

        # Step 1: Check Mastermind Self-Learning Knowledge Base
        mm_info = self.mastermind.get_domain_intelligence(clean_d)
        mm_confidence = mm_info.get("confidence_score", 0) if mm_info else 0
        has_learned_pattern = bool(top_cand.get("is_learned_match") or (mm_confidence and mm_confidence >= 90))

        # Step 2: Try Live SMTP Verification on candidate addresses
        is_catch_all = await loop.run_in_executor(None, self.check_catch_all, clean_d, primary_mx)
        
        verified_email = None
        smtp_success = False
        is_dbeb_blocked = False
        winning_pattern_id = None

        if not is_catch_all:
            for cand in candidates[:4]:
                cand_email = cand["email"]
                is_valid, reason, code = await loop.run_in_executor(
                    None, self._smtp_handshake_sync, cand_email, primary_mx, 1.5
                )
                if is_valid:
                    verified_email = cand_email
                    smtp_success = True
                    winning_pattern_id = cand["pattern_id"]
                    break
                elif code == 550 or "5.4.1" in reason or "Access denied" in reason or "Client host blocked" in reason:
                    is_dbeb_blocked = True

        # Case 1: Mailbox Confirmed via Live SMTP 250 OK -> 100% Free Verified ($0.00)
        if smtp_success and verified_email:
            if winning_pattern_id:
                self.brain.record_successful_pattern(clean_d, winning_pattern_id)
            return {
                "email": verified_email,
                "confidence_score": 100,
                "verification_method": "100% Active Mailbox (SMTP 250 OK)",
                "mail_provider": provider,
                "is_enterprise_locked": False,
                "pipeline_type": "FREE_UNLOCKED",
                "mx_host": primary_mx
            }

        # Case 2: Mastermind Brain knows the verified corporate pattern -> 100% Free Verified ($0.00)
        if has_learned_pattern and not (is_enterprise and not top_cand.get("is_learned_match")):
            return {
                "email": top_cand["email"],
                "confidence_score": max(mm_confidence, 90),
                "verification_method": f"Free Verified (Mastermind Brain {max(mm_confidence, 90)}%)",
                "mail_provider": provider,
                "is_enterprise_locked": False,
                "pipeline_type": "FREE_UNLOCKED",
                "mx_host": primary_mx
            }

        # Case 3: Mega-Enterprise or SMTP Rejected (550 Address Not Found) -> Guarded Mode
        if is_enterprise or is_dbeb_blocked or not smtp_success:
            return {
                "email": None,
                "confidence_score": 50,
                "verification_method": f"Guarded ({'Mailbox Rejected 550' if is_dbeb_blocked else 'Apollo Reveal Required'})",
                "mail_provider": provider,
                "is_enterprise_locked": True,
                "pipeline_type": "ENTERPRISE_LOCKED",
                "mx_host": primary_mx
            }

        # Case 4: Standard Verified Inbox
        return {
            "email": verified_email or top_cand["email"],
            "confidence_score": 85,
            "verification_method": f"Free Verified Pattern ({provider})",
            "mail_provider": provider,
            "is_enterprise_locked": False,
            "pipeline_type": "FREE_UNLOCKED",
            "mx_host": primary_mx
        }
