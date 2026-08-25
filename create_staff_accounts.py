"""Create one temporary account for each clinic role; preserves existing users."""
from app.core import db, init_db, new_id, now, password_hash, audit

ACCOUNTS = {
    'reception': ('receptionist', 'Temp-Reception-2026!'),
    'nurse': ('nurse', 'Temp-Nurse-2026!'),
    'doctor': ('doctor', 'Temp-Doctor-2026!'),
    'laboratory': ('laboratory', 'Temp-Lab-2026!'),
    'radiology': ('radiology', 'Temp-Radiology-2026!'),
    'pharmacy': ('pharmacist', 'Temp-Pharmacy-2026!'),
    'cashier': ('cashier', 'Temp-Cashier-2026!'),
    'manager': ('clinic_manager', 'Temp-Manager-2026!'),
    'clinic.admin': ('clinic_admin', 'Temp-Admin-2026!'),
}

init_db()
created = []
with db() as conn:
    for username, (role, password) in ACCOUNTS.items():
        if conn.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            continue
        user_id = new_id()
        conn.execute(
            'INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',
            (user_id, username, password_hash(password), role, 1, 0, None, now()),
        )
        created.append((username, role))

for username, role in created:
    audit(None, 'staff_account_created', 'user', username, 'Temporary role account: ' + role)
print('Created: ' + ', '.join(username for username, _ in created) if created else 'All role accounts already exist.')
