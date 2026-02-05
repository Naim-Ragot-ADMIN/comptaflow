from pydantic import BaseModel, Field, EmailStr
from typing import List


class DocumentIn(BaseModel):
    filename: str = Field(..., min_length=1)


class DocumentOut(BaseModel):
    id: int
    filename: str
    vendor: str
    doc_date: str
    amount_ttc: float
    vat: float
    status: str
    created_at: str


class DocumentList(BaseModel):
    items: List[DocumentOut]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=4, max_length=128)


class LoginOut(BaseModel):
    token: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    created_at: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(..., min_length=3, max_length=32)


class EntryOut(BaseModel):
    date: str
    journal: str
    account: str
    label: str
    debit: float
    credit: float
    doc: str
    vendor: str


class RuleOut(BaseModel):
    id: int
    keyword: str
    account_code: str
    account_label: str
    created_at: str


class RuleCreate(BaseModel):
    keyword: str = Field(..., min_length=2)
    account_code: str = Field(..., min_length=3)
    account_label: str = Field(..., min_length=3)


class BankTxnOut(BaseModel):
    id: int
    txn_date: str
    description: str
    amount: float
    created_at: str


class RecoOut(BaseModel):
    document_id: int
    bank_txn_id: int
    match_score: float


class CheckoutIn(BaseModel):
    plan_id: str = Field(..., min_length=2)


class SubscriptionOut(BaseModel):
    plan_id: str
    status: str


class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=140)
    message: str = Field(..., min_length=5, max_length=2000)


class TicketOut(BaseModel):
    id: int
    user_email: str
    subject: str
    message: str
    status: str
    created_at: str


class KBCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=140)
    content: str = Field(..., min_length=5, max_length=4000)


class KBOut(BaseModel):
    id: int
    title: str
    content: str
    created_at: str


class NotificationCreate(BaseModel):
    message: str = Field(..., min_length=3, max_length=240)
    level: str = Field(..., min_length=3, max_length=20)


class NotificationOut(BaseModel):
    id: int
    message: str
    level: str
    created_at: str


class EmailCreate(BaseModel):
    to_email: EmailStr
    subject: str = Field(..., min_length=3, max_length=140)
    body: str = Field(..., min_length=5, max_length=4000)


class EmailOut(BaseModel):
    id: int
    to_email: str
    subject: str
    body: str
    status: str
    created_at: str
