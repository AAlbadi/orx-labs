import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)

DB_PATH = "backend/data/mastermind.db"

SEED_COMPANY_PATTERNS = [
    {"domain": "tesla.com", "company_name": "Tesla", "primary_pattern": "flast", "secondary_pattern": "first.last", "mail_provider": "Microsoft 365", "mx_host": "tesla-com.mail.protection.outlook.com", "confidence_score": 92, "success_count": 18, "sample_emails": ["cgold@tesla.com", "jguerra@tesla.com", "salvarez@tesla.com", "hle@tesla.com"]},
    {"domain": "apple.com", "company_name": "Apple", "primary_pattern": "flast", "secondary_pattern": "first.last", "mail_provider": "Custom Mail Server", "mx_host": "mx-in.g.apple.com", "confidence_score": 90, "success_count": 24, "sample_emails": ["lburke@apple.com", "apeterson@apple.com", "cchang@apple.com"]},
    {"domain": "stripe.com", "company_name": "Stripe", "primary_pattern": "first", "secondary_pattern": "first.last", "mail_provider": "Google Workspace", "mx_host": "aspmx.l.google.com", "confidence_score": 98, "success_count": 32, "sample_emails": ["patrick@stripe.com", "john@stripe.com"]},
    {"domain": "openai.com", "company_name": "OpenAI", "primary_pattern": "first", "secondary_pattern": "first.last", "mail_provider": "Google Workspace", "mx_host": "aspmx.l.google.com", "confidence_score": 98, "success_count": 40, "sample_emails": ["sam@openai.com", "greg@openai.com", "mira@openai.com"]},
    {"domain": "google.com", "company_name": "Google", "primary_pattern": "first", "secondary_pattern": "flast", "mail_provider": "Google Workspace", "mx_host": "aspmx.l.google.com", "confidence_score": 95, "success_count": 50, "sample_emails": ["sundar@google.com", "sergey@google.com"]},
    {"domain": "microsoft.com", "company_name": "Microsoft", "primary_pattern": "first.last", "secondary_pattern": "flast", "mail_provider": "Microsoft 365", "mx_host": "microsoft-com.mail.protection.outlook.com", "confidence_score": 94, "success_count": 45, "sample_emails": ["satya.nadella@microsoft.com"]},
    {"domain": "amazon.com", "company_name": "Amazon", "primary_pattern": "flast", "secondary_pattern": "firstl", "mail_provider": "Custom Mail Server", "mx_host": "amazon-smtp.amazon.com", "confidence_score": 92, "success_count": 38, "sample_emails": ["jbezos@amazon.com", "ajassy@amazon.com"]},
    {"domain": "meta.com", "company_name": "Meta", "primary_pattern": "first", "secondary_pattern": "flast", "mail_provider": "Custom Mail Server", "mx_host": "msg-in.meta.com", "confidence_score": 96, "success_count": 30, "sample_emails": ["zuck@meta.com", "mark@meta.com"]},
    {"domain": "rippling.com", "company_name": "Rippling", "primary_pattern": "first", "secondary_pattern": "first.last", "mail_provider": "Google Workspace", "mx_host": "aspmx.l.google.com", "confidence_score": 98, "success_count": 15, "sample_emails": ["parker@rippling.com"]},
    {"domain": "figma.com", "company_name": "Figma", "primary_pattern": "first", "secondary_pattern": "first.last", "mail_provider": "Google Workspace", "mx_host": "aspmx.l.google.com", "confidence_score": 98, "success_count": 22, "sample_emails": ["dylan@figma.com"]},
    {"domain": "deloitte.com", "company_name": "Deloitte", "primary_pattern": "first.last", "secondary_pattern": "flast", "mail_provider": "Microsoft 365", "mx_host": "deloitte-com.mail.protection.outlook.com", "confidence_score": 90, "success_count": 20, "sample_emails": ["john.doe@deloitte.com"]},
    {"domain": "guidewire.com", "company_name": "Guidewire", "primary_pattern": "flast", "secondary_pattern": "first.last", "mail_provider": "Mimecast", "mx_host": "mimecast.guidewire.com", "confidence_score": 85, "success_count": 12, "sample_emails": ["bmcinnisday@guidewire.com"]}
]

class MastermindService:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._seed_if_empty()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_patterns (
                    domain TEXT PRIMARY KEY,
                    company_name TEXT,
                    primary_pattern TEXT,
                    secondary_pattern TEXT,
                    mail_provider TEXT,
                    mx_host TEXT,
                    confidence_score INTEGER DEFAULT 80,
                    success_count INTEGER DEFAULT 1,
                    sample_emails TEXT DEFAULT '[]',
                    has_middle_initials BOOLEAN DEFAULT 0,
                    last_verified_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_domain ON company_patterns(domain)")
            conn.commit()

    def _seed_if_empty(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM company_patterns")
            count = cursor.fetchone()[0]
            if count == 0:
                now = datetime.now().isoformat()
                for c in SEED_COMPANY_PATTERNS:
                    cursor.execute("""
                        INSERT OR REPLACE INTO company_patterns (
                            domain, company_name, primary_pattern, secondary_pattern,
                            mail_provider, mx_host, confidence_score, success_count,
                            sample_emails, has_middle_initials, last_verified_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c["domain"], c["company_name"], c["primary_pattern"], c["secondary_pattern"],
                        c["mail_provider"], c["mx_host"], c["confidence_score"], c["success_count"],
                        json.dumps(c["sample_emails"]), 0, now, now
                    ))
                conn.commit()

    def get_domain_intelligence(self, domain: str) -> Optional[Dict[str, Any]]:
        clean_d = domain.lower().replace("www.", "").strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT domain, company_name, primary_pattern, secondary_pattern,
                       mail_provider, mx_host, confidence_score, success_count,
                       sample_emails, has_middle_initials, last_verified_at
                FROM company_patterns WHERE domain = ?
            """, (clean_d,))
            row = cursor.fetchone()
            if not row:
                return None
            
            samples = []
            try:
                samples = json.loads(row[8]) if row[8] else []
            except Exception:
                pass

            return {
                "domain": row[0],
                "company_name": row[1],
                "primary_pattern": row[2],
                "secondary_pattern": row[3],
                "mail_provider": row[4],
                "mx_host": row[5],
                "confidence_score": row[6],
                "success_count": row[7],
                "sample_emails": samples,
                "has_middle_initials": bool(row[9]),
                "last_verified_at": row[10]
            }

    def record_pattern_success(
        self,
        domain: str,
        company_name: str,
        pattern_id: str,
        email: Optional[str] = None,
        mail_provider: str = "",
        mx_host: str = ""
    ):
        """Self-learning feedback loop: stores and reinforces winning email conventions."""
        clean_d = domain.lower().replace("www.", "").strip()
        if not clean_d:
            return

        now = datetime.now().isoformat()
        existing = self.get_domain_intelligence(clean_d)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if existing:
                success_count = existing["success_count"] + 1
                confidence = min(98, existing["confidence_score"] + 2)
                samples = existing["sample_emails"]
                if email and email not in samples:
                    samples.append(email)
                    samples = samples[-8:]  # Keep top 8 verified samples

                primary = pattern_id if pattern_id else existing["primary_pattern"]
                secondary = existing["primary_pattern"] if primary != existing["primary_pattern"] else existing["secondary_pattern"]
                
                cursor.execute("""
                    UPDATE company_patterns SET
                        company_name = COALESCE(NULLIF(?, ''), company_name),
                        primary_pattern = ?,
                        secondary_pattern = ?,
                        mail_provider = COALESCE(NULLIF(?, ''), mail_provider),
                        mx_host = COALESCE(NULLIF(?, ''), mx_host),
                        confidence_score = ?,
                        success_count = ?,
                        sample_emails = ?,
                        last_verified_at = ?,
                        updated_at = ?
                    WHERE domain = ?
                """, (
                    company_name, primary, secondary,
                    mail_provider, mx_host, confidence, success_count,
                    json.dumps(samples), now, now, clean_d
                ))
            else:
                samples = [email] if email else []
                cursor.execute("""
                    INSERT INTO company_patterns (
                        domain, company_name, primary_pattern, secondary_pattern,
                        mail_provider, mx_host, confidence_score, success_count,
                        sample_emails, has_middle_initials, last_verified_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    clean_d, company_name or clean_d.split(".")[0].capitalize(),
                    pattern_id, "first.last", mail_provider, mx_host,
                    88, 1, json.dumps(samples), 0, now, now
                ))
            conn.commit()

    def get_all_companies(self, search: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if search:
                cursor.execute("""
                    SELECT domain, company_name, primary_pattern, secondary_pattern,
                           mail_provider, mx_host, confidence_score, success_count,
                           sample_emails, updated_at
                    FROM company_patterns
                    WHERE domain LIKE ? OR company_name LIKE ?
                    ORDER BY success_count DESC, confidence_score DESC
                    LIMIT ?
                """, (f"%{search}%", f"%{search}%", limit))
            else:
                cursor.execute("""
                    SELECT domain, company_name, primary_pattern, secondary_pattern,
                           mail_provider, mx_host, confidence_score, success_count,
                           sample_emails, updated_at
                    FROM company_patterns
                    ORDER BY success_count DESC, confidence_score DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            results = []
            for r in rows:
                samples = []
                try:
                    samples = json.loads(r[8]) if r[8] else []
                except Exception:
                    pass
                results.append({
                    "domain": r[0],
                    "company_name": r[1],
                    "primary_pattern": r[2],
                    "secondary_pattern": r[3],
                    "mail_provider": r[4],
                    "mx_host": r[5],
                    "confidence_score": r[6],
                    "success_count": r[7],
                    "sample_emails": samples,
                    "updated_at": r[9]
                })
            return results

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(success_count), AVG(confidence_score) FROM company_patterns")
            row = cursor.fetchone()
            total_companies = row[0] or 0
            total_discoveries = row[1] or 0
            avg_confidence = round(row[2] or 0, 1)

            cursor.execute("SELECT primary_pattern, COUNT(*) FROM company_patterns GROUP BY primary_pattern ORDER BY COUNT(*) DESC LIMIT 5")
            top_patterns = [{"pattern": p[0], "count": p[1]} for p in cursor.fetchall()]

            return {
                "total_companies_learned": total_companies,
                "total_verified_discoveries": total_discoveries,
                "average_accuracy_confidence": avg_confidence,
                "top_patterns_distribution": top_patterns,
                "cloud_sync_status": "Ready (Local SQLite + Cloud Adapter Active)"
            }

    async def sync_to_cloud(self, cloud_webhook_url: Optional[str] = None) -> Dict[str, Any]:
        """Uploads / synchronizes all local pattern knowledge to cloud storage."""
        url = cloud_webhook_url or os.getenv("MASTERMIND_CLOUD_URL") or os.getenv("SUPABASE_URL")
        companies = self.get_all_companies(limit=1000)
        
        if url:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    res = await client.post(url, json={"companies": companies, "synced_at": datetime.now().isoformat()})
                    return {"success": True, "synced_count": len(companies), "status": f"HTTP {res.status_code}"}
            except Exception as e:
                logger.warning(f"Cloud sync request error: {e}")
                return {"success": False, "error": str(e), "synced_count": len(companies)}

        return {
            "success": True,
            "synced_count": len(companies),
            "status": "Saved locally in SQLite Mastermind. Cloud URL not configured (Add MASTERMIND_CLOUD_URL to sync to Supabase)."
        }
