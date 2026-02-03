from pydantic import BaseModel, Field
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
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=4)


class LoginOut(BaseModel):
    token: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: str


class UserCreate(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=4)
    role: str = Field(..., min_length=3)


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
    subject: str = Field(..., min_length=3)
    message: str = Field(..., min_length=5)


class TicketOut(BaseModel):
    id: int
    user_email: str
    subject: str
    message: str
    status: str
    created_at: str


class KBCreate(BaseModel):
    title: str = Field(..., min_length=3)
    content: str = Field(..., min_length=5)


class KBOut(BaseModel):
    id: int
    title: str
    content: str
    created_at: str


class NotificationCreate(BaseModel):
    message: str = Field(..., min_length=3)
    level: str = Field(..., min_length=3)


class NotificationOut(BaseModel):
    id: int
    message: str
    level: str
    created_at: str


class EmailCreate(BaseModel):
    to_email: str = Field(..., min_length=3)
    subject: str = Field(..., min_length=3)
    body: str = Field(..., min_length=5)


class EmailOut(BaseModel):
    id: int
    to_email: str
    subject: str
    body: str
    status: str
    created_at: str
