"""Anonymous custom builder: visible quotes and preset price parity."""
import os, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='hc-quote-') as d:
 env=dict(os.environ,DATABASE_URL='sqlite:///'+str(Path(d)/'test.db'),HOMECUE_JWT_SECRET='custom-builder-local-test-secret-12345678901234567890')
 server=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--port','8899'],cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
   for viewport in [{'width':1440,'height':1000},{'width':390,'height':844}]:
    page=browser.new_page(viewport=viewport);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    for _ in range(50):
     try:page.goto('http://127.0.0.1:8899/checkout-complete');break
     except Exception:time.sleep(.2)
    expect(page.get_by_role('heading',name='Build your own HomeCue.')).to_be_visible()
    price=page.locator('#live-custom-price');expect(price).to_contain_text('₹199/month')
    previous=5198
    for code in ['task','orientation','night','entrance','escalation']:
     page.locator(f'input[value={code}]').check();total=int(page.locator('#checkoutForm').get_attribute('data-total'));assert total>previous;previous=total
     expect(price).to_contain_text('functions selected')
    page.locator('select[name=zones]').select_option('3');page.locator('select[name=caregivers]').select_option('3')
    expect(price).to_contain_text('₹999/month');assert page.locator('#checkoutForm').get_attribute('data-total')=='25998'
    for code in ['night','entrance','escalation']:page.locator(f'input[value={code}]').uncheck()
    page.locator('select[name=zones]').select_option('1');page.locator('select[name=caregivers]').select_option('1')
    expect(price).to_contain_text('₹499/month');assert page.locator('#checkoutForm').get_attribute('data-total')=='15498'
    page.reload();expect(price).to_contain_text('₹499/month')
    page.screenshot(path=str(ROOT/f"HomeCue_Custom_{viewport['width']}.png"),full_page=True)
    page.locator('#checkoutForm input[name=name]').fill('Demo buyer');page.locator('#checkoutForm input[name=email]').fill('buyer@example.com');page.get_by_role('button',name='Pay for custom plan (demo)').click()
    expect(page.get_by_text('Welcome back.',exact=True)).to_be_visible()
    assert not errors,errors
    print('PASS public builder, each click increases total, Starter/Family parity, persisted choices, sign-in at payment:',viewport['width'],flush=True)
    page.close()
   browser.close()
 finally:
  server.terminate();server.wait(timeout=10)
