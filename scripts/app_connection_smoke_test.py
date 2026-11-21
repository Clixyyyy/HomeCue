"""Website and Flutter integration, using a throwaway shared database."""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8898'
with tempfile.TemporaryDirectory(prefix='homecue-app-test-') as directory:
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(Path(directory) / 'test.db'), HOMECUE_JWT_SECRET='homecue-cross-client-test-secret-not-production-123456789')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8898'], cwd=ROOT / 'backend', env=env, stdout=subprocess.DEVNULL)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
            context = browser.new_context(viewport={'width':430,'height':932})
            site = context.new_page()
            for _ in range(60):
                try:
                    site.goto(URL)
                    break
                except Exception:
                    time.sleep(.2)
            site.get_by_role('button',name='My Home',exact=True).click()
            site.locator('#authForm input[name=email]').fill('connected@example.com')
            site.locator('#authForm input[name=password]').fill('ConnectedPassword123!')
            site.locator('#authForm button[value=register]').click()
            site.locator('#createHome input[name=name]').fill('Connected demo home')
            site.locator('#createHome button[type=submit]').click()
            site.get_by_text('Hello, Caregiver.',exact=True).wait_for()
            app = context.new_page()
            errors = []
            app.on('pageerror',lambda error: errors.append(str(error)))
            app.goto(URL+'/app/')
            app.locator('flt-semantics-placeholder').wait_for(state='attached',timeout=60000)
            app.locator('flt-semantics-placeholder').evaluate('(el)=>el.click()')
            email_field=app.get_by_role('textbox',name='Email',exact=True)
            email_field.click()
            email_field.press_sequentially('connected@example.com',delay=25)
            email_field.press('Tab')
            password_field=app.get_by_role('textbox',name='Password',exact=True)
            password_field.click()
            password_field.press_sequentially('ConnectedPassword123!',delay=25)
            app.get_by_role('textbox',name='Password',exact=True).press('Tab')
            try:
                with app.expect_response(lambda r: '/api/homes/1' in r.url and '/members' not in r.url and '/events' not in r.url) as response:
                    app.get_by_role('button',name='Sign in',exact=True).click()
                assert response.value.json()['name']=='Connected demo home'
            except Exception:
                print(app.locator('body').inner_text(),errors,flush=True)
                raise
            expect(app.get_by_text('Hi, Caregiver.',exact=False)).to_be_visible(timeout=20000)
            print('PASS website account and home load in Flutter',flush=True)
            site.locator('[data-action="tab:activity"]').first.click()
            site.locator('[data-action="demo-event"]').click()
            site.get_by_text('DEMO',exact=True).wait_for()
            app.get_by_role('tab',name='Activity',exact=True).click()
            expect(app.get_by_text('Recent events.',exact=False)).to_be_visible()
            expect(app.get_by_role('checkbox',name='DEMO',exact=True)).to_be_visible(timeout=20000)
            print('PASS website demo event automatically appears in app',flush=True)
            app.get_by_role('button',name='Create clearly labelled demo event').click()
            expect(app.get_by_role('checkbox',name='DEMO',exact=True)).to_have_count(2)
            site.locator('[data-action="tab:activity"]').first.click()
            expect(site.get_by_text('DEMO',exact=True)).to_have_count(2)
            print('PASS app event appears on website',flush=True)
            app.get_by_role('tab',name='Plans',exact=True).click()
            app.get_by_role('button',name='Buy Starter',exact=True).click()
            app.get_by_role('button',name='Place demo order',exact=True).click()
            app.get_by_role('button',name='Complete demo payment',exact=True).click()
            expect(app.get_by_text('Demo order complete',exact=True)).to_be_visible()
            app.get_by_role('button',name='Done',exact=True).click()
            print('PASS app packages and demo checkout',flush=True)
            app.get_by_role('tab',name='Home',exact=True).click()
            expect(app.get_by_role('group',name=re.compile(r'^PURCHASED · DEMO Starter plan'))).to_be_visible(timeout=20000)
            site.get_by_role('button',name='My Home',exact=True).click()
            site.get_by_role('heading',name='Starter plan',exact=True).wait_for()
            site.locator('[data-action="tab:setup"]').first.click()
            assert site.locator('#mod-task').is_enabled()
            assert site.locator('#mod-night').is_disabled()
            print('PASS app purchase persists on website and locks excluded settings',flush=True)
            site.get_by_role('button',name='Pricing',exact=True).click()
            site.get_by_role('button',name='Customize Complete ↗',exact=True).click()
            site.locator('input[name=custom_option][value=night]').check()
            site.locator('input[name=custom_option][value=escalation]').check()
            site.locator('#checkoutForm input[name=name]').fill('Caregiver')
            site.locator('#checkoutForm input[name=email]').fill('connected@example.com')
            site.get_by_role('button',name='Pay for custom plan (demo)',exact=True).click()
            site.get_by_role('heading',name='Your custom configuration is ready.').wait_for()
            expect(app.get_by_role('group',name=re.compile(r'^PURCHASED · DEMO Custom Complete plan'))).to_be_visible(timeout=20000)
            app.get_by_role('tab',name='Setup',exact=True).click()
            expect(app.get_by_role('switch').nth(0)).to_be_disabled()
            expect(app.get_by_role('switch').nth(1)).to_be_enabled()
            print('PASS website custom purchase refreshes into app with matching entitlements',flush=True)
            app.screenshot(path=str(ROOT/'HomeCue_App_Preview.png'))
            assert not errors,errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
