from __future__ import annotations
import json, os, re
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from core import *
from web import frontend

app=FastAPI(title='SudanCare Network', version='0.1.0', docs_url='/api/docs')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('SUDANCARE_ALLOWED_ORIGINS','http://localhost:8080').split(','), allow_credentials=True, allow_methods=['GET','POST'], allow_headers=['content-type'])
_login_windows={}

@app.middleware('http')
async def security_headers(request:Request, call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['X-Frame-Options']='DENY'; response.headers['Referrer-Policy']='same-origin'; response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    return response

@app.on_event('startup')
def startup(): init_db()

def auth(request: Request, roles=None):
    user=actor(request.cookies.get('sc_session'))
    if not user: raise HTTPException(401,'Authentication required')
    if roles and user['role'] not in roles: raise HTTPException(403,'Insufficient role')
    return user

class Credentials(BaseModel): username:str=Field(min_length=3,max_length=64); password:str=Field(min_length=12,max_length=128)
class Patient(BaseModel): name_ar:Optional[str]=None; name_en:Optional[str]=None; phone:Optional[str]=None; gender:Optional[str]=None; birth_date:Optional[str]=None; allergies:str=''; chronic_conditions:str=''; preferred_language:str='ar'; consent_whatsapp:bool=False
class Encounter(BaseModel): patient_id:str; chief_complaint:str=''; vitals:str=''; assessment:str=''; diagnosis:str=''; plan:str=''
class Payment(BaseModel): amount_minor:int=Field(gt=0); method:str; verification_ref:Optional[str]=None
class Facility(BaseModel): name_ar:str=Field(min_length=2,max_length=160); name_en:Optional[str]=None; city:Optional[str]=None; country:str='Sudan'; phone:Optional[str]=None; email:Optional[str]=None; facility_type:str='clinic'; privacy_accepted:bool=False
class Appointment(BaseModel): patient_id:str; department_id:Optional[str]=None; provider_id:Optional[str]=None; starts_at:int; ends_at:int; priority:str='routine'; reason:str=''
class LabOrder(BaseModel): patient_id:str; encounter_id:Optional[str]=None; test_id:str
class LabResult(BaseModel): result_value:str=Field(min_length=1,max_length=1000); abnormal_flag:str='normal'; critical_flag:bool=False
class RadiologyOrder(BaseModel): patient_id:str; encounter_id:Optional[str]=None; modality:str; body_region:str=''; priority:str='routine'
class RadiologyReport(BaseModel): report_text:str=Field(min_length=1,max_length=10000)
class Medicine(BaseModel): name_ar:str; name_en:Optional[str]=None; alias:Optional[str]=None; dosage_form:Optional[str]=None; unit:str
class Batch(BaseModel): medicine_id:str; batch_no:str; quantity:int=Field(gt=0); expires_on:Optional[str]=None; supplier:Optional[str]=None
class StockAdjustment(BaseModel): quantity_delta:int; note:str=Field(min_length=2,max_length=500)
class MessagePreview(BaseModel): patient_id:str; channel:str; template_key:str; preview:str; expires_at:Optional[int]=None
class Invoice(BaseModel): patient_id:str; total_minor:int=Field(gt=0)

@app.post('/setup')
def setup(data:Credentials):
    with db() as conn:
        if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone(): raise HTTPException(409,'Setup already completed')
        uid=new_id(); conn.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(uid,data.username,password_hash(data.password),'clinic_admin',1,0,None,now(),))
    audit(uid,'setup_completed','user',uid); return {'status':'created','username':data.username}

@app.post('/auth/login')
def login(data:Credentials,response:Response):
    key=data.username.lower(); attempts=_login_windows.get(key,[]); attempts=[x for x in attempts if x>now()-900]
    if len(attempts)>=10: raise HTTPException(429,'Too many login attempts; try again later')
    with db() as conn:
        u=conn.execute('SELECT * FROM users WHERE username=?',(data.username,)).fetchone()
        if not u or not u['active'] or (u['locked_until'] or 0)>now() or not password_matches(data.password,u['password_hash']):
            _login_windows[key]=attempts+[now()]
            if u: conn.execute('UPDATE users SET failed_attempts=failed_attempts+1,locked_until=CASE WHEN failed_attempts>=4 THEN ? ELSE locked_until END WHERE id=?',(now()+900,u['id']))
            raise HTTPException(401,'Invalid credentials')
        conn.execute('UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=?',(u['id'],))
    token=issue_token(u['id']); response.set_cookie('sc_session',token,httponly=True,secure=False,samesite='lax',max_age=3600); audit(u['id'],'login','user',u['id']); return {'role':u['role']}

@app.post('/auth/logout')
def logout(request:Request,response:Response):
    u=auth(request); response.delete_cookie('sc_session'); audit(u['id'],'logout','user',u['id']); return {'status':'ok'}

@app.get('/auth/me')
def me(request:Request):
    u=auth(request); return {'username':u['username'],'role':u['role']}

@app.get('/health')
def health(): return {'status':'ok','mode':os.getenv('SUDANCARE_MODE','clinic')}

@app.get('/')
def frontend_home(): return frontend()

@app.get('/patients')
def patients(request:Request,q:str=''):
    auth(request)
    with db() as conn:
        rows=conn.execute("SELECT * FROM patients WHERE mrn LIKE ? OR name_ar LIKE ? OR name_en LIKE ? OR phone LIKE ? ORDER BY created_at DESC LIMIT 50", tuple(['%'+q+'%']*4)).fetchall()
    return [dict(x) for x in rows]

@app.post('/patients')
def create_patient(data:Patient,request:Request):
    u=auth(request,['receptionist','nurse','doctor','clinic_admin']);
    if not (data.name_ar or data.name_en): raise HTTPException(422,'An Arabic or English name is required')
    pid=new_id(); mrn='SC-'+str(now())[-8:]+'-'+pid[:4].upper()
    with db() as conn: conn.execute('INSERT INTO patients VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(pid,mrn,data.name_ar,data.name_en,data.phone,data.gender,data.birth_date,data.allergies,data.chronic_conditions,data.preferred_language,int(data.consent_whatsapp),now()))
    audit(u['id'],'patient_created','patient',pid); queue('patient.upsert',{'id':pid}); return {'id':pid,'mrn':mrn}

@app.post('/facilities')
def create_facility(data:Facility,request:Request):
    u=auth(request,['clinic_admin','system_admin']); fid=new_id()
    with db() as conn: conn.execute('INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(fid,data.name_ar,data.name_en,data.city,data.country,data.phone,data.email,data.facility_type,'active','trial',now() if data.privacy_accepted else None,now()))
    audit(u['id'],'facility_created','facility',fid); return {'id':fid,'status':'active'}

@app.get('/appointments')
def list_appointments(request:Request,status:Optional[str]=None):
    auth(request)
    with db() as conn: rows=conn.execute('SELECT * FROM appointments WHERE (? IS NULL OR status=?) ORDER BY starts_at',(status,status)).fetchall()
    return [dict(x) for x in rows]

@app.post('/appointments')
def book_appointment(data:Appointment,request:Request):
    u=auth(request,['receptionist','clinic_admin'])
    if data.ends_at<=data.starts_at: raise HTTPException(422,'Appointment end must follow start')
    with db() as conn:
        clash=conn.execute('SELECT id FROM appointments WHERE provider_id IS ? AND status="booked" AND starts_at<? AND ends_at>?',(data.provider_id,data.ends_at,data.starts_at)).fetchone()
        if data.provider_id and clash: raise HTTPException(409,'Provider schedule conflict')
        aid=new_id(); q='Q-'+str(now())[-4:]; conn.execute('INSERT INTO appointments VALUES(?,?,?,?,?,?,?,?,?,?,?)',(aid,data.patient_id,data.department_id,data.provider_id,data.starts_at,data.ends_at,data.priority,'booked',q,data.reason,now()))
    audit(u['id'],'appointment_booked','appointment',aid); queue('appointment.upsert',{'id':aid}); return {'id':aid,'queue_number':q,'status':'booked'}

@app.post('/appointments/{appointment_id}/{transition}')
def appointment_transition(appointment_id:str,transition:str,request:Request):
    u=auth(request,['receptionist','nurse','doctor','clinic_admin']); allowed={'checked_in','cancelled','no_show','completed'}
    if transition not in allowed: raise HTTPException(422,'Unsupported visit status')
    with db() as conn:
        if not conn.execute('SELECT 1 FROM appointments WHERE id=?',(appointment_id,)).fetchone(): raise HTTPException(404,'Appointment not found')
        conn.execute('UPDATE appointments SET status=? WHERE id=?',(transition,appointment_id))
    audit(u['id'],'appointment_'+transition,'appointment',appointment_id); return {'status':transition}

@app.post('/lab/orders')
def order_lab(data:LabOrder,request:Request):
    u=auth(request,['doctor','clinic_admin']); oid=new_id(); accession='LAB-'+str(now())[-8:]+'-'+oid[:4].upper()
    with db() as conn: conn.execute('INSERT INTO lab_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(oid,data.patient_id,data.encounter_id,data.test_id,'ordered',accession,None,None,None,0,None,None,now()))
    audit(u['id'],'lab_ordered','lab_order',oid); return {'id':oid,'accession_number':accession,'status':'ordered'}

@app.post('/lab/orders/{order_id}/collect')
def collect_lab(order_id:str,request:Request):
    u=auth(request,['laboratory','clinic_admin'])
    with db() as conn:
        changed=conn.execute('UPDATE lab_orders SET status="collected",collected_at=? WHERE id=? AND status="ordered"',(now(),order_id)).rowcount
    if not changed: raise HTTPException(409,'Order is not available for collection')
    audit(u['id'],'lab_collected','lab_order',order_id); return {'status':'collected'}

@app.post('/lab/orders/{order_id}/result')
def result_lab(order_id:str,data:LabResult,request:Request):
    u=auth(request,['laboratory','clinic_admin'])
    with db() as conn:
        changed=conn.execute('UPDATE lab_orders SET status="result_entered",result_value=?,abnormal_flag=?,critical_flag=? WHERE id=? AND status IN ("collected","processing")',(data.result_value,data.abnormal_flag,int(data.critical_flag),order_id)).rowcount
    if not changed: raise HTTPException(409,'Result requires a collected or processing order')
    audit(u['id'],'lab_result_entered','lab_order',order_id); return {'status':'result_entered'}

@app.post('/lab/orders/{order_id}/release')
def release_lab(order_id:str,request:Request):
    u=auth(request,['laboratory','clinic_admin'])
    with db() as conn:
        changed=conn.execute('UPDATE lab_orders SET status="released",validated_by=?,released_at=? WHERE id=? AND status="result_entered"',(u['id'],now(),order_id)).rowcount
    if not changed: raise HTTPException(409,'Only entered results may be released')
    audit(u['id'],'lab_result_released','lab_order',order_id); queue('lab_result.released',{'id':order_id}); return {'status':'released'}

@app.get('/lab/orders')
def list_lab_orders(request:Request):
    auth(request,['laboratory','doctor','clinic_manager','clinic_admin'])
    with db() as conn: return [dict(r) for r in conn.execute('SELECT * FROM lab_orders ORDER BY created_at DESC LIMIT 100').fetchall()]

@app.post('/radiology/orders')
def order_radiology(data:RadiologyOrder,request:Request):
    u=auth(request,['doctor','clinic_admin']); oid=new_id()
    with db() as conn: conn.execute('INSERT INTO radiology_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(oid,data.patient_id,data.encounter_id,data.modality,data.body_region,data.priority,'ordered',None,None,None,None,now()))
    audit(u['id'],'radiology_ordered','radiology_order',oid); return {'id':oid,'status':'ordered','device_connected':False}

@app.post('/radiology/orders/{order_id}/report')
def draft_radiology_report(order_id:str,data:RadiologyReport,request:Request):
    u=auth(request,['radiology','clinic_admin'])
    with db() as conn: changed=conn.execute('UPDATE radiology_orders SET status="report_draft",report_text=? WHERE id=? AND status IN ("ordered","performed","report_draft")',(data.report_text,order_id)).rowcount
    if not changed: raise HTTPException(409,'Report cannot be drafted in its current state')
    audit(u['id'],'radiology_report_drafted','radiology_order',order_id); return {'status':'report_draft'}

@app.post('/radiology/orders/{order_id}/approve')
def approve_radiology_report(order_id:str,request:Request):
    u=auth(request,['radiology','clinic_admin'])
    with db() as conn: changed=conn.execute('UPDATE radiology_orders SET status="approved",approved_by=?,approved_at=? WHERE id=? AND status="report_draft"',(u['id'],now(),order_id)).rowcount
    if not changed: raise HTTPException(409,'Only a draft report may be approved')
    audit(u['id'],'radiology_report_approved','radiology_order',order_id); queue('radiology_report.approved',{'id':order_id}); return {'status':'approved'}

@app.get('/radiology/orders')
def list_radiology_orders(request:Request):
    auth(request,['radiology','doctor','clinic_manager','clinic_admin'])
    with db() as conn: return [dict(r) for r in conn.execute('SELECT * FROM radiology_orders ORDER BY created_at DESC LIMIT 100').fetchall()]

@app.post('/inventory/medicines')
def create_medicine(data:Medicine,request:Request):
    u=auth(request,['pharmacist','clinic_admin']); mid=new_id()
    with db() as conn: conn.execute('INSERT INTO medicines VALUES(?,?,?,?,?,?,?,?)',(mid,data.name_ar,data.name_en,data.alias,data.dosage_form,data.unit,1,now()))
    audit(u['id'],'medicine_created','medicine',mid); return {'id':mid}

@app.post('/inventory/batches')
def receive_batch(data:Batch,request:Request):
    u=auth(request,['pharmacist','clinic_admin']); bid=new_id()
    with db() as conn:
        conn.execute('INSERT INTO stock_batches VALUES(?,?,?,?,?,?,?)',(bid,data.medicine_id,data.batch_no,data.quantity,data.expires_on,data.supplier,now()))
        conn.execute('INSERT INTO stock_moves VALUES(?,?,?,?,?,?,?)',(new_id(),bid,data.quantity,'received','Stock received',u['id'],now()))
    audit(u['id'],'stock_received','stock_batch',bid); return {'id':bid,'quantity':data.quantity}

@app.post('/inventory/batches/{batch_id}/adjust')
def adjust_stock(batch_id:str,data:StockAdjustment,request:Request):
    u=auth(request,['pharmacist','clinic_admin'])
    with db() as conn:
        row=conn.execute('SELECT quantity,expires_on FROM stock_batches WHERE id=?',(batch_id,)).fetchone()
        if not row: raise HTTPException(404,'Stock batch not found')
        if row['quantity']+data.quantity_delta<0: raise HTTPException(409,'Stock cannot fall below zero')
        if data.quantity_delta<0 and row['expires_on'] and row['expires_on']<__import__('datetime').date.today().isoformat(): raise HTTPException(409,'Expired stock cannot be dispensed')
        conn.execute('UPDATE stock_batches SET quantity=quantity+? WHERE id=?',(data.quantity_delta,batch_id))
        conn.execute('INSERT INTO stock_moves VALUES(?,?,?,?,?,?,?)',(new_id(),batch_id,data.quantity_delta,'adjustment',data.note,u['id'],now()))
    audit(u['id'],'stock_adjusted','stock_batch',batch_id,data.note); return {'status':'recorded'}

@app.get('/inventory/alerts')
def inventory_alerts(request:Request,threshold:int=10):
    auth(request,['pharmacist','clinic_manager','clinic_admin'])
    with db() as conn: rows=conn.execute('SELECT b.*,m.name_ar,m.name_en FROM stock_batches b JOIN medicines m ON b.medicine_id=m.id WHERE b.quantity<=? OR (b.expires_on IS NOT NULL AND b.expires_on<=date("now","+30 days"))',(threshold,)).fetchall()
    return [dict(x) for x in rows]

@app.get('/inventory/batches')
def list_stock(request:Request):
    auth(request,['pharmacist','clinic_manager','clinic_admin'])
    with db() as conn: return [dict(x) for x in conn.execute('SELECT b.*,m.name_ar,m.name_en FROM stock_batches b JOIN medicines m ON b.medicine_id=m.id ORDER BY b.created_at DESC LIMIT 100').fetchall()]

@app.post('/communications/preview')
def preview_message(data:MessagePreview,request:Request):
    u=auth(request,['receptionist','clinic_admin']); mid=new_id()
    if data.channel not in {'whatsapp','sms','email'}: raise HTTPException(422,'Unsupported communication channel')
    with db() as conn: conn.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',(mid,data.patient_id,data.channel,data.template_key,data.preview,'draft',data.expires_at,now()))
    audit(u['id'],'message_previewed','message',mid); return {'id':mid,'status':'draft','delivery':'not_sent—credentials and approved templates required'}

@app.get('/reports/summary')
def report_summary(request:Request,from_ts:int=0,to_ts:int=2147483647):
    auth(request,['clinic_manager','clinic_admin','central_admin','system_admin'])
    with db() as conn:
        visits=conn.execute('SELECT COUNT(*) c FROM encounters WHERE created_at BETWEEN ? AND ?',(from_ts,to_ts)).fetchone()['c']
        waiting=conn.execute('SELECT COUNT(*) c FROM appointments WHERE status IN ("booked","checked_in")').fetchone()['c']
        revenue=conn.execute('SELECT COALESCE(SUM(verified_paid_minor),0) c FROM invoices WHERE created_at BETWEEN ? AND ?',(from_ts,to_ts)).fetchone()['c']
        low=conn.execute('SELECT COUNT(*) c FROM stock_batches WHERE quantity<=10').fetchone()['c']
    return {'deidentified':True,'visits':visits,'waiting_patients':waiting,'verified_revenue_minor':revenue,'low_stock_batches':low}

@app.get('/exports/patients')
def export_patients(request:Request):
    auth(request,['clinic_admin','central_admin','system_admin'])
    with db() as conn: rows=[dict(r) for r in conn.execute('SELECT id,mrn,name_ar,name_en,phone,gender,birth_date FROM patients').fetchall()]
    audit(actor(request.cookies.get('sc_session'))['id'],'patient_exported','export'); return {'format':'json','data':rows}

@app.get('/sync/conflicts')
def sync_conflicts(request:Request):
    auth(request,['clinic_admin','central_admin','system_admin'])
    with db() as conn: return [dict(r) for r in conn.execute('SELECT * FROM sync_conflicts WHERE state="needs_review"').fetchall()]

@app.post('/encounters')
def create_encounter(data:Encounter,request:Request):
    u=auth(request,['doctor','clinic_admin']); eid=new_id()
    with db() as conn: conn.execute('INSERT INTO encounters VALUES(?,?,?,?,?,?,?,?,?,?,?)',(eid,data.patient_id,'draft',data.chief_complaint,data.vitals,data.assessment,data.diagnosis,data.plan,None,None,now()))
    audit(u['id'],'encounter_drafted','encounter',eid); return {'id':eid,'status':'draft'}

@app.post('/encounters/{encounter_id}/sign')
def sign(encounter_id:str,request:Request):
    u=auth(request,['doctor'])
    with db() as conn:
        e=conn.execute('SELECT * FROM encounters WHERE id=?',(encounter_id,)).fetchone()
        if not e: raise HTTPException(404,'Encounter not found')
        if e['status']!='draft': raise HTTPException(409,'Signed records require an addendum, not editing')
        conn.execute('UPDATE encounters SET status="signed",signed_by=?,signed_at=? WHERE id=?',(u['id'],now(),encounter_id))
    audit(u['id'],'encounter_signed','encounter',encounter_id); queue('encounter.signed',{'id':encounter_id}); return {'status':'signed'}

@app.post('/invoices/{invoice_id}/payments')
def payment(invoice_id:str,data:Payment,request:Request):
    u=auth(request,['cashier','clinic_admin']); pay_id=new_id()
    with db() as conn:
        inv=conn.execute('SELECT * FROM invoices WHERE id=?',(invoice_id,)).fetchone()
        if not inv: raise HTTPException(404,'Invoice not found')
        conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?)',(pay_id,invoice_id,data.amount_minor,data.method,data.verification_ref,'verified',now()))
        paid=inv['verified_paid_minor']+data.amount_minor; status='paid' if paid>=inv['total_minor'] else 'partially_paid'
        conn.execute('UPDATE invoices SET verified_paid_minor=?,status=? WHERE id=?',(paid,status,invoice_id))
    audit(u['id'],'payment_verified','invoice',invoice_id); return {'status':status,'verified_paid_minor':paid}

@app.get('/invoices')
def list_invoices(request:Request):
    auth(request,['cashier','clinic_manager','clinic_admin','central_admin','system_admin'])
    with db() as conn: return [dict(r) for r in conn.execute('SELECT * FROM invoices ORDER BY created_at DESC LIMIT 100').fetchall()]

@app.post('/invoices')
def create_invoice(data:Invoice,request:Request):
    u=auth(request,['cashier','clinic_admin']); iid=new_id()
    with db() as conn: conn.execute('INSERT INTO invoices VALUES(?,?,?,?,?,?)',(iid,data.patient_id,data.total_minor,0,'unpaid',now()))
    audit(u['id'],'invoice_created','invoice',iid); return {'id':iid,'status':'unpaid'}

def queue(kind,payload):
    with db() as conn: conn.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',(new_id(),kind,json.dumps(payload),new_id(),'queued',0,now(),now()))

@app.get('/sync/status')
def sync_status(request:Request):
    auth(request,['clinic_admin','system_admin'])
    with db() as conn: rows=conn.execute('SELECT state,COUNT(*) count FROM outbox GROUP BY state').fetchall()
    return {'mode':os.getenv('SUDANCARE_MODE','clinic'),'queue':{r['state']:r['count'] for r in rows},'note':'Transport worker is intentionally not enabled in this pilot foundation.'}

@app.get('/legacy',response_class=HTMLResponse)
def home():
    return '''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SudanCare</title><style>
*{box-sizing:border-box}body{margin:0;font:16px system-ui,-apple-system,sans-serif;background:#f3f7f6;color:#14332e}header{padding:20px max(20px,calc((100% - 1120px)/2));background:#067968;color:#fff;display:flex;justify-content:space-between;align-items:center}main{max-width:1120px;margin:26px auto;padding:0 20px}.card{background:#fff;border:1px solid #d9e8e4;border-radius:14px;padding:20px;box-shadow:0 3px 15px #14332e0c}.auth{max-width:460px;margin:8vh auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.stat{font-size:30px;font-weight:750;color:#067968}input,select,textarea,button{padding:12px;margin:6px 0;border-radius:8px;border:1px solid #b6d3cd;width:100%;font:inherit}button{background:#067968;color:#fff;border:0;font-weight:700;cursor:pointer}button.alt{background:#fff;color:#067968;border:1px solid #067968}.hide{display:none}.muted{color:#526a65}.error{color:#a52a2a}.ok{color:#067968}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #e1ece9;text-align:right}@media(max-width:600px){header{padding:15px}main{padding:0 12px}}
</style></head><body><header><div><b>SudanCare Network</b><br><small>شبكة سودان كير للرعاية الصحية</small></div><button id="logout" class="alt hide" style="width:auto" onclick="signout()">تسجيل الخروج</button></header><main>
<section id="auth" class="card auth"><h1>ابدأ العمل</h1><p class="muted">Local-first Clinic Edition</p><div id="login"><input id="user" placeholder="اسم المستخدم / Username"><input id="pass" type="password" placeholder="كلمة المرور / Password"><button onclick="signin()">تسجيل الدخول</button><button class="alt" onclick="toggleSetup()">إعداد عيادة جديدة</button></div><div id="setup" class="hide"><input id="setupUser" placeholder="اسم مستخدم المسؤول"><input id="setupPass" type="password" placeholder="كلمة مرور (12 حرفًا على الأقل)"><button onclick="createAdmin()">إنشاء المسؤول</button><button class="alt" onclick="toggleSetup()">عودة للدخول</button></div><p id="message" role="status"></p></section>
<section id="workspace" class="hide"><h1>لوحة المتابعة</h1><p id="welcome" class="muted"></p><div class="grid"><div class="card"><div class="stat" id="visits">—</div><div>الزيارات / Visits</div></div><div class="card"><div class="stat" id="waiting">—</div><div>في الانتظار / Waiting</div></div><div class="card"><div class="stat" id="stock">—</div><div>تنبيهات المخزون / Stock alerts</div></div></div><br><div class="grid"><section class="card"><h2>تسجيل مريض</h2><input id="nameAr" placeholder="الاسم بالعربية"><input id="nameEn" placeholder="Name in English"><input id="phone" placeholder="الهاتف"><button onclick="addPatient()">حفظ المريض</button><p id="patientMsg"></p></section><section class="card"><h2>بحث المرضى</h2><input id="query" oninput="findPatients()" placeholder="الاسم، الهاتف، أو الرقم الطبي"><div id="patients" class="muted">ابدأ بالبحث</div></section></div><br><section class="card"><h2>الزيارات والمواعيد</h2><table><thead><tr><th>الطابور</th><th>الحالة</th><th>الوقت</th></tr></thead><tbody id="appointments"></tbody></table></section></section>
</main><script>
const msg=x=>{message.textContent=x;message.className='error'};async function api(url,opt={}){let r=await fetch(url,{headers:{'content-type':'application/json'},...opt});let d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'حدث خطأ');return d}function toggleSetup(){setup.classList.toggle('hide');login.classList.toggle('hide');message.textContent=''}async function createAdmin(){try{await api('/setup',{method:'POST',body:JSON.stringify({username:setupUser.value,password:setupPass.value})});toggleSetup();message.className='ok';message.textContent='تم إنشاء المسؤول. يمكنك تسجيل الدخول الآن.'}catch(e){msg(e.message)}}async function signin(){try{await api('/auth/login',{method:'POST',body:JSON.stringify({username:user.value,password:pass.value})});await load(true)}catch(e){msg(e.message)}}async function signout(){await api('/auth/logout',{method:'POST'});location.reload()}async function load(showError=false){try{let me=await api('/auth/me');auth.classList.add('hide');workspace.classList.remove('hide');logout.classList.remove('hide');welcome.textContent='مرحبًا '+me.username+' · '+me.role;let s=await api('/reports/summary');visits.textContent=s.visits;waiting.textContent=s.waiting_patients;stock.textContent=s.low_stock_batches;let a=await api('/appointments');appointments.innerHTML=a.length?a.map(x=>`<tr><td>${x.queue_number||'—'}</td><td>${x.status}</td><td>${new Date(x.starts_at*1000).toLocaleString()}</td></tr>`).join(''):'<tr><td colspan=3 class=muted>لا توجد مواعيد</td></tr>'}catch(e){if(showError){msg('تعذر فتح لوحة العمل: '+e.message)}}}async function addPatient(){try{let p=await api('/patients',{method:'POST',body:JSON.stringify({name_ar:nameAr.value,name_en:nameEn.value,phone:phone.value})});patientMsg.className='ok';patientMsg.textContent='تم الحفظ · '+p.mrn;findPatients();load()}catch(e){patientMsg.className='error';patientMsg.textContent=e.message}}async function findPatients(){try{let rows=await api('/patients?q='+encodeURIComponent(query.value));patients.innerHTML=rows.length?'<table>'+rows.map(x=>`<tr><td>${x.mrn}</td><td>${x.name_ar||x.name_en||''}</td><td>${x.phone||''}</td></tr>`).join('')+'</table>':'لا توجد نتائج'}catch(e){}}load();
</script></body></html>'''
