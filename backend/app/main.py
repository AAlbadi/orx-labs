import io
import csv
import logging
import os
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.models.lead import (
    Lead, SearchRequest, VerifyKeyRequest, LeadStatus
)
from app.core.agent import LeadFinderAgent
from app.services.apollo_api_service import ApolloApiService
from app.services.email_verifier_service import EmailVerifierService
from app.services.llm_query_service import LlmQueryService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Apollo Lead Intelligence API",
    description="2026 AI-Powered Dual-Pipeline Lead Finder with Free/Enterprise Cost Control",
    version="2.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = LeadFinderAgent()
apollo_service = ApolloApiService()
verifier = EmailVerifierService()
llm_service = LlmQueryService()

@app.get("/")
async def root():
    return {
        "service": "LeadsHunter Autonomous Lead Intelligence API",
        "status": "online",
        "docs_url": "/docs",
        "health_check": "/api/status"
    }

@app.get("/api/status")
async def get_status():
    """System health check, Apollo API status, and LLM status."""
    api_key = os.getenv("APOLLO_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    return {
        "status": "online",
        "version": "2.4.0-ultra-fast",
        "has_apollo_key": bool(api_key),
        "has_gemini_key": bool(gemini_key),
        "engine": "Dual-Pipeline Engine (100% Free SMB / On-Demand Apollo Enterprise Guard)",
        "optimizations": "DNS 1.0s timeout + in-memory TLD heuristic"
    }

@app.get("/api/mastermind/stats")
async def get_mastermind_stats():
    """Returns self-learning Mastermind intelligence metrics and pattern distributions."""
    return verifier.mastermind.get_stats()

@app.get("/api/mastermind/domains")
async def get_mastermind_domains(search: str = "", limit: int = 100):
    """Lists learned company email patterns from Mastermind SQLite knowledge base."""
    return {"companies": verifier.mastermind.get_all_companies(search=search, limit=limit)}

@app.post("/api/mastermind/sync-cloud")
async def sync_mastermind_cloud(payload: Dict[str, Any] = Body(default={})):
    """Triggers background cloud sync with Supabase / PostgreSQL / REST adapter."""
    cloud_url = payload.get("cloud_url")
    return await verifier.mastermind.sync_to_cloud(cloud_url)

@app.post("/api/apollo/verify-key")
async def verify_apollo_key(payload: VerifyKeyRequest):
    """Verifies Apollo.io API Key via Apollo health check endpoint."""
    res = await apollo_service.verify_api_key(payload.api_key)
    return res

@app.post("/api/search/stream")
async def search_leads_stream(request: SearchRequest):
    """Streams leads through the Dual-Pipeline Router via Server-Sent Events (SSE)."""
    return StreamingResponse(
        agent.run(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/unlock-lead")
async def unlock_lead(payload: Dict[str, Any]):
    """
    On-Demand Enterprise Reveal:
    Triggered when user clicks 'Reveal via Apollo API' on an Enterprise Guarded lead.
    1. Calls Apollo /v1/people/match (1 credit on paid plan).
    2. Fallback to candidate email pattern if Apollo match is restricted.
    """
    name = payload.get("name", "")
    company = payload.get("company", "")
    linkedin_url = payload.get("linkedin_url", "")
    meta = payload.get("meta", {})
    api_key = payload.get("api_key") or os.getenv("APOLLO_API_KEY")

    first_name, middle_initial, last_name = verifier.extract_name_and_slug_middle(name, linkedin_url)

    email = None
    phone = None
    method = "Apollo Database Match"
    confidence = 98

    # 1. Try Direct Apollo Database Match
    if api_key:
        apollo_match = await apollo_service.match_and_enrich_single(
            name=name,
            company=company,
            linkedin_url=linkedin_url,
            api_key=api_key
        )

        if apollo_match.get("success") and apollo_match.get("lead"):
            matched = apollo_match["lead"]
            email = matched.get("email")
            phone = matched.get("phone")
            confidence = 100
            method = "Apollo Verified Database Record"

    # 2. Fallback: If Apollo match not available or free plan, use preserved candidate pattern
    if not email and meta.get("candidate_email_preview"):
        email = meta.get("candidate_email_preview")
        method = "Enterprise Pattern Estimate"
        confidence = 80

    return {
        "name": name,
        "company": company,
        "email": email,
        "phone": phone,
        "confidence_score": confidence,
        "verification_method": method,
        "status": "Unlocked" if email else "No Email",
        "is_enterprise_locked": False,
        "pipeline_type": "FREE_UNLOCKED"
    }

@app.post("/api/export-csv")
async def export_leads_csv(leads: List[Lead]):
    """Exports leads to CSV format with intelligence and pipeline metadata."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "Name", "Role / Title", "Company", "Location", "Email", "Pipeline Type", 
        "Deliverability Score", "Verification Method", "Mail Provider", "Phone", "LinkedIn URL", "Industry", "Company Size"
    ])
    
    for l in leads:
        meta = l.meta or {}
        writer.writerow([
            l.name,
            l.role or l.headline,
            l.company,
            l.location,
            l.email or "",
            l.pipeline_type,
            f"{l.confidence_score}%" if l.confidence_score else "N/A",
            l.verification_method or "Free Verified",
            l.mail_provider or "Standard",
            l.phone or "",
            l.linkedin_url,
            meta.get("company_industry", ""),
            meta.get("company_size", "")
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=apollo_leads_2026.csv"}
    )

@app.post("/api/generate-outreach")
async def generate_outreach(payload: Dict[str, Any]):
    lead = payload.get("lead", {})
    name = lead.get("name", "there").split()[0]
    company = lead.get("company", "your company")
    headline = lead.get("headline", "your team's work")
    
    casual = {
        "subject": f"Hey {name} — quick thought on {company}",
        "body": (
            f"Hi {name},\n\n"
            f"Saw what you're building at {company} and wanted to reach out.\n\n"
            f"We help teams scaling outbound pipeline unlock high-value prospects.\n\n"
            f"Open to a brief 5-minute chat next week?\n\n"
            f"Best,\nAziz"
        )
    }
    
    value = {
        "subject": f"Idea for {company}'s outbound growth",
        "body": (
            f"Hi {name},\n\n"
            f"Noticed your focus on {headline} at {company}.\n\n"
            f"We put together an AI-driven outreach strategy tailored for your space.\n\n"
            f"Would you be interested if I sent over a quick 2-minute walkthrough video?\n\n"
            f"Cheers,\nAziz"
        )
    }
    
    direct = {
        "subject": f"Quick question regarding {company}",
        "body": (
            f"Hi {name},\n\n"
            f"Are you currently looking to automate prospect discovery and enrich lead contacts for {company}?\n\n"
            f"If so, I'd love to share how our platform can streamline this in seconds.\n\n"
            f"Let me know if you have 10 minutes this week.\n\n"
            f"Thanks,\nAziz"
        )
    }
    
    return {
        "casual": casual,
        "value": value,
        "direct": direct
    }
