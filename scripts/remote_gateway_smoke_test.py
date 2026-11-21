"""Local HTTPS test for the approved-account gateway; never opens a public tunnel."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='hc-gateway-browser-') as directory:
    temp=Path(directory)
    env=dict(os.environ,DATABASE_URL='sqlite:///'+str(temp/'test.db'),HOMECUE_JWT_SECRET='gateway-browser-test-only-secret-12345678901234567890',HOMECUE_REMOTE_EMAIL='remote-test@example.com')
    seed="""from fastapi.testclient import TestClient
from main import app
with TestClient(app) as c:
 r=c.post('/api/auth/register',json={'email':'remote-test@example.com','name':'RemoteTester','password':'Remote-test-password-123!'})
 assert r.status_code==201
 assert c.post('/api/homes',headers={'Authorization':'Bearer '+r.json()['token']},json={'name':'Remote shared home'}).status_code==201
"""
    subprocess.run([sys.executable,'-c',seed],cwd=ROOT/'backend',env=env,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(temp/'key.pem'),'-out',str(temp/'cert.pem'),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    server=subprocess.Popen([sys.executable,'-m','uvicorn','remote_gateway:create_app','--factory','--host','127.0.0.1','--port','8896','--ssl-keyfile',str(temp/'key.pem'),'--ssl-certfile',str(temp/'cert.pem')],cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
            context=browser.new_context(ignore_https_errors=True,viewport={'width':430,'height':932})
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            url='https://127.0.0.1:8896'
            for _ in range(50):
                try:page.goto(url+'/app/');break
                except Exception:time.sleep(.2)
            expect(page.get_by_role('heading',name='Sign in to your home.')).to_be_visible()
            page.get_by_label('Email',exact=True).fill('remote-test@example.com')
            page.get_by_label('HomeCue password',exact=True).fill('wrong')
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page.locator('#error')).to_contain_text('Incorrect email/password')
            page.get_by_label('HomeCue password',exact=True).fill('Remote-test-password-123!')
            page.screenshot(path=str(ROOT/'HomeCue_Remote_Signin_Preview.png'))
            page.get_by_role('button',name='Sign in',exact=True).click()
            page.wait_for_url(url+'/app/')
            page.locator('flt-semantics-placeholder').wait_for(state='attached',timeout=60000)
            page.locator('flt-semantics-placeholder').evaluate('(el)=>el.click()')
            expect(page.get_by_text('Hi, RemoteTester.',exact=False)).to_be_visible(timeout=30000)
            print('PASS protected sign-in opens Flutter app without a second login',flush=True)
            site=context.new_page()
            site.goto(url+'/dashboard')
            expect(site.get_by_text('Hello, RemoteTester.',exact=True)).to_be_visible()
            expect(site.get_by_text('Remote shared home',exact=True)).to_be_visible()
            print('PASS same protected session opens website and existing home',flush=True)
            site.get_by_role('button',name='Sign out',exact=True).click()
            expect(site.get_by_role('heading',name='Sign in to your home.')).to_be_visible()
            assert context.request.get(url+'/api/homes').status==401
            assert not errors,errors
            print('PASS remote sign-out locks the website and API',flush=True)
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10)
