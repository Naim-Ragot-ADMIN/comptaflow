from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
import csv
import io
from pathlib import Path
import uuid
import os
from collections import defaultdict

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from .database import init_db, get_connection, UPLOADS_DIR
from .models import (
    DocumentIn,
    DocumentOut,
    DocumentList,
    LoginIn,
    LoginOut,
    UserOut,
    UserCreate,
    EntryOut,
    RuleOut,
    RuleCreate,
    BankTxnOut,
    RecoOut,
    CheckoutIn,
    SubscriptionOut,
    TicketCreate,
    TicketOut,
    KBCreate,
    KBOut,
    NotificationCreate,
    NotificationOut,
    EmailCreate,
    EmailOut,
)
from .ai_handler import extract_document
from .utils import hash_password, to_accounting_entries, best_matches


app = FastAPI(title="ComptaFlow API", version="0.1.0")

def _get_origins():
    raw = os.getenv("CORS_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic in-memory rate limit for login
_login_attempts = defaultdict(list)
_LOGIN_WINDOW_SEC = 300
_LOGIN_MAX_ATTEMPTS = 8


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=()"
    return response


@app.on_event("startup")
def startup():
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE name = ?", ("Cabinet Demo",))
    tenant = cur.fetchone()
    if not tenant:
        cur.execute(
            "INSERT INTO tenants (name, created_at) VALUES (?, ?)",
            ("Cabinet Demo", datetime.utcnow().isoformat()),
        )
        conn.commit()
        tenant_id = cur.lastrowid
    else:
        tenant_id = tenant["id"]
    cur.execute("SELECT id FROM users WHERE email = ?", ("admin@comptaflow.fr",))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users (email, tenant_id, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            ("admin@comptaflow.fr", tenant_id, "admin", hash_password("demo1234"), datetime.utcnow().isoformat()),
        )
        conn.commit()
    conn.close()


def require_user(x_auth_token: str | None):
    if not x_auth_token:
        raise HTTPException(status_code=401, detail="Missing token")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT users.id, users.email, users.tenant_id, users.role, sessions.expires_at
        FROM sessions JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (x_auth_token,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")
    if row["expires_at"]:
        try:
            if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
                raise HTTPException(status_code=401, detail="Token expired")
        except ValueError:
            pass
    return dict(row)


def require_role(user: dict, allowed: set[str]):
    if user["role"] not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient role")


@app.post("/documents", response_model=DocumentOut)
def create_document(payload: DocumentIn, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    data = extract_document(payload.filename)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents
        (filename, vendor, doc_date, amount_ttc, vat, status, created_at, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["filename"],
            data["vendor"],
            data["doc_date"],
            data["amount_ttc"],
            data["vat"],
            data["status"],
            data["created_at"],
            user["tenant_id"],
        ),
    )
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return DocumentOut(id=doc_id, **data)


@app.post("/documents/upload", response_model=DocumentOut)
def upload_document(file: UploadFile = File(...), x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant", "client"})
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stored_name = f"{stamp}_{safe_name}"
    target: Path = UPLOADS_DIR / stored_name
    with target.open("wb") as f:
        f.write(file.file.read())

    data = extract_document(file.filename, str(target))
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents
        (filename, vendor, doc_date, amount_ttc, vat, status, created_at, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["filename"],
            data["vendor"],
            data["doc_date"],
            data["amount_ttc"],
            data["vat"],
            data["status"],
            data["created_at"],
            user["tenant_id"],
        ),
    )
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return DocumentOut(id=doc_id, **data)


@app.get("/documents", response_model=DocumentList)
def list_documents(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE tenant_id = ? ORDER BY id DESC", (user["tenant_id"],))
    rows = cur.fetchall()
    conn.close()
    items = [DocumentOut(**dict(r)) for r in rows]
    return DocumentList(items=items)


@app.get("/documents.csv")
def export_documents_csv(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE tenant_id = ? ORDER BY id DESC", (user["tenant_id"],))
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "filename", "vendor", "doc_date", "amount_ttc", "vat", "status", "created_at"])
    for r in rows:
        writer.writerow([
            r["id"], r["filename"], r["vendor"], r["doc_date"],
            r["amount_ttc"], r["vat"], r["status"], r["created_at"]
        ])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv")


@app.get("/documents.xlsx")
def export_documents_xlsx(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    try:
        from openpyxl import Workbook  # type: ignore
    except Exception:
        raise HTTPException(status_code=501, detail="XLSX export unavailable. Install openpyxl.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE tenant_id = ? ORDER BY id DESC", (user["tenant_id"],))
    rows = cur.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Documents"
    ws.append(["id", "filename", "vendor", "doc_date", "amount_ttc", "vat", "status", "created_at"])
    for r in rows:
        ws.append([
            r["id"], r["filename"], r["vendor"], r["doc_date"],
            r["amount_ttc"], r["vat"], r["status"], r["created_at"]
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/entries", response_model=list[EntryOut])
def list_entries(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT keyword, account_code, account_label FROM account_rules WHERE tenant_id = ?",
        (user["tenant_id"],),
    )
    rules = [(r["keyword"], r["account_code"], r["account_label"]) for r in cur.fetchall()]
    cur.execute("SELECT * FROM documents WHERE tenant_id = ? ORDER BY id DESC", (user["tenant_id"],))
    rows = cur.fetchall()
    conn.close()
    entries = []
    for r in rows:
        entries.extend(to_accounting_entries(dict(r), rules))
    return entries


@app.get("/entries.xlsx")
def export_entries_xlsx(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    try:
        from openpyxl import Workbook  # type: ignore
    except Exception:
        raise HTTPException(status_code=501, detail="XLSX export unavailable. Install openpyxl.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT keyword, account_code, account_label FROM account_rules WHERE tenant_id = ?",
        (user["tenant_id"],),
    )
    rules = [(r["keyword"], r["account_code"], r["account_label"]) for r in cur.fetchall()]
    cur.execute("SELECT * FROM documents WHERE tenant_id = ? ORDER BY id DESC", (user["tenant_id"],))
    rows = cur.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Ecritures"
    ws.append(["date", "journal", "account", "label", "debit", "credit", "doc", "vendor"])
    for r in rows:
        for e in to_accounting_entries(dict(r), rules):
            ws.append([
                e["date"], e["journal"], e["account"], e["label"],
                e["debit"], e["credit"], e["doc"], e["vendor"]
            ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/bank/import", response_model=list[BankTxnOut])
def import_bank_csv(file: UploadFile = File(...), x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    content = file.file.read().decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    conn = get_connection()
    cur = conn.cursor()
    for r in reader:
        txn_date = (r.get("date") or r.get("Date") or "").strip()
        description = (r.get("description") or r.get("Libellé") or r.get("Label") or "").strip()
        amount_raw = (r.get("amount") or r.get("Montant") or r.get("Amount") or "0").replace(",", ".")
        amount = float(amount_raw) if amount_raw else 0.0
        cur.execute(
            """
            INSERT INTO bank_transactions (tenant_id, txn_date, description, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["tenant_id"], txn_date, description, amount, datetime.utcnow().isoformat()),
        )
        rows.append(
            BankTxnOut(
                id=cur.lastrowid,
                txn_date=txn_date,
                description=description,
                amount=amount,
                created_at=datetime.utcnow().isoformat(),
            )
        )
    conn.commit()
    conn.close()
    return rows


@app.get("/bank", response_model=list[BankTxnOut])
def list_bank(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, txn_date, description, amount, created_at FROM bank_transactions WHERE tenant_id = ? ORDER BY id DESC",
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    return [BankTxnOut(**dict(r)) for r in rows]


@app.get("/reconciliations", response_model=list[RecoOut])
def get_reconciliations(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE tenant_id = ?", (user["tenant_id"],))
    docs = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM bank_transactions WHERE tenant_id = ?", (user["tenant_id"],))
    txns = [dict(r) for r in cur.fetchall()]
    conn.close()
    return [RecoOut(**m) for m in best_matches(docs, txns)]


@app.get("/billing/plans")
def billing_plans():
    return {
        "plans": [
            {"id": "starter", "name": "Starter", "price_eur_month": 29, "features": ["100 pièces/mois", "1 cabinet"]},
            {"id": "pro", "name": "Pro", "price_eur_month": 99, "features": ["1000 pièces/mois", "multi-cabinets"]},
            {"id": "enterprise", "name": "Enterprise", "price_eur_month": 299, "features": ["illimité", "SLA + support"]},
        ]
    }


def _stripe():
    try:
        import stripe  # type: ignore
    except Exception:
        raise HTTPException(status_code=501, detail="Stripe SDK missing. Install stripe.")
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=501, detail="Stripe not configured")
    stripe.api_key = secret
    return stripe


@app.get("/billing/config")
def billing_config():
    missing = []
    if not os.getenv("STRIPE_SECRET_KEY"):
        missing.append("STRIPE_SECRET_KEY")
    if not os.getenv("STRIPE_PRICE_STARTER"):
        missing.append("STRIPE_PRICE_STARTER")
    if not os.getenv("STRIPE_PRICE_PRO"):
        missing.append("STRIPE_PRICE_PRO")
    if not os.getenv("STRIPE_PRICE_ENTERPRISE"):
        missing.append("STRIPE_PRICE_ENTERPRISE")
    if not os.getenv("STRIPE_WEBHOOK_SECRET"):
        missing.append("STRIPE_WEBHOOK_SECRET")
    ok = len(missing) == 0
    return {"ok": ok, "missing": missing}


@app.post("/billing/test")
def billing_test(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    stripe = _stripe()
    price_id = os.getenv("STRIPE_PRICE_STARTER")
    if not price_id:
        raise HTTPException(status_code=400, detail="Missing STRIPE_PRICE_STARTER")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=os.getenv("STRIPE_SUCCESS_URL", "http://localhost:8000/success"),
        cancel_url=os.getenv("STRIPE_CANCEL_URL", "http://localhost:8000/cancel"),
        metadata={"tenant_id": str(user["tenant_id"]), "plan_id": "starter"},
    )
    return {"checkout_url": session.url}


@app.post("/billing/checkout")
def billing_checkout(payload: CheckoutIn, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    stripe = _stripe()

    price_map = {
        "starter": os.getenv("STRIPE_PRICE_STARTER"),
        "pro": os.getenv("STRIPE_PRICE_PRO"),
        "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE"),
    }
    price_id = price_map.get(payload.plan_id)
    if not price_id:
        raise HTTPException(status_code=400, detail="Unknown plan")

    success_url = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:8000/success")
    cancel_url = os.getenv("STRIPE_CANCEL_URL", "http://localhost:8000/cancel")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": str(user["tenant_id"]), "plan_id": payload.plan_id},
    )
    return {"checkout_url": session.url}


@app.get("/billing/status", response_model=SubscriptionOut)
def billing_status(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT plan_id, status FROM subscriptions WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
        (user["tenant_id"],),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return SubscriptionOut(plan_id="starter", status="inactive")
    return SubscriptionOut(plan_id=row["plan_id"], status=row["status"])


@app.get("/billing/metrics")
def billing_metrics(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT status, COUNT(*) as cnt
        FROM subscriptions
        WHERE tenant_id = ?
        GROUP BY status
        """,
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    counts = {r["status"]: r["cnt"] for r in rows}
    active = counts.get("active", 0)
    return {
        "active_subscriptions": active,
        "status_breakdown": counts,
    }


@app.get("/billing/analytics")
def billing_analytics(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT plan_id, status FROM subscriptions WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user["tenant_id"],),
    )
    row = cur.fetchone()
    conn.close()

    price_map = {
        "starter": 29,
        "pro": 99,
        "enterprise": 299,
    }
    if not row or row["status"] != "active":
        return {"mrr": 0, "arpa": 0, "churn": 0}

    mrr = price_map.get(row["plan_id"], 0)
    arpa = mrr
    churn = 0
    return {"mrr": mrr, "arpa": arpa, "churn": churn}


@app.get("/support/tickets", response_model=list[TicketOut])
def list_tickets(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_email, subject, message, status, created_at FROM tickets WHERE tenant_id = ? ORDER BY id DESC",
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    return [TicketOut(**dict(r)) for r in rows]


@app.post("/support/tickets", response_model=TicketOut)
def create_ticket(payload: TicketCreate, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tickets (tenant_id, user_email, subject, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user["tenant_id"], user["email"], payload.subject, payload.message, "open", datetime.utcnow().isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return TicketOut(
        id=new_id,
        user_email=user["email"],
        subject=payload.subject,
        message=payload.message,
        status="open",
        created_at=datetime.utcnow().isoformat(),
    )


@app.post("/support/tickets/{ticket_id}/close")
def close_ticket(ticket_id: int, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tickets SET status = 'closed' WHERE id = ? AND tenant_id = ?",
        (ticket_id, user["tenant_id"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/kb", response_model=list[KBOut])
def list_kb(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, content, created_at FROM knowledge_base WHERE tenant_id = ? ORDER BY id DESC",
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    return [KBOut(**dict(r)) for r in rows]


@app.post("/kb", response_model=KBOut)
def create_kb(payload: KBCreate, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO knowledge_base (tenant_id, title, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user["tenant_id"], payload.title, payload.content, datetime.utcnow().isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return KBOut(
        id=new_id,
        title=payload.title,
        content=payload.content,
        created_at=datetime.utcnow().isoformat(),
    )


@app.delete("/kb/{kb_id}")
def delete_kb(kb_id: int, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM knowledge_base WHERE id = ? AND tenant_id = ?",
        (kb_id, user["tenant_id"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/notifications", response_model=list[NotificationOut])
def list_notifications(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, message, level, created_at FROM notifications WHERE tenant_id = ? ORDER BY id DESC",
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    return [NotificationOut(**dict(r)) for r in rows]


@app.post("/notifications", response_model=NotificationOut)
def create_notification(payload: NotificationCreate, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    level = payload.level.lower()
    if level not in {"info", "warning", "success"}:
        raise HTTPException(status_code=400, detail="Invalid level")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO notifications (tenant_id, message, level, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user["tenant_id"], payload.message, level, datetime.utcnow().isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return NotificationOut(
        id=new_id,
        message=payload.message,
        level=level,
        created_at=datetime.utcnow().isoformat(),
    )


@app.delete("/notifications/{notification_id}")
def delete_notification(notification_id: int, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM notifications WHERE id = ? AND tenant_id = ?",
        (notification_id, user["tenant_id"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


def _send_email_smtp(to_email: str, subject: str, body: str):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_email = os.getenv("SMTP_FROM", user or "")
    if not host or not user or not password or not from_email:
        return False
    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


def _create_notification(tenant_id: int, message: str, level: str = "info"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO notifications (tenant_id, message, level, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (tenant_id, message, level, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


@app.get("/emails", response_model=list[EmailOut])
def list_emails(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, to_email, subject, body, status, created_at FROM email_queue WHERE tenant_id = ? ORDER BY id DESC",
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    return [EmailOut(**dict(r)) for r in rows]


@app.post("/emails", response_model=EmailOut)
def create_email(payload: EmailCreate, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    status = "queued"
    sent = _send_email_smtp(payload.to_email, payload.subject, payload.body)
    if sent:
        status = "sent"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO email_queue (tenant_id, to_email, subject, body, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user["tenant_id"], payload.to_email, payload.subject, payload.body, status, datetime.utcnow().isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return EmailOut(
        id=new_id,
        to_email=payload.to_email,
        subject=payload.subject,
        body=payload.body,
        status=status,
        created_at=datetime.utcnow().isoformat(),
    )


@app.post("/workflows/remind-missing")
def workflow_remind_missing(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM documents WHERE tenant_id = ? AND status != 'OK'",
        (user["tenant_id"],),
    )
    row = cur.fetchone()
    missing = row["cnt"] if row else 0
    conn.close()
    if missing == 0:
        return {"status": "ok", "message": "Aucune piece en attente."}
    _create_notification(
        user["tenant_id"],
        f"{missing} piece(s) en attente de verification. Merci de completer vos documents.",
        "warning",
    )
    return {"status": "ok", "message": "Notifications creees."}


@app.post("/workflows/monthly-reminder")
def workflow_monthly_reminder(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT email FROM users WHERE tenant_id = ? AND role = 'client'",
        (user["tenant_id"],),
    )
    clients = [r["email"] for r in cur.fetchall()]
    conn.close()
    sent = 0
    for email in clients:
        subject = "Rappel mensuel - Pieces comptables"
        body = "Bonjour, merci de deposer vos pieces du mois dans ComptaFlow."
        ok = _send_email_smtp(email, subject, body)
        status = "sent" if ok else "queued"
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO email_queue (tenant_id, to_email, subject, body, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user["tenant_id"], email, subject, body, status, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
        if ok:
            sent += 1
    return {"status": "ok", "clients": len(clients), "sent": sent}


@app.get("/billing/invoices")
def billing_invoices(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    try:
        stripe = _stripe()
    except HTTPException:
        return {"invoices": []}

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT stripe_customer_id
        FROM subscriptions
        WHERE tenant_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user["tenant_id"],),
    )
    row = cur.fetchone()
    conn.close()
    if not row or not row["stripe_customer_id"]:
        return {"invoices": []}

    invoices = stripe.Invoice.list(customer=row["stripe_customer_id"], limit=10)
    items = []
    for inv in invoices.get("data", []):
        items.append(
            {
                "id": inv.get("id"),
                "status": inv.get("status"),
                "amount_due": (inv.get("amount_due") or 0) / 100,
                "currency": inv.get("currency"),
                "created": inv.get("created"),
                "hosted_invoice_url": inv.get("hosted_invoice_url"),
                "invoice_pdf": inv.get("invoice_pdf"),
            }
        )
    return {"invoices": items}


@app.get("/success")
def billing_success():
    return {
        "status": "ok",
        "message": "Paiement reussi. Vous pouvez fermer cette page et retourner a ComptaFlow.",
    }


@app.get("/cancel")
def billing_cancel():
    return {
        "status": "cancel",
        "message": "Paiement annule. Vous pouvez fermer cette page et retourner a ComptaFlow.",
    }


@app.post("/billing/webhook")
async def billing_webhook(request):
    stripe = _stripe()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not endpoint_secret:
        raise HTTPException(status_code=501, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    def upsert_subscription(tenant_id: int | None, plan_id: str | None, status: str | None, customer_id, subscription_id):
        conn = get_connection()
        cur = conn.cursor()
        if subscription_id:
            cur.execute(
                "SELECT id FROM subscriptions WHERE stripe_subscription_id = ?",
                (subscription_id,),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE subscriptions
                    SET status = ?, stripe_customer_id = COALESCE(stripe_customer_id, ?), updated_at = ?
                    WHERE id = ?
                    """,
                    (status or "active", customer_id, datetime.utcnow().isoformat(), row["id"]),
                )
                conn.commit()
                conn.close()
                return
        if tenant_id and plan_id:
            cur.execute(
                """
                INSERT INTO subscriptions (tenant_id, plan_id, status, stripe_customer_id, stripe_subscription_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(tenant_id),
                    plan_id,
                    status or "active",
                    customer_id,
                    subscription_id,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        conn.close()

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type in {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "invoice.payment_failed",
        "invoice.payment_succeeded",
        "customer.subscription.deleted",
    }:
        tenant_id = None
        plan_id = None
        status = None
        customer_id = None
        subscription_id = None

        metadata = data.get("metadata") or {}
        tenant_id = metadata.get("tenant_id")
        plan_id = metadata.get("plan_id")

        status = data.get("status")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription") or data.get("id")

        if event_type == "invoice.payment_failed":
            status = "past_due"
        if event_type == "invoice.payment_succeeded":
            status = "active"
        if event_type == "customer.subscription.deleted":
            status = "canceled"

        upsert_subscription(tenant_id, plan_id, status, customer_id, subscription_id)

    return {"status": "ok"}


@app.get("/stats")
def get_stats(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(vat), 0) AS vat_sum FROM documents WHERE tenant_id = ?",
        (user["tenant_id"],),
    )
    row = cur.fetchone()
    conn.close()
    return {"count": row["count"], "vat_sum": row["vat_sum"]}


@app.delete("/documents")
def clear_documents(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM documents WHERE tenant_id = ?", (user["tenant_id"],))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/login", response_model=LoginOut)
def login(payload: LoginIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    key = f"{payload.email}:{ip}"
    now = datetime.utcnow()
    attempts = [t for t in _login_attempts[key] if (now - t).total_seconds() < _LOGIN_WINDOW_SEC]
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Try later.")
    _login_attempts[key] = attempts

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (payload.email,))
    row = cur.fetchone()
    if not row:
        _login_attempts[key].append(now)
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if row["password_hash"] != hash_password(payload.password):
        _login_attempts[key].append(now)
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = uuid.uuid4().hex
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    cur.execute(
        "INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (row["id"], token, datetime.utcnow().isoformat(), expires_at),
    )
    conn.commit()
    conn.close()
    return LoginOut(token=token)


@app.post("/logout")
def logout(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE user_id = ? AND token = ?", (user["id"], x_auth_token))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/me")
def me(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM tenants WHERE id = ?", (user["tenant_id"],))
    tenant = cur.fetchone()
    conn.close()
    return {
        "email": user["email"],
        "tenant": tenant["name"] if tenant else "Cabinet",
        "role": user["role"],
    }


@app.get("/users", response_model=list[UserOut])
def list_users(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, role, created_at FROM users WHERE tenant_id = ?", (user["tenant_id"],))
    rows = cur.fetchall()
    conn.close()
    return [UserOut(**dict(r)) for r in rows]


@app.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    role = payload.role.lower()
    if role not in {"admin", "accountant", "client"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, tenant_id, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (payload.email, user["tenant_id"], role, hash_password(payload.password), datetime.utcnow().isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return UserOut(id=new_id, email=payload.email, role=role, created_at=datetime.utcnow().isoformat())


@app.delete("/users/{user_id}")
def delete_user(user_id: int, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete self")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM users WHERE id = ? AND tenant_id = ?",
        (user_id, user["tenant_id"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/rules", response_model=list[RuleOut])
def list_rules(x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin", "accountant"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, keyword, account_code, account_label, created_at FROM account_rules WHERE tenant_id = ?",
        (user["tenant_id"],),
    )
    rows = cur.fetchall()
    conn.close()
    return [RuleOut(**dict(r)) for r in rows]


@app.post("/rules", response_model=RuleOut)
def create_rule(payload: RuleCreate, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO account_rules (tenant_id, keyword, account_code, account_label, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user["tenant_id"],
            payload.keyword.lower(),
            payload.account_code,
            payload.account_label,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return RuleOut(
        id=new_id,
        keyword=payload.keyword.lower(),
        account_code=payload.account_code,
        account_label=payload.account_label,
        created_at=datetime.utcnow().isoformat(),
    )


@app.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, x_auth_token: str | None = Header(default=None)):
    user = require_user(x_auth_token)
    require_role(user, {"admin"})
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM account_rules WHERE id = ? AND tenant_id = ?",
        (rule_id, user["tenant_id"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
