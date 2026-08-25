import os, tempfile, unittest
from fastapi.testclient import TestClient

os.environ['SUDANCARE_DB_PATH'] = tempfile.mktemp(suffix='.db')
from app.main import app
from app.core import db, new_id, now, password_hash

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        with db() as conn:
            exists=conn.execute('SELECT 1 FROM users WHERE username="adminuser"').fetchone()
        if not exists:
            result=self.client.post('/setup',json={'username':'adminuser','password':'temporary-demo-password'})
            self.assertEqual(result.status_code,200)
        with db() as conn: conn.execute('UPDATE users SET role="clinic_admin" WHERE username="adminuser"')
        self.assertEqual(self.client.post('/auth/login',json={'username':'adminuser','password':'temporary-demo-password'}).status_code,200)

    def tearDown(self): self.client.__exit__(None,None,None)

    def test_patient_appointment_and_report(self):
        patient=self.client.post('/patients',json={'name_ar':'مريض اختباري','phone':'0911111111'}).json()
        booking=self.client.post('/appointments',json={'patient_id':patient['id'],'starts_at':1800000000,'ends_at':1800001800})
        self.assertEqual(booking.status_code,200)
        self.assertEqual(self.client.get('/reports/summary').status_code,200)
        self.assertEqual(self.client.get('/sync/status').status_code,200)

    def test_signed_encounter_is_immutable(self):
        patient=self.client.post('/patients',json={'name_en':'Test Patient'}).json()
        with db() as conn:
            conn.execute('UPDATE users SET role="doctor" WHERE username="adminuser"')
        encounter=self.client.post('/encounters',json={'patient_id':patient['id'],'diagnosis':'Draft diagnosis'}).json()
        self.assertEqual(self.client.post('/encounters/'+encounter['id']+'/sign').status_code,200)
        self.assertEqual(self.client.post('/encounters/'+encounter['id']+'/sign').status_code,409)

    def test_expired_stock_cannot_be_reduced(self):
        with db() as conn:
            conn.execute('UPDATE users SET role="pharmacist" WHERE username="adminuser"')
        med=self.client.post('/inventory/medicines',json={'name_ar':'دواء اختباري','unit':'tablet'}).json()
        batch=self.client.post('/inventory/batches',json={'medicine_id':med['id'],'batch_no':'EXPIRED-1','quantity':5,'expires_on':'2020-01-01'}).json()
        blocked=self.client.post('/inventory/batches/'+batch['id']+'/adjust',json={'quantity_delta':-1,'note':'Dispense'})
        self.assertEqual(blocked.status_code,409)
