from __future__ import annotations
import base64, hashlib, hmac, os, secrets, sqlite3, time, uuid
from contextlib import contextmanager

DB_PATH = os.getenv("SUDANCARE_DB_PATH", "./sudancare.db")
SECRET = os.getenv("SUDANCARE_SECRET", "development-only-change-me").encode()

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS facilities (id TEXT PRIMARY KEY, name_ar TEXT NOT NULL, name_en TEXT, city TEXT, country TEXT NOT NULL DEFAULT 'Sudan', phone TEXT, email TEXT, facility_type TEXT NOT NULL DEFAULT 'clinic', status TEXT NOT NULL DEFAULT 'active', subscription_status TEXT NOT NULL DEFAULT 'trial', privacy_accepted_at INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS departments (id TEXT PRIMARY KEY, facility_id TEXT NOT NULL, name_ar TEXT NOT NULL, name_en TEXT, active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, FOREIGN KEY(facility_id) REFERENCES facilities(id));
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS patients (id TEXT PRIMARY KEY, mrn TEXT UNIQUE NOT NULL, name_ar TEXT, name_en TEXT, phone TEXT, gender TEXT, birth_date TEXT, allergies TEXT, chronic_conditions TEXT, preferred_language TEXT DEFAULT 'ar', consent_whatsapp INTEGER DEFAULT 0, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS encounters (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, status TEXT NOT NULL, chief_complaint TEXT, vitals TEXT, assessment TEXT, diagnosis TEXT, plan TEXT, signed_by TEXT, signed_at INTEGER, created_at INTEGER NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS invoices (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, total_minor INTEGER NOT NULL, verified_paid_minor INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, created_at INTEGER NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL, amount_minor INTEGER NOT NULL, method TEXT NOT NULL, verification_ref TEXT, status TEXT NOT NULL, created_at INTEGER NOT NULL, FOREIGN KEY(invoice_id) REFERENCES invoices(id));
CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY, actor_id TEXT, action TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT, details TEXT, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, state TEXT NOT NULL DEFAULT 'queued', retries INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS appointments (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, department_id TEXT, provider_id TEXT, starts_at INTEGER NOT NULL, ends_at INTEGER NOT NULL, priority TEXT NOT NULL DEFAULT 'routine', status TEXT NOT NULL DEFAULT 'booked', queue_number TEXT, reason TEXT, created_at INTEGER NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS lab_tests (id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name_ar TEXT NOT NULL, name_en TEXT, reference_range TEXT, active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lab_orders (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, encounter_id TEXT, test_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ordered', accession_number TEXT UNIQUE, collected_at INTEGER, result_value TEXT, abnormal_flag TEXT, critical_flag INTEGER NOT NULL DEFAULT 0, validated_by TEXT, released_at INTEGER, created_at INTEGER NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS radiology_orders (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, encounter_id TEXT, modality TEXT NOT NULL, body_region TEXT, priority TEXT NOT NULL DEFAULT 'routine', status TEXT NOT NULL DEFAULT 'ordered', report_text TEXT, approved_by TEXT, approved_at INTEGER, attachment_url TEXT, created_at INTEGER NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS medicines (id TEXT PRIMARY KEY, name_ar TEXT NOT NULL, name_en TEXT, alias TEXT, dosage_form TEXT, unit TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS stock_batches (id TEXT PRIMARY KEY, medicine_id TEXT NOT NULL, batch_no TEXT NOT NULL, quantity INTEGER NOT NULL, expires_on TEXT, supplier TEXT, created_at INTEGER NOT NULL, FOREIGN KEY(medicine_id) REFERENCES medicines(id));
CREATE TABLE IF NOT EXISTS stock_moves (id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, quantity_delta INTEGER NOT NULL, kind TEXT NOT NULL, note TEXT, actor_id TEXT, created_at INTEGER NOT NULL, FOREIGN KEY(batch_id) REFERENCES stock_batches(id));
CREATE TABLE IF NOT EXISTS services (id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name_ar TEXT NOT NULL, name_en TEXT, price_minor INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, channel TEXT NOT NULL, template_key TEXT NOT NULL, preview TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', expires_at INTEGER, created_at INTEGER NOT NULL, FOREIGN KEY(patient_id) REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS sync_conflicts (id TEXT PRIMARY KEY, event_id TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL, local_payload TEXT NOT NULL, remote_payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'needs_review', resolved_by TEXT, created_at INTEGER NOT NULL);
'''

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try: yield conn; conn.commit()
    finally: conn.close()

def init_db():
    with db() as conn: conn.executescript(SCHEMA)

def now(): return int(time.time())
def new_id(): return str(uuid.uuid4())

def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310000)
    return base64.b64encode(salt + digest).decode()

def password_matches(password: str, stored: str) -> bool:
    raw = base64.b64decode(stored); return hmac.compare_digest(password_hash(password, raw[:16]), stored)

def issue_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32); digest = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn: conn.execute('INSERT INTO sessions VALUES (?, ?, ?)', (digest, user_id, now()+3600))
    return token

def actor(token: str | None):
    if not token: return None
    with db() as conn:
        row=conn.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()
        return dict(row) if row else None

def audit(actor_id, action, object_type, object_id=None, details=''):
    with db() as conn: conn.execute('INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)',(new_id(),actor_id,action,object_type,object_id,details,now()))
