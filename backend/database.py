import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "comptaflow.db"
UPLOADS_DIR = BASE_DIR / "uploads"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def init_db():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            vendor TEXT NOT NULL,
            doc_date TEXT NOT NULL,
            amount_ttc REAL NOT NULL,
            vat REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            tenant_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS account_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            account_code TEXT NOT NULL,
            account_label TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            txn_date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            plan_id TEXT NOT NULL,
            status TEXT NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            level TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS email_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            to_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            bank_txn_id INTEGER NOT NULL,
            match_score REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    if not _column_exists(cur, "documents", "tenant_id"):
        cur.execute("ALTER TABLE documents ADD COLUMN tenant_id INTEGER DEFAULT 1")
    if not _column_exists(cur, "users", "tenant_id"):
        cur.execute("ALTER TABLE users ADD COLUMN tenant_id INTEGER DEFAULT 1")
    if not _column_exists(cur, "users", "role"):
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
    if not _column_exists(cur, "users", "password_salt"):
        cur.execute("ALTER TABLE users ADD COLUMN password_salt TEXT")
    if not _column_exists(cur, "sessions", "expires_at"):
        cur.execute("ALTER TABLE sessions ADD COLUMN expires_at TEXT DEFAULT ''")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bank_tenant ON bank_transactions(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bank_date ON bank_transactions(txn_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rules_tenant ON account_rules(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rules_keyword ON account_rules(keyword)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_tenant ON tickets(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_tenant ON notifications(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_tenant ON email_queue(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON subscriptions(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_updated ON subscriptions(updated_at)")
    conn.commit()
    conn.close()
