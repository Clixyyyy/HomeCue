"""Optional local check for HomeCue website. Requires Playwright + Chromium."""
import os, subprocess, sys, tempfile, time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = "8897"
with tempfile.TemporaryDirectory(prefix="hc-browser-") as d:
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///" + str(Path(d) / "smoke.db")
    env["HOMECUE_JWT_SECRET"] = "browser-smoke-secret-unique-local-test-only-556677889900"
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", PORT], cwd=ROOT/"backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        with sync_playwright() as pw:
            executable = os.environ.get("HOMECUE_BROWSER_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
            mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            if not executable and mac_chrome.exists():
                executable = str(mac_chrome)
            browser = pw.chromium.launch(headless=True, executable_path=executable, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--no-proxy-server"])
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page.set_default_timeout(4000)
            print("browser ready",flush=True)
            errors = []
            page.on("pageerror", lambda x: errors.append(str(x)))
            for _ in range(40):
                try:
                    page.goto(f"http://127.0.0.1:{PORT}/",wait_until="domcontentloaded",timeout=2000)
                    break
                except Exception:
                    time.sleep(.2)
            print("homepage loaded",page.title(),"url",page.url,"body",page.locator("body").inner_text()[:170],flush=True)
            assert page.get_by_text("A little guidance,",exact=False).count() > 0
            page.screenshot(path=str(ROOT/"HomeCue_Website_Preview.png"), full_page=True)
            print("click pricing",flush=True)
            page.get_by_role("button",name="Pricing", exact=True).click()
            page.get_by_text("₹499", exact=True).wait_for()
            print("click annual",flush=True)
            page.get_by_role("button",name="Annual estimate −15%").click()
            page.get_by_text("₹424", exact=True).wait_for()
            page.get_by_role("button", name="Buy Starter ↗", exact=True).click()
            page.get_by_text("Welcome back.",exact=True).wait_for()
            page.locator('#authForm input[name=email]').fill('smoketest@example.com')
            page.locator('#authForm input[name=password]').fill('SmokeTestPassword123!')
            page.locator('#authForm button[value=register]').click()
            page.locator('#createHome input[name=name]').fill('Lab flat')
            page.locator('#createHome button[type=submit]').click()
            page.get_by_role("heading", name="Order summary", exact=True).wait_for()
            page.get_by_text("₹20,087", exact=True).wait_for()
            page.locator('#checkoutForm input[name=name]').fill('Demo buyer')
            page.locator('#checkoutForm input[name=email]').fill('demo@example.com')
            page.locator('input[name=payment][value=emi]').check()
            page.locator('select[name=tenure]').select_option('6')
            assert 'Total ₹20,087' in page.locator('#emi-estimate').inner_text()
            page.locator('select[name=outcome]').select_option('declined')
            page.get_by_role("button", name="Place demo order", exact=True).click()
            page.get_by_text('Demo payment declined.', exact=False).wait_for()
            page.locator('select[name=outcome]').select_option('cancelled')
            page.get_by_role("button", name="Place demo order", exact=True).click()
            page.get_by_text('Demo payment cancelled.', exact=False).wait_for()
            page.locator('input[name=payment][value=card]').check()
            assert page.get_by_label('Demo card number').input_value() == '4242 4242 4242 4242'
            page.locator('select[name=outcome]').select_option('success')
            page.get_by_role("button", name="Place demo order", exact=True).click()
            page.get_by_role("heading", name="Your demo order is complete.", exact=True).wait_for()
            page.get_by_text('Payment: Card ending 4242', exact=True).wait_for()
            page.get_by_role("button", name="Explore other packages", exact=True).click()
            page.get_by_role("button", name="Buy Family ↗", exact=True).wait_for()
            page.get_by_role('button',name='My Home',exact=True).click()
            page.get_by_role('heading',name='Starter plan',exact=True).wait_for()
            page.locator('[data-action="tab:setup"]').first.click()
            assert page.locator('#mod-task').is_enabled()
            assert page.locator('#mod-night').is_disabled()
            page.get_by_role('button',name='Pricing',exact=True).click()
            page.get_by_role('button', name='Customize Complete ↗',exact=True).wait_for()
            print("PASS demo purchase: package benefits / annual total / checkout / confirmation", flush=True)
            page.get_by_role('button', name='Customize Complete ↗', exact=True).click()
            page.locator('#checkoutForm input[name=name]').fill('Custom buyer')
            page.locator('#checkoutForm input[name=email]').fill('custom@example.com')
            page.get_by_role('button', name='Pay for custom plan (demo)').click()
            page.get_by_text('Choose at least one support option.', exact=True).wait_for()
            page.locator('input[name=custom_option][value=task]').check()
            page.locator('input[name=custom_option][value=orientation]').check()
            page.locator('select[name=zones]').select_option('3')
            page.locator('select[name=caregivers]').select_option('2')
            assert '3 home zones · 2 caregivers' in page.locator('#custom-summary').inner_text()
            assert '₹17,999' in page.locator('#custom-summary').inner_text()
            assert page.locator('#checkoutForm').get_attribute('data-total') == '24623'
            page.get_by_role('button', name='Pay for custom plan (demo)').click()
            page.get_by_role('heading', name='Your custom configuration is ready.').wait_for()
            assert page.get_by_text('Entrance awareness', exact=True).count() == 0
            page.get_by_role('button', name='Edit configuration', exact=True).click()
            assert page.locator('input[value=task]').is_checked()
            assert page.locator('select[name=zones]').input_value() == '3'
            print('PASS custom options / required selection / summary / edit preservation', flush=True)
            print("click myhome",flush=True)
            page.get_by_role("button",name="My Home").click()
            page.get_by_text('Hello, Caregiver.').wait_for(timeout=5000)
            page.get_by_role('heading',name='Custom Complete plan').wait_for()
            page.reload()
            page.get_by_role('heading',name='Custom Complete plan').wait_for()
            print("setup",flush=True)
            page.locator('[data-action="tab:setup"]').first.click()
            page.get_by_text('Module preferences').wait_for(timeout=5000)
            assert page.locator('#mod-night').is_disabled()
            assert page.locator('#mod-entrance').is_disabled()
            page.locator('#mod-task').check()
            page.locator('[data-action="save:task"]').click()
            page.get_by_text('Preference saved. Physical device not controlled.', exact=True).wait_for(timeout=5000)
            page.reload()
            page.locator('[data-action="tab:setup"]').first.click()
            from playwright.sync_api import expect
            expect(page.locator('#mod-task')).to_be_checked()
            print("activity",flush=True)
            page.locator('[data-action="tab:activity"]').click()
            page.get_by_role('heading', name='Activity', exact=True).wait_for(timeout=5000)
            page.locator('[data-action="demo-event"]').click()
            page.get_by_text('DEMO',exact=True).wait_for(timeout=5000)
            page.screenshot(path=str(ROOT/"HomeCue_Dashboard_Preview.png"), full_page=True)
            assert not errors, errors
            print("PASS browser: homepage / pricing / annual price / auth / home / module / demo event")
            print("Preview images created in project root")
            browser.close()
    finally:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill()
