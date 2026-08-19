from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    company = Column(String, nullable=True)
    role = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    github_username = Column(String, nullable=True)
    academic_profile = Column(String, nullable=True)
    
    # Enrichment & Lifecycle states:
    # INGESTED -> HARVESTING -> ENRICHED -> COPYWRITING -> DRAFTED -> CONTACTED -> REPLIED -> NEGOTIATING -> BOOKED -> STOPPED
    status = Column(String, default="INGESTED", nullable=False)
    
    # Context Harvester JSON footprint
    # { "linkedin": {...}, "github": [...], "publications": [...] }
    harvested_context = Column(JSON, default=dict, nullable=False)
    
    # Synapse Copywriter outputs
    personalized_subject = Column(String, nullable=True)
    personalized_copy = Column(Text, nullable=True)
    selected_variant = Column(String, nullable=True) # "A" or "B"
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    logs = relationship("EmailLog", back_populates="lead", cascade="all, delete-orphan")
    negotiator_state = relationship("NegotiatorState", back_populates="lead", uselist=False, cascade="all, delete-orphan")


class EmailCampaign(Base):
    __tablename__ = "email_campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    template_a_subject = Column(String, nullable=False)
    template_a_body = Column(Text, nullable=False)
    template_b_subject = Column(String, nullable=False)
    template_b_body = Column(Text, nullable=False)
    
    # Steps configs: e.g., [{"delay_days": 3, "step": 2}]
    sequence_steps = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    logs = relationship("EmailLog", back_populates="campaign")


class EmailLog(Base):
    __tablename__ = "email_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("email_campaigns.id"), nullable=True)
    
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    
    # SENT -> DELIVERED -> OPENED -> CLICKED -> BOUNCED
    status = Column(String, default="SENT", nullable=False)
    message_id = Column(String, nullable=True, index=True) # SMTP Header Message-ID for thread correlation
    
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    lead = relationship("Lead", back_populates="logs")
    campaign = relationship("EmailCampaign", back_populates="logs")


class NegotiatorState(Base):
    __tablename__ = "negotiator_states"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), unique=True, nullable=False)
    
    # Dialogue loop logs: [{"role": "user", "content": "..."}]
    conversation_history = Column(JSON, default=list, nullable=False)
    
    # ACTIVE -> BOOKED -> CLOSED
    status = Column(String, default="ACTIVE", nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    
    last_message_received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    lead = relationship("Lead", back_populates="negotiator_state")
