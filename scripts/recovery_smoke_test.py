"""Verify password recovery UI without using or changing a real account."""
import os, sys, tempfile, subprocess, sqlite3, time, hmac, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jwt
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='hc-recovery-') as d:
 dbfile=Path(d)/'test.db';secret='browser-recovery-test-secret-1234567890123456789012345'
 env=dict(os.environ,DATABASE_URL='sqlite:///'+str(dbfile),HOMECUE_JWT_SECRET=secret)
 server=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--port','8900'],cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  with sync_playwright() as pw:
   b=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True);page=b.new_page()
   url='http://127.0.0.1:8900'
   for _ in range(50):
    try:page.goto(url);break
    except Exception:time.sleep(.2)
   account=page.request.post(url+'/api/auth/register',data={'email':'recovery-browser@example.com','password':'Original-password-123!'}).json()
   page.request.post(url+'/api/homes',headers={'Authorization':'Bearer '+account['token']},data={'name':'Preserved family home'})
   with sqlite3.connect(dbfile) as db:uid,pwhash=db.execute('select id,password_hash from users where email=?',('recovery-browser@example.com',)).fetchone()
   token=jwt.encode({'sub':str(uid),'purpose':'password_reset','pv':hmac.new(secret.encode(),pwhash.encode(),hashlib.sha256).hexdigest(),'exp':datetime.now(timezone.utc)+timedelta(minutes=15)},secret,algorithm='HS256')
   page.goto(url+'/reset-password#token='+token)
   expect(page.get_by_role('heading',name='Choose a new password.')).to_be_visible();assert '#' not in page.url
   page.locator('input[name=password]').fill('New-recovery-password-123!');page.locator('input[name=confirmation]').fill('Mismatch-password-123!')
   page.get_by_role('button',name='Save password and sign in').click();expect(page.locator('#reset-error')).to_contain_text('do not match')
   page.locator('input[name=confirmation]').fill('New-recovery-password-123!');page.get_by_role('button',name='Save password and sign in').click()
   expect(page.get_by_text('Preserved family home',exact=True)).to_be_visible()
   assert page.request.post(url+'/api/auth/login',data={'email':'recovery-browser@example.com','password':'New-recovery-password-123!'}).status==200
   assert page.request.post(url+'/api/auth/reset-password',data={'token':token,'new_password':'Another-recovery-password-123!'}).status==400
   print('PASS recovery form, confirmation validation, sign-in, preserved home, single-use token')
   b.close()
 finally:
  server.terminate();server.wait(timeout=10)
