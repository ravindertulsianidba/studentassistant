from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr

class GoogleIn(BaseModel):
    id_token: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailIn(BaseModel):
    token: str


class ResendVerificationIn(BaseModel):
    email: EmailStr


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str


class DeleteAccountIn(BaseModel):
    password: Optional[str] = None


class DevLoginIn(BaseModel):
    email: str


class RefreshIn(BaseModel):
    refresh_token: str


class CaptureIn(BaseModel):
    text: str


class ImportIn(BaseModel):
    image_base64: Optional[str] = None
    text: Optional[str] = None
    kind: Optional[str] = "auto"
    filename: Optional[str] = None


class NotesIn(BaseModel):
    title: str
    course: Optional[str] = None
    transcript: str


class SearchIn(BaseModel):
    query: str


class TaskIn(BaseModel):
    title: str
    course: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[str] = "normal"
    category: Optional[str] = "general"


class EventIn(BaseModel):
    title: str
    event_type: str = "personal"
    course: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    location: Optional[str] = None
    days: Optional[List[str]] = None
    recurring: bool = False
    notes: Optional[str] = None


class ReviewActionIn(BaseModel):
    action: str
    edited: Optional[Dict[str, Any]] = None


class ReminderIn(BaseModel):
    title: str
    remind_at: str
    body: Optional[str] = None
    ref_type: Optional[str] = "manual"
    ref_id: Optional[str] = None


class ReminderStatusIn(BaseModel):
    status: str  # scheduled | delivered | failed | snoozed | done | cancelled
    external_id: Optional[str] = None
    snooze_until: Optional[str] = None
    detail: Optional[str] = None


class CalendarSyncIn(BaseModel):
    # device reports the OS-calendar event id it created for each of our event ids
    mappings: Dict[str, str]
