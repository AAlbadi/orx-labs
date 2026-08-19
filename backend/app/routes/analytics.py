from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.app.database.connection import get_db
from backend.app.database.schema import Lead, EmailLog, NegotiatorState

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/dashboard")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Fetch high-level KPI and funnel statistics for the ORX dashboard."""
    total_leads = db.query(Lead).count()
    status_counts = db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
    
    # Map raw query counts to dictionary
    status_map = {status: count for status, count in status_counts}
    
    enriched_count = total_leads - status_map.get("INGESTED", 0) - status_map.get("HARVESTING", 0)
    contacted_count = (
        status_map.get("CONTACTED", 0) + 
        status_map.get("REPLIED", 0) + 
        status_map.get("NEGOTIATING", 0) + 
        status_map.get("BOOKED", 0)
    )
    replied_count = (
        status_map.get("REPLIED", 0) + 
        status_map.get("NEGOTIATING", 0) + 
        status_map.get("BOOKED", 0)
    )
    booked_count = status_map.get("BOOKED", 0)
    
    reply_rate = (replied_count / contacted_count * 100) if contacted_count > 0 else 0.0
    booking_rate = (booked_count / replied_count * 100) if replied_count > 0 else 0.0
    
    # Recent logs for timeline feed
    recent_logs = (
        db.query(EmailLog)
        .order_by(EmailLog.sent_at.desc())
        .limit(10)
        .all()
    )
    
    formatted_logs = []
    for log in recent_logs:
        # Fetch associated lead info
        lead = db.query(Lead).filter(Lead.id == log.lead_id).first()
        formatted_logs.append({
            "id": log.id,
            "lead_name": f"{lead.first_name} {lead.last_name}" if lead else "Unknown Lead",
            "lead_email": lead.email if lead else "",
            "subject": log.subject,
            "status": log.status,
            "sent_at": log.sent_at.isoformat()
        })

    # Timeline of active bookings
    booked_states = (
        db.query(NegotiatorState)
        .filter(NegotiatorState.status == "BOOKED")
        .order_by(NegotiatorState.updated_at.desc())
        .limit(5)
        .all()
    )
    meetings = []
    for state in booked_states:
        lead = db.query(Lead).filter(Lead.id == state.lead_id).first()
        meetings.append({
            "lead_name": f"{lead.first_name} {lead.last_name}" if lead else "Unknown",
            "company": lead.company if lead else "",
            "booked_at": state.updated_at.isoformat()
        })

    return {
        "summary": {
            "total_leads": total_leads,
            "enriched_leads": enriched_count,
            "contacted_leads": contacted_count,
            "replied_leads": replied_count,
            "meetings_booked": booked_count,
            "reply_rate": round(reply_rate, 1),
            "booking_rate": round(booking_rate, 1)
        },
        "funnel": {
            "Ingested": status_map.get("INGESTED", 0),
            "Enriched": enriched_count,
            "Contacted": contacted_count,
            "Replied": replied_count,
            "Booked": booked_count
        },
        "recent_logs": formatted_logs,
        "meetings": meetings
    }
