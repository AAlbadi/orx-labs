from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class LeadStatus(str, Enum):
    FOUND = "Found"
    PROCESSING = "Processing"
    UNLOCKED = "Unlocked"
    NO_EMAIL = "No Email"
    FAILED = "Failed"
    ALREADY_UNLOCKED = "Already Unlocked"

class Lead(BaseModel):
    id: str
    name: str
    headline: Optional[str] = ""
    role: Optional[str] = ""
    company: Optional[str] = ""
    location: Optional[str] = ""
    linkedin_url: str
    email: Optional[str] = None
    email_status: Optional[str] = None  # "verified", "guessed", "unavailable"
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    status: LeadStatus = LeadStatus.FOUND
    apollo_unlocked: bool = False
    source: str = "Apollo Intelligence"
    confidence_score: Optional[int] = None
    verification_method: Optional[str] = None
    mail_provider: Optional[str] = None
    mx_host: Optional[str] = None
    is_enterprise_locked: bool = False  # True for Fortune 500 / 10k+ employees (requires on-demand Apollo unlock)
    pipeline_type: str = "FREE_UNLOCKED"  # "FREE_UNLOCKED" or "ENTERPRISE_LOCKED"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class SearchRequest(BaseModel):
    prompt: str
    max_leads: int = 10
    apollo_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    auto_unlock_apollo: bool = True
    delay_between_profiles_sec: float = 1.0
    exclude_urls: List[str] = Field(default_factory=list)
    previous_prompt: Optional[str] = None
    page: int = 1

class VerifyKeyRequest(BaseModel):
    api_key: str

class ChromeStatusResponse(BaseModel):
    connected: bool
    port: int = 9222
    version_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
