import csv
import io
import json
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from backend.app.database.connection import get_db
from backend.app.database.schema import Lead, NegotiatorState, EmailLog
from backend.app.celery_app import process_harvester_job, process_dispatch_job
from backend.app.services.negotiator import negotiator
from backend.app.services.sequencer import sequencer

router = APIRouter(prefix="/leads", tags=["leads"])

class LeadCreateSchema(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_username: Optional[str] = None
    academic_profile: Optional[str] = None

class MessageInputSchema(BaseModel):
    message: str

@router.get("/")
def get_leads(db: Session = Depends(get_db)):
    """Fetch all leads in the database."""
    return db.query(Lead).order_by(Lead.id.desc()).all()

@router.post("/upload/json")
def upload_leads_json(leads: List[LeadCreateSchema], background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Bulk upload leads via JSON array and trigger enrichment."""
    added_leads = []
    for l in leads:
        # Check duplicate
        existing = db.query(Lead).filter(Lead.email == l.email).first()
        if existing:
            continue
            
        new_lead = Lead(**l.model_dump())
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        added_leads.append(new_lead)
        
        # Trigger background harvester job immediately
        background_tasks.add_task(process_harvester_job, new_lead.id)
        
    return {"message": f"Successfully ingested {len(added_leads)} leads and queued for enrichment.", "leads_count": len(added_leads)}

@router.post("/upload/csv")
async def upload_leads_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk upload leads via CSV file."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
        
    contents = await file.read()
    buffer = io.StringIO(contents.decode('utf-8'))
    reader = csv.DictReader(buffer)
    
    added_count = 0
    for row in reader:
        email_val = row.get("email") or row.get("Email")
        if not email_val:
            continue
            
        # Clean email
        email_val = email_val.strip()
        existing = db.query(Lead).filter(Lead.email == email_val).first()
        if existing:
            continue
            
        new_lead = Lead(
            email=email_val,
            first_name=row.get("first_name") or row.get("First Name") or row.get("firstName"),
            last_name=row.get("last_name") or row.get("Last Name") or row.get("lastName"),
            company=row.get("company") or row.get("Company"),
            role=row.get("role") or row.get("Role") or row.get("Title") or row.get("job_title"),
            linkedin_url=row.get("linkedin_url") or row.get("LinkedIn") or row.get("linkedin"),
            github_username=row.get("github_username") or row.get("GitHub") or row.get("github"),
            academic_profile=row.get("academic_profile") or row.get("Academic") or row.get("arxiv")
        )
        
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        added_count += 1
        
        # Trigger harvester pipeline in background
        background_tasks.add_task(process_harvester_job, new_lead.id)
        
    return {"message": f"Successfully ingested {added_count} leads from CSV.", "leads_count": added_count}

@router.post("/{lead_id}/enrich")
def force_enrich_lead(lead_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Force run context harvester and copywriting enrichment. Also resets failed states."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Reset status so pipeline can re-enter
    lead.status = "INGESTED"
    db.commit()

    background_tasks.add_task(process_harvester_job, lead.id)
    return {"message": "Context harvest & copywriting queued."}

@router.post("/{lead_id}/dispatch")
def force_dispatch_email(lead_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Force dispatch generated personalized outreach email."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.status != "DRAFTED" and not lead.personalized_copy:
        raise HTTPException(status_code=400, detail="Personalized copy is not drafted yet.")
        
    background_tasks.add_task(process_dispatch_job, lead.id)
    return {"message": "Email dispatch task triggered."}

@router.post("/{lead_id}/simulate-reply")
def simulate_reply(lead_id: int, input_data: MessageInputSchema, db: Session = Depends(get_db)):
    """Simulates receiving a reply from a prospect. Triggers smart-stop and AI Negotiator loop."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    # Apply smart-stop (marks lead status as REPLIED)
    sequencer.simulate_incoming_reply(db, lead.email)
    
    # Process reply with AI Negotiator
    ai_reply = negotiator.process_incoming_message(db, lead.id, input_data.message)
    
    # Log the reply email
    reply_log = EmailLog(
        lead_id=lead.id,
        subject=f"Re: {lead.personalized_subject or 'Outreach'}",
        body=input_data.message,
        status="DELIVERED",
        sent_at=lead.updated_at
    )
    db.add(reply_log)
    db.commit()
    
    return {"status": "REPLIED", "ai_reply": ai_reply}

@router.get("/{lead_id}/negotiation")
def get_negotiator_history(lead_id: int, db: Session = Depends(get_db)):
    """Fetch the active dialogue negotiator history for the lead."""
    state = db.query(NegotiatorState).filter(NegotiatorState.lead_id == lead_id).first()
    if not state:
        return {"status": "INACTIVE", "history": []}
    return {
        "status": state.status,
        "history": state.conversation_history
    }

@router.post("/{lead_id}/negotiator-reply")
def post_negotiator_message(lead_id: int, input_data: MessageInputSchema, db: Session = Depends(get_db)):
    """Allows manual override or triggers the next message of the AI Negotiator agent."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    ai_reply = negotiator.process_incoming_message(db, lead.id, input_data.message)
    return {"ai_reply": ai_reply}

class SearchInputSchema(BaseModel):
    query: str

@router.post("/search")
def search_and_ingest_leads(input_data: SearchInputSchema, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Searches the web via ScrapeGraphAI SearchGraph, extracts lead details,
    saves them to database, and triggers background context enrichment.
    """
    try:
        from backend.app.services.harvester import harvester
        results = harvester.find_leads_via_search(input_data.query)
        
        added_leads = []
        for lead_dict in results:
            email_val = lead_dict.get("email")
            if not email_val:
                continue
            
            existing = db.query(Lead).filter(Lead.email == email_val).first()
            if existing:
                continue
                
            new_lead = Lead(
                email=email_val,
                first_name=lead_dict.get("first_name"),
                last_name=lead_dict.get("last_name"),
                company=lead_dict.get("company"),
                role=lead_dict.get("role"),
                linkedin_url=lead_dict.get("linkedin_url"),
                github_username=lead_dict.get("github_username")
            )
            db.add(new_lead)
            db.commit()
            db.refresh(new_lead)
            added_leads.append(new_lead)
            
            # Queue background harvester/enricher for the found lead!
            background_tasks.add_task(process_harvester_job, new_lead.id)
            
        return {
            "message": f"Successfully scraped and ingested {len(added_leads)} leads for query: '{input_data.query}'.",
            "leads_count": len(added_leads)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
