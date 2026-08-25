"""Create synthetic, explicitly temporary demo data for a fresh local database."""
from app.core import db, init_db, new_id, now, password_hash

init_db()
with db() as conn:
    if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
        raise SystemExit('Demo data can only be seeded into an empty database.')
    admin_id=new_id()
    conn.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(admin_id,'demo.admin',password_hash('DemoOnly-ChangeMe-2026'),'clinic_admin',1,0,None,now()))
    patient_id=new_id()
    conn.execute('INSERT INTO patients VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(patient_id,'SC-DEMO-0001','مريضة تجريبية','Demo Patient','0900000000','female','1990-01-01','No known allergies','', 'ar',0,now()))
print('Created synthetic demo account demo.admin. Change its password before any use.')
