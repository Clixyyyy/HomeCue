"""End-to-end API tests: users, home isolation, device token, shared event history."""
import os
import sys
import tempfile
from pathlib import Path

# Import the real app with a throwaway DB before any server module import.
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
TEST_DIR = tempfile.TemporaryDirectory(prefix="homecue-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(TEST_DIR.name) / "test.db")
os.environ["HOMECUE_JWT_SECRET"] = "unit-test-secret-only-not-used-outside-tests-1234567890"
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_account(client, email, name="Caregiver"):
    result = client.post("/api/auth/register", json={"email": email, "name": name, "password": "A-long-password-123!"})
    assert result.status_code == 201, result.text
    return result.json()["token"]


def test_health_plans_and_home_device_flow():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["physical_control"] is False
        plans = client.get("/api/plans").json()
        assert len(plans["plans"]) == 3
        assert client.get("/api/homes").status_code == 401
        owner = create_account(client, "owner@example.com")
        other = create_account(client, "second@example.com")
        home = client.post("/api/homes", headers=bearer(owner), json={"name": "Test house", "city": "Bengaluru"})
        assert home.status_code == 201
        home_id = home.json()["id"]
        detail = client.get(f"/api/homes/{home_id}", headers=bearer(owner))
        assert len(detail.json()["modules"]) == 5
        assert detail.json()["hardware_connected"] is False
        assert client.get(f"/api/homes/{home_id}", headers=bearer(other)).status_code == 404
        assert client.post(f"/api/homes/{home_id}/device-token", headers=bearer(other)).status_code == 404

        assert client.post(f"/api/homes/{home_id}/purchases", headers=bearer(owner), json={"request_id":"existing-api-family-test-001","plan_id":"family","payment_method":"upi"}).status_code == 201
        updated = client.put(f"/api/homes/{home_id}/modules/task", headers=bearer(owner), json={"enabled": True,"cue_level":2})
        assert updated.status_code == 200
        assert updated.json()["physical_change"] is False
        assert client.get(f"/api/homes/{home_id}", headers=bearer(owner)).json()["modules"][0]["cue_level"] == 2

        unauth = client.post(f"/api/device/{home_id}/events", json={"module":"task","kind":"tag_scan","message":"Test"})
        assert unauth.status_code == 401
        cred = client.post(f"/api/homes/{home_id}/device-token", headers=bearer(owner))
        device_token = cred.json()["token"]
        hw = {"X-Device-Token": device_token}
        assert client.post(f"/api/device/{home_id}/heartbeat", headers=hw).status_code == 200
        assert client.get(f"/api/homes/{home_id}", headers=bearer(owner)).json()["hardware_connected"] is True
        event = client.post(f"/api/device/{home_id}/events", headers=hw, json={"module":"task","kind":"tag_scan","message":"RFID tag observed"})
        assert event.status_code == 201, event.text
        e_id = event.json()["id"]
        feed = client.get(f"/api/homes/{home_id}/events", headers=bearer(owner)).json()
        assert len(feed)==1 and feed[0]["id"] == e_id and feed[0]["source"] == "device"
        assert client.post(f"/api/homes/{home_id}/events/{e_id}/ack", headers=bearer(owner)).status_code == 200
        assert client.get(f"/api/homes/{home_id}/events", headers=bearer(owner)).json()[0]["acknowledged"] is True
        assert client.get(f"/api/homes/{home_id}/events", headers=bearer(other)).status_code == 404

        share = client.post(f"/api/homes/{home_id}/members", headers=bearer(owner), json={"email":"second@example.com","role":"viewer"})
        assert share.status_code == 201
        assert len(client.get(f"/api/homes/{home_id}/events", headers=bearer(other)).json()) == 1
        assert client.put(f"/api/homes/{home_id}/modules/night", headers=bearer(other), json={"enabled":True,"cue_level":1}).status_code == 404

        created = client.post(f"/api/homes/{home_id}/demo-event", headers=bearer(owner))
        assert created.status_code == 201
        feed2 = client.get(f"/api/homes/{home_id}/events", headers=bearer(owner)).json()
        assert feed2[0]["source"] == "demo"

        contact = client.post(f"/api/homes/{home_id}/contacts", headers=bearer(owner),json={"name":"Family person","phone":""})
        assert contact.status_code == 201
        assert len(client.get(f"/api/homes/{home_id}/contacts",headers=bearer(other)).json()) == 1

        rotate = client.post(f"/api/homes/{home_id}/device-token",headers=bearer(owner))
        assert rotate.status_code == 200
        assert client.post(f"/api/device/{home_id}/heartbeat",headers=hw).status_code == 401
        assert client.post(f"/api/device/{home_id}/heartbeat",headers={"X-Device-Token":rotate.json()["token"]}).status_code == 200

        login = client.post("/api/auth/login", json={"email":"owner@example.com","password":"A-long-password-123!"})
        assert login.status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/styles.css").status_code == 200


def test_invalid_auth_and_inputs():
    with TestClient(app) as client:
        bad = client.post("/api/auth/register", json={"email":"bad","name":"X","password":"A-long-password-123!"})
        assert bad.status_code == 422
        owner=create_account(client,"third@example.com")
        assert client.post("/api/auth/login",json={"email":"third@example.com","password":"wrong"}).status_code == 401
        assert client.post("/api/homes",headers=bearer(owner),json={"name":""}).status_code == 422
        assert client.get("/api/private-unknown").status_code == 404


def test_purchases_entitlements_and_isolation():
    with TestClient(app) as client:
        owner = create_account(client, "buyer@example.com")
        outsider = create_account(client, "outside-buyer@example.com")
        viewer = create_account(client, "plan-viewer@example.com")
        home_id = client.post('/api/homes', headers=bearer(owner), json={'name':'Purchase home'}).json()['id']
        path = f'/api/homes/{home_id}'
        assert client.get(path,headers=bearer(owner)).json()['purchase'] is None
        assert client.put(path+'/modules/task',headers=bearer(owner),json={'enabled':True}).status_code==403
        body={'request_id':'starter-purchase-test-001','plan_id':'starter','payment_method':'card','period':'annual'}
        assert client.post(path+'/purchases',json=body).status_code==401
        assert client.post(path+'/purchases',headers=bearer(outsider),json=body).status_code==404
        purchase=client.post(path+'/purchases',headers=bearer(owner),json=body)
        assert purchase.status_code==201,purchase.text
        assert purchase.json()['initial_total_inr']==20087
        assert client.post(path+'/purchases',headers=bearer(owner),json=body).json()['id']==purchase.json()['id']
        assert client.post(path+'/purchases',headers=bearer(owner),json={**body,'plan_id':'family'}).status_code==409
        detail=client.get(path,headers=bearer(owner)).json()
        assert {m['code'] for m in detail['modules'] if m['included']}=={'task','orientation'}
        assert client.put(path+'/modules/task',headers=bearer(owner),json={'enabled':True}).status_code==200
        assert client.put(path+'/modules/night',headers=bearer(owner),json={'enabled':True}).status_code==403
        assert client.post(path+'/members',headers=bearer(owner),json={'email':'plan-viewer@example.com'}).status_code==403
        custom={'request_id':'custom-purchase-test-001','plan_id':'complete','payment_method':'upi','modules':['night','escalation'],'zones':4,'caregivers':3}
        assert client.post(path+'/purchases',headers=bearer(owner),json={**custom,'modules':[]}).status_code==422
        assert client.post(path+'/purchases',headers=bearer(owner),json={**custom,'modules':['unknown']}).status_code==422
        assert client.post(path+'/purchases',headers=bearer(owner),json=custom).status_code==201
        detail=client.get(path,headers=bearer(owner)).json()
        assert detail['purchase']['modules']==['night','escalation']
        assert detail['purchase']['zones']==4
        assert detail['purchase']['initial_total_inr']==14648
        assert not next(m for m in detail['modules'] if m['code']=='task')['enabled']
        assert client.put(path+'/modules/task',headers=bearer(owner),json={'enabled':True}).status_code==403
        assert client.put(path+'/modules/night',headers=bearer(owner),json={'enabled':True}).status_code==200
        assert client.post(path+'/members',headers=bearer(owner),json={'email':'plan-viewer@example.com'}).status_code==201
        assert client.get(path,headers=bearer(viewer)).json()['purchase']['name']=='Custom Complete'
        assert client.post(path+'/purchases',headers=bearer(viewer),json={**body,'request_id':'viewer-purchase-test-001'}).status_code==403
        assert client.post(path+'/purchases',headers=bearer(owner),json={**body,'request_id':'downgrade-purchase-test-001'}).status_code==409
    with TestClient(app) as client:
        assert client.get(path,headers=bearer(owner)).json()['purchase']['modules']==['night','escalation']


def test_custom_price_calculation():
    from main import custom_price
    assert custom_price(['task'],1,1,'monthly')==10348
    assert custom_price(['task','orientation'],3,2,'annual')==24623
    assert custom_price(['task'],2,1,'monthly')-custom_price(['task'],1,1,'monthly')==1050
    assert custom_price(['task'],1,2,'monthly')-custom_price(['task'],1,1,'monthly')==1050


def test_custom_matches_preset_plans():
    from main import custom_price, MODULES
    assert custom_price(['task','orientation'],1,1,'monthly')==14999+499
    assert custom_price(MODULES,3,3,'monthly')==24999+999
    assert custom_price(['task','orientation'],1,1,'annual')==14999+424*12
    assert custom_price(MODULES,3,3,'annual')==24999+849*12


def test_one_time_password_recovery():
    from main import SessionLocal, User, password_reset_token
    from sqlalchemy import select
    with TestClient(app) as client:
        old=create_account(client,'recovery-test@example.com')
        home=client.post('/api/homes',headers=bearer(old),json={'name':'Keep this home'}).json()
        with SessionLocal() as db:
            recovery=password_reset_token(db.scalar(select(User).where(User.email=='recovery-test@example.com')))
        assert client.get('/api/me',headers=bearer(recovery)).status_code==401
        assert client.post('/api/auth/reset-password',json={'token':old,'new_password':'Replacement-password-123!'}).status_code==400
        assert client.post('/api/auth/reset-password',json={'token':recovery,'new_password':'short'}).status_code==422
        result=client.post('/api/auth/reset-password',json={'token':recovery,'new_password':'Replacement-password-123!'})
        assert result.status_code==200,result.text
        assert client.get('/api/homes',headers=bearer(result.json()['token'])).json()[0]['id']==home['id']
        assert client.get('/api/me',headers=bearer(old)).status_code==401
        assert client.post('/api/auth/reset-password',json={'token':recovery,'new_password':'Different-password-456!'}).status_code==400
        assert client.post('/api/auth/login',json={'email':'recovery-test@example.com','password':'A-long-password-123!'}).status_code==401
        assert client.post('/api/auth/login',json={'email':' RECOVERY-TEST@example.com ','password':'Replacement-password-123!'}).status_code==200


def test_remote_gateway_access_controls():
    from remote_gateway import RemoteGateway, COOKIE
    from main import SessionLocal, User, hash_password
    from sqlalchemy import select
    allowed='gateway-owner@example.com'
    with TestClient(app) as local:
        owner=create_account(local,allowed)
        other=create_account(local,'gateway-other@example.com')
        home=local.post('/api/homes',headers=bearer(owner),json={'name':'Gateway protected home'}).json()
    gateway=RemoteGateway(app,[allowed])
    with TestClient(gateway,base_url='https://remote.example',follow_redirects=False) as remote:
        assert remote.get('/app/').status_code==303
        assert remote.get('/assets/app.js').status_code==303
        assert remote.get('/api/homes',headers=bearer(owner)).status_code==401
        assert remote.get('/openapi.json').status_code==303
        assert remote.get('/api/remote-session').status_code==401
        assert remote.get('/remote-access?next=https://evil.example').status_code==200
        body={'email':allowed,'password':'A-long-password-123!','next':'/app/'}
        assert remote.post('/remote-access/sign-in',json={**body,'email':'gateway-other@example.com'}).status_code==401
        assert remote.post('/remote-access/sign-in',json={**body,'password':'wrong'}).status_code==401
        assert remote.post('/remote-access/sign-in',json=body,headers={'Origin':'https://evil.example'}).status_code==403
        result=remote.post('/remote-access/sign-in',json={**body,'next':'//evil.example'})
        assert result.status_code==200 and result.json()['next']=='/app/'
        cookie=result.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=lax' in cookie
        assert remote.get('/app/').status_code==200
        assert remote.get('/api/homes').json()[0]['id']==home['id']
        assert remote.get('/api/homes',headers=bearer(other)).json()[0]['id']==home['id']
        session=remote.get('/api/remote-session').json()
        assert session['user']['email']==allowed
        assert remote.post('/api/auth/register',json={}).status_code==403
        assert remote.post('/api/remote-sign-out').status_code==200
        assert remote.get('/api/homes').status_code==401
        assert remote.post('/remote-access/sign-in',json=body).status_code==200
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.email==allowed));user.password_hash=hash_password('Changed-gateway-password-123!');db.commit()
        assert remote.get('/api/homes').status_code==401
    with TestClient(RemoteGateway(app,[allowed]),base_url='https://remote.example') as rate_limited:
        for _ in range(8):
            assert rate_limited.post('/remote-access/sign-in',json={**body,'password':'wrong'}).status_code==401
        assert rate_limited.post('/remote-access/sign-in',json={**body,'password':'wrong'}).status_code==429
