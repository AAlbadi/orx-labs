"""
Background task pipeline for ORX. Runs in FastAPI's BackgroundTasks
(in-process) or Celery workers (distributed).

Failure modes are VISIBLE — statuses like HARVEST_FAILED / COPY_FAILED
are stored so the UI can surface them to the founder instead of silently
using fake data.
"""
import os
from celery import Celery
from backend.app.config import settings
from backend.app.database.connection import SessionLocal
from backend.app.database.schema import Lead, EmailLog
from backend.app.services.harvester import harvester
from backend.app.services.copywriter import copywriter
from backend.app.services.sequencer import sequencer
from backend.app.services.negotiator import negotiator

# Configure Celery
celery_app = Celery(
    "outreach_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def process_harvester_job(lead_id: int):
    """
    Stage 1: Real context enrichment from web sources.
    - LinkedIn scraping (ScrapeGraphAI / HTTP / LLM inference)
    - GitHub API
    - arXiv API
    On success → chains into copywriting.
    On failure → marks lead HARVEST_FAILED with error in context.
    """
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return

        lead.status = "HARVESTING"
        db.commit()

        print(f"[JOB] Harvesting context for: {lead.first_name} {lead.last_name} <{lead.email}>")
        context = harvester.harvest_lead_context(
            first_name=lead.first_name or "",
            last_name=lead.last_name or "",
            company=lead.company or "",
            linkedin_url=lead.linkedin_url,
            github_username=lead.github_username,
            academic_profile=lead.academic_profile,
        )

        lead.harvested_context = context
        lead.status = "ENRICHED"
        db.commit()
        print(f"[JOB] Context harvested for {lead.email}. Chaining to copywriting.")

        # Auto-chain to copywriting
        process_copywriter_job(lead_id)

    except Exception as e:
        print(f"[JOB ERROR] Harvest failed for lead {lead_id}: {e}")
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.status = "HARVEST_FAILED"
                lead.harvested_context = {"error": str(e)}
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def process_copywriter_job(lead_id: int):
    """
    Stage 2: AI copywriting using real context.
    Uses free LLM via OpenRouter.
    On failure → marks lead COPY_FAILED.
    """
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead or lead.status != "ENRICHED":
            return

        lead.status = "COPYWRITING"
        db.commit()

        variant = "A" if lead_id % 2 == 0 else "B"
        lead.selected_variant = variant

        print(f"[JOB] Writing Variant-{variant} copy for: {lead.email}")
        subject, body = copywriter.generate_copy(
            lead_info={
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "company": lead.company,
                "role": lead.role,
            },
            context=lead.harvested_context or {},
            variant=variant,
        )

        lead.personalized_subject = subject
        lead.personalized_copy = body
        lead.status = "DRAFTED"
        db.commit()
        print(f"[JOB] ✓ Draft ready for {lead.email}")

    except Exception as e:
        print(f"[JOB ERROR] Copywriting failed for lead {lead_id}: {e}")
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.status = "COPY_FAILED"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def process_dispatch_job(lead_id: int):
    """
    Stage 3: Send the drafted email via SMTP.
    """
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead or lead.status != "DRAFTED":
            return

        print(f"[JOB] Dispatching email to: {lead.email}")
        result = sequencer.send_email(
            to_email=lead.email,
            subject=lead.personalized_subject,
            body=lead.personalized_copy,
        )

        log_entry = EmailLog(
            lead_id=lead.id,
            subject=lead.personalized_subject,
            body=lead.personalized_copy,
            status=result.get("status", "SENT"),
            message_id=result.get("message_id"),
            sent_at=result.get("sent_at"),
        )
        db.add(log_entry)
        lead.status = "CONTACTED"
        db.commit()
        print(f"[JOB] ✓ Email dispatched to {lead.email}")

    except Exception as e:
        print(f"[JOB ERROR] Dispatch failed for lead {lead_id}: {e}")
    finally:
        db.close()


# ── Celery task wrappers ──────────────────────────────────────────────────────

@celery_app.task(name="tasks.harvest_lead")
def celery_harvest_lead(lead_id: int):
    process_harvester_job(lead_id)


@celery_app.task(name="tasks.generate_copy")
def celery_generate_copy(lead_id: int):
    process_copywriter_job(lead_id)


@celery_app.task(name="tasks.dispatch_email")
def celery_dispatch_email(lead_id: int):
    process_dispatch_job(lead_id)
