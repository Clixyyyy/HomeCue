"""HomeCue research prototype API.

No medical claims, emergency monitoring, door locking, medication or stove control.
The IoT route accepts authenticated observations. It NEVER actuates a home device.
"""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "storage"
STORE.mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{STORE / 'homecue.db'}")
MODE = os.getenv("HOMECUE_ENV", "development")
SECRET = os.getenv("HOMECUE_JWT_SECRET", "")
if not SECRET:
    if MODE == "production":
        raise RuntimeError("HOMECUE_JWT_SECRET is required in production")
    # Local-only secret file: stable between development restarts, not committed to ZIP.
    secret_file = STORE / ".dev_secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(64), encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:
            pass
    SECRET = secret_file.read_text(encoding="utf-8").strip()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(220))


class Home(Base):
    __tablename__ = "homes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(100), default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    device_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Member(Base):
    __tablename__ = "members"
    id: Mapped[int] = mapped_column(primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="viewer")


class Module(Base):
    __tablename__ = "modules"
    id: Mapped[int] = mapped_column(primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cue_level: Mapped[int] = mapped_column(Integer, default=1)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"), index=True)
    module: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="device")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(35), default="")


class PlanPurchase(Base):
    __tablename__ = "plan_purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str] = mapped_column(String(80), unique=True)
    plan_id: Mapped[str] = mapped_column(String(30))
    module_codes: Mapped[str] = mapped_column(Text)
    period: Mapped[str] = mapped_column(String(10))
    zones: Mapped[int] = mapped_column(Integer)
    caregivers: Mapped[int] = mapped_column(Integer)
    payment_method: Mapped[str] = mapped_column(String(20))
    initial_total_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Interest(Base):
    __tablename__ = "interest"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(180))
    plan: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


MODULES = ["task", "night", "entrance", "orientation", "escalation"]
MODULE_LABELS = {
    "task": "Task guidance",
    "night": "Movement observations",
    "entrance": "Entrance awareness",
    "orientation": "Orientation and routines",
    "escalation": "Family updates",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="HomeCue Shared API",
    version="0.3.0",
    description="Prototype: settings and observation events only. No physical actuation or emergency claims.",
    lifespan=lifespan,
)
CORS = [x.strip() for x in os.getenv("HOMECUE_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"])
@app.middleware("http")
async def fresh_local_pages(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/app/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/assets", StaticFiles(directory=ROOT / "static"), name="assets")


def get_db():
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def valid_email(value: str) -> str:
    v = value.strip().lower()
    if len(v) > 180 or not EMAIL_PATTERN.fullmatch(v):
        raise HTTPException(422, "Enter a valid email address")
    return v


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + ":" + derived.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        check = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(check, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def password_version(user: User) -> str:
    return hmac.new(SECRET.encode(), user.password_hash.encode(), hashlib.sha256).hexdigest()


def password_reset_token(user: User) -> str:
    return jwt.encode({"sub":str(user.id),"purpose":"password_reset","pv":password_version(user),
                       "exp":datetime.now(timezone.utc)+timedelta(minutes=15)},SECRET,algorithm="HS256")


def user_jwt(user: User) -> str:
    payload = {"purpose":"access","pv":password_version(user),"sub": str(user.id), "iat": int(datetime.now(timezone.utc).timestamp()), "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, SECRET, algorithm="HS256")


def require_user(authorization: Annotated[str | None, Header()] = None, db: DB = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    try:
        decoded = jwt.decode(authorization[7:].strip(), SECRET, algorithms=["HS256"])
        user_id = int(decoded["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    user = db.get(User, user_id)
    if not user or decoded.get("purpose") != "access" or not hmac.compare_digest(str(decoded.get("pv", "")), password_version(user)):
        raise HTTPException(401, "Invalid or expired session. Sign in again.")
    return user


CurrentUser = Annotated[User, Depends(require_user)]


def get_home(home_id: int, user: User, db: Session, *, manage: bool = False) -> Home:
    home = db.get(Home, home_id)
    if not home:
        raise HTTPException(404, "Home not found")
    if home.owner_id == user.id:
        return home
    member = db.scalar(select(Member).where(Member.home_id == home_id, Member.user_id == user.id))
    if not member or (manage and member.role != "editor"):
        raise HTTPException(404, "Home not found or no access")
    return home


def is_online(home: Home) -> bool:
    return bool(home.device_last_seen and utcnow() - home.device_last_seen < timedelta(minutes=3))


def basic_home(h: Home) -> dict:
    return {"id": h.id, "name": h.name, "city": h.city, "hardware_connected": is_online(h), "last_seen": h.device_last_seen.isoformat() + "Z" if h.device_last_seen else None}


class RegisterBody(BaseModel):
    email: str
    name: str = Field(default="Caregiver", min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=200)


class LoginBody(BaseModel):
    email: str
    password: str


class NewHomeBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    city: str = Field(default="", max_length=100)


class ModuleBody(BaseModel):
    enabled: bool
    cue_level: int = Field(default=1, ge=1, le=3)


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", max_length=35)


class MemberBody(BaseModel):
    email: str
    role: Literal["viewer", "editor"] = "viewer"


class DeviceEventBody(BaseModel):
    module: Literal["task", "night", "entrance", "orientation", "escalation"]
    kind: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=260)


CUSTOM_RATES = {"task": (5000,150), "night": (2000,100), "entrance": (2000,100), "orientation": (5000,150), "escalation": (2000,100)}
CUSTOM_PRICING = {"base_setup_inr":4999, "base_monthly_inr":199, "extra_zone_setup_inr":1000, "extra_zone_monthly_inr":50, "extra_caregiver_setup_inr":1000, "extra_caregiver_monthly_inr":50}


def custom_price(codes, zones, caregivers, period):
    setup = CUSTOM_PRICING["base_setup_inr"] + sum(CUSTOM_RATES[c][0] for c in codes) + (zones-1)*CUSTOM_PRICING["extra_zone_setup_inr"] + (caregivers-1)*CUSTOM_PRICING["extra_caregiver_setup_inr"]
    monthly = CUSTOM_PRICING["base_monthly_inr"] + sum(CUSTOM_RATES[c][1] for c in codes) + (zones-1)*CUSTOM_PRICING["extra_zone_monthly_inr"] + (caregivers-1)*CUSTOM_PRICING["extra_caregiver_monthly_inr"]
    service = ((monthly*85+50)//100)*12 if period == "annual" else monthly
    return setup + service


class PurchaseBody(BaseModel):
    request_id: str = Field(min_length=16, max_length=80)
    plan_id: Literal["starter", "family", "complete"]
    period: Literal["monthly", "annual"] = "monthly"
    modules: list[Literal["task", "night", "entrance", "orientation", "escalation"]] = Field(default_factory=list, max_length=5)
    zones: int = Field(default=1, ge=1, le=5)
    caregivers: int = Field(default=1, ge=1, le=5)
    payment_method: Literal["upi", "card", "emi", "custom"]


def current_purchase(home_id: int, db: Session):
    return db.scalar(select(PlanPurchase).where(PlanPurchase.home_id == home_id).order_by(PlanPurchase.id.desc()))


def purchase_view(p: PlanPurchase | None):
    if p is None:
        return None
    return {"id": p.id, "plan_id": p.plan_id, "name": {"starter": "Starter", "family": "Family", "complete": "Custom Complete"}[p.plan_id],
            "status": "demo_purchased", "modules": json.loads(p.module_codes), "period": p.period,
            "zones": p.zones, "caregivers": p.caregivers, "payment_method": p.payment_method,
            "initial_total_inr": p.initial_total_inr, "purchased_at": p.purchased_at.isoformat() + "Z",
            "note": "Demo purchase recorded. No real payment, hardware activation or recurring charge."}


@app.post("/api/homes/{home_id}/purchases", status_code=201)
def purchase_plan(home_id: int, data: PurchaseBody, user: CurrentUser, db: DB):
    h = get_home(home_id, user, db)
    if h.owner_id != user.id:
        raise HTTPException(403, "Only the home owner can purchase or change its plan")
    codes = [code for code in MODULES if code in data.modules] if data.plan_id == "complete" else (["task", "orientation"] if data.plan_id == "starter" else MODULES[:])
    if not codes:
        raise HTTPException(422, "Choose at least one support option")
    if data.payment_method == "custom":
        raise HTTPException(422, "Choose UPI, card or EMI to complete demo payment")
    zones = data.zones if data.plan_id == "complete" else (1 if data.plan_id == "starter" else 3)
    caregivers = data.caregivers if data.plan_id == "complete" else (1 if data.plan_id == "starter" else 3)
    previous = db.scalar(select(PlanPurchase).where(PlanPurchase.request_id == data.request_id))
    if previous:
        if previous.home_id != home_id or previous.user_id != user.id:
            raise HTTPException(409, "Purchase request already used")
        if (previous.plan_id, previous.period, json.loads(previous.module_codes), previous.zones, previous.caregivers, previous.payment_method) != (data.plan_id, data.period, codes, zones, caregivers, data.payment_method):
            raise HTTPException(409, "Purchase request already used for a different selection")
        return purchase_view(previous)
    member_count = len(list(db.scalars(select(Member.id).where(Member.home_id == home_id)))) + 1
    if member_count > caregivers:
        raise HTTPException(409, f"This home already has {member_count} caregivers. Choose a plan with enough caregiver accounts.")
    monthly = {"starter": 499, "family": 999}[data.plan_id] if data.plan_id != "complete" else None
    service = (round(monthly * .85) * 12 if data.period == "annual" else monthly) if monthly else None
    total = service + {"starter": 14999, "family": 24999}[data.plan_id] if service else None
    if data.plan_id == "complete":
        total = custom_price(codes,zones,caregivers,data.period)
    p = PlanPurchase(home_id=home_id, user_id=user.id, request_id=data.request_id, plan_id=data.plan_id,
                     module_codes=json.dumps(codes), period=data.period, zones=zones, caregivers=caregivers,
                     payment_method=data.payment_method, initial_total_inr=total)
    db.add(p)
    for m in db.scalars(select(Module).where(Module.home_id == home_id)):
        if m.code not in codes:
            m.enabled = False
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Purchase request already recorded; refresh your dashboard")
    return purchase_view(p)


class InterestBody(BaseModel):
    email: str
    plan: Literal["starter", "family", "complete", "undecided"] = "undecided"


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.3.0", "prototype": True, "physical_control": False, "remote_emergency_support": False}


@app.post("/api/auth/register", status_code=201)
def register(data: RegisterBody, db: DB):
    email = valid_email(data.email)
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(name=data.name.strip(), email=email, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": user_jwt(user), "user": {"id": user.id, "name": user.name, "email": user.email}}


class ResetPasswordBody(BaseModel):
    token: str = Field(min_length=1, max_length=4096)
    new_password: str = Field(min_length=12, max_length=200)


@app.post("/api/auth/reset-password")
def reset_password(data: ResetPasswordBody, db: DB):
    try:
        decoded = jwt.decode(data.token, SECRET, algorithms=["HS256"])
        user = db.get(User, int(decoded["sub"]))
        if not user or decoded.get("purpose") != "password_reset" or not hmac.compare_digest(str(decoded.get("pv", "")),password_version(user)):
            raise ValueError("Invalid recovery link")
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(400,"This recovery link is expired or already used. Request a new one.")
    changed=db.execute(update(User).where(User.id==user.id,User.password_hash==user.password_hash).values(password_hash=hash_password(data.new_password)))
    if changed.rowcount!=1:
        db.rollback()
        raise HTTPException(400,"This recovery link is expired or already used. Request a new one.")
    db.commit()
    db.refresh(user)
    return {"token":user_jwt(user),"user":{"id":user.id,"name":user.name,"email":user.email}}


@app.post("/api/auth/login")
def login(data: LoginBody, db: DB):
    email = valid_email(data.email)
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": user_jwt(user), "user": {"id": user.id, "name": user.name, "email": user.email}}


@app.get("/api/me")
def me(user: CurrentUser):
    return {"id": user.id, "name": user.name, "email": user.email}


@app.get("/api/plans")
def plans():
    return {"status": "concept_only_no_payments", "annual_discount_proposal_percent": 15,
            "custom_pricing": CUSTOM_PRICING, "custom_options": [
                {"id": "task", "setup_inr": 5000, "monthly_inr": 150, "name": "Task guidance", "benefit": "Recognise tagged objects and review steps in a familiar routine.", "availability": "RFID lab prototype"},
                {"id": "night", "setup_inr": 2000, "monthly_inr": 100, "name": "Movement awareness", "benefit": "Review movement observations in a chosen area; night-path lighting needs additional hardware.", "availability": "Sensor bench test; lighting planned"},
                {"id": "entrance", "setup_inr": 2000, "monthly_inr": 100, "name": "Entrance awareness", "benefit": "Plan observation of doorway activity alongside family review.", "availability": "Future hardware"},
                {"id": "orientation", "setup_inr": 5000, "monthly_inr": 150, "name": "Orientation and routines", "benefit": "Plan time and routine cues for familiar spaces.", "availability": "Time module test; display planned"},
                {"id": "escalation", "setup_inr": 2000, "monthly_inr": 100, "name": "Family updates", "benefit": "Share recorded observations with trusted caregivers on the website and app.", "availability": "Shared activity available; push/SMS planned"},
            ], "plans": [
        {"id": "starter", "name": "Starter", "included_modules": ["task", "orientation"], "zones": 1, "caregivers": 1, "monthly_inr": 499, "setup_from_inr": 14999, "features": ["Orientation display", "One configured guidance zone", "One caregiver account"]},
        {"id": "family", "name": "Family", "included_modules": MODULES, "zones": 3, "caregivers": 3, "monthly_inr": 999, "setup_from_inr": 24999, "features": ["Orientation and night guidance (future hardware)", "One task station", "Entrance monitoring (future hardware)", "Up to three caregivers"]},
        {"id": "complete", "name": "Complete", "included_modules": [], "zones": None, "caregivers": None, "monthly_inr": None, "setup_from_inr": None, "features": ["Up to five home zones", "More configurable cues", "Care circle and planned service support"]},
    ]}


@app.post("/api/interest", status_code=201)
def interest(data: InterestBody, db: DB):
    db.add(Interest(email=valid_email(data.email), plan=data.plan))
    db.commit()
    return {"ok": True, "note": "Interest registered; no payment or subscription created"}


@app.get("/api/homes")
def homes(user: CurrentUser, db: DB):
    memberships = list(db.scalars(select(Member.home_id).where(Member.user_id == user.id)))
    query = select(Home).where(or_(Home.owner_id == user.id, Home.id.in_(memberships))).order_by(Home.id)
    return [basic_home(h) for h in db.scalars(query)]


@app.post("/api/homes", status_code=201)
def create_home(data: NewHomeBody, user: CurrentUser, db: DB):
    h = Home(name=data.name.strip(), city=data.city.strip(), owner_id=user.id)
    db.add(h)
    db.flush()
    db.add_all(Module(home_id=h.id, code=code, enabled=False, cue_level=1) for code in MODULES)
    db.commit()
    return basic_home(h)


@app.get("/api/homes/{home_id}")
def detail(home_id: int, user: CurrentUser, db: DB):
    h = get_home(home_id, user, db)
    purchase = current_purchase(home_id, db)
    included = json.loads(purchase.module_codes) if purchase else []
    return {**basic_home(h), "owner": h.owner_id == user.id, "purchase": purchase_view(purchase),
            "modules": [{"code": m.code, "label": MODULE_LABELS[m.code], "included": m.code in included, "enabled": m.enabled, "cue_level": m.cue_level} for m in db.scalars(select(Module).where(Module.home_id == h.id).order_by(Module.id))]}


@app.put("/api/homes/{home_id}/modules/{code}")
def update_module(home_id: int, code: str, data: ModuleBody, user: CurrentUser, db: DB):
    get_home(home_id, user, db, manage=True)
    if code not in MODULES:
        raise HTTPException(404, "Unknown module")
    purchase = current_purchase(home_id, db)
    if purchase is None or code not in json.loads(purchase.module_codes):
        raise HTTPException(403, "This option is not included in your purchased plan")
    m = db.scalar(select(Module).where(Module.home_id == home_id, Module.code == code))
    m.enabled, m.cue_level = data.enabled, data.cue_level
    db.commit()
    return {"code": code, "enabled": m.enabled, "cue_level": m.cue_level, "physical_change": False}


@app.get("/api/homes/{home_id}/contacts")
def contacts(home_id: int, user: CurrentUser, db: DB):
    get_home(home_id, user, db)
    return [{"id": c.id, "name": c.name, "phone": c.phone} for c in db.scalars(select(Contact).where(Contact.home_id == home_id))]


@app.post("/api/homes/{home_id}/contacts", status_code=201)
def add_contact(home_id: int, data: ContactBody, user: CurrentUser, db: DB):
    get_home(home_id, user, db, manage=True)
    c = Contact(home_id=home_id, name=data.name.strip(), phone=data.phone.strip())
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "phone": c.phone, "sms_active": False}


@app.delete("/api/homes/{home_id}/contacts/{contact_id}")
def remove_contact(home_id: int, contact_id: int, user: CurrentUser, db: DB):
    get_home(home_id, user, db, manage=True)
    c = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.home_id == home_id))
    if not c:
        raise HTTPException(404, "Contact not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


@app.get("/api/homes/{home_id}/members")
def members(home_id: int, user: CurrentUser, db: DB):
    h = get_home(home_id, user, db)
    owner = db.get(User, h.owner_id)
    result = [{"id": owner.id, "name": owner.name, "email": owner.email, "role": "owner"}]
    for m in db.scalars(select(Member).where(Member.home_id == home_id)):
        u = db.get(User, m.user_id)
        if u:
            result.append({"id": u.id, "name": u.name, "email": u.email, "role": m.role})
    return result


@app.post("/api/homes/{home_id}/members", status_code=201)
def invite_existing_member(home_id: int, data: MemberBody, user: CurrentUser, db: DB):
    h = get_home(home_id, user, db)
    if h.owner_id != user.id:
        raise HTTPException(403, "Only owner can add caregiver accounts")
    other = db.scalar(select(User).where(User.email == valid_email(data.email)))
    if not other:
        raise HTTPException(404, "Ask this caregiver to register an account first")
    if other.id == h.owner_id or db.scalar(select(Member.id).where(Member.user_id == other.id, Member.home_id == h.id)):
        raise HTTPException(409, "Already has access to this home")
    purchase = current_purchase(home_id, db)
    count = len(list(db.scalars(select(Member.id).where(Member.home_id == home_id)))) + 1
    if purchase is None or count >= purchase.caregivers:
        raise HTTPException(403, "Your plan does not have an available caregiver account. Choose a larger plan.")
    db.add(Member(home_id=h.id, user_id=other.id, role=data.role))
    db.commit()
    return {"ok": True, "email": other.email, "role": data.role, "note": "Direct access grant; no email sent"}


@app.get("/api/homes/{home_id}/events")
def events(home_id: int, user: CurrentUser, db: DB, limit: int = Query(default=50, ge=1, le=100), module: str | None = None):
    get_home(home_id, user, db)
    stmt = select(Event).where(Event.home_id == home_id)
    if module in MODULES:
        stmt = stmt.where(Event.module == module)
    stmt = stmt.order_by(Event.id.desc()).limit(limit)
    return [{"id": e.id, "module": e.module, "kind": e.kind, "message": e.message,
             "source": e.source, "created_at": e.created_at.isoformat() + "Z", "acknowledged": e.acknowledged}
            for e in db.scalars(stmt)]


@app.post("/api/homes/{home_id}/events/{event_id}/ack")
def acknowledge(home_id: int, event_id: int, user: CurrentUser, db: DB):
    get_home(home_id, user, db, manage=True)
    e = db.scalar(select(Event).where(Event.id == event_id, Event.home_id == home_id))
    if not e:
        raise HTTPException(404, "Event not found")
    e.acknowledged = True
    db.commit()
    return {"ok": True}


@app.post("/api/homes/{home_id}/demo-event", status_code=201)
def demo_event(home_id: int, user: CurrentUser, db: DB):
    get_home(home_id, user, db, manage=True)
    e = Event(home_id=home_id, module="task", kind="tag_scan", message="Demo: an RFID tag was scanned (no device involved)", source="demo")
    db.add(e)
    db.commit()
    return {"id": e.id, "source": "demo", "note": "Simulated data; not a sensor reading"}


@app.post("/api/homes/{home_id}/device-token")
def rotate_device_token(home_id: int, user: CurrentUser, db: DB):
    h = get_home(home_id, user, db)
    if h.owner_id != user.id:
        raise HTTPException(403, "Only home owner can generate hardware credentials")
    raw = secrets.token_urlsafe(42)
    h.device_token_hash = hashlib.sha256(raw.encode()).hexdigest()
    h.device_last_seen = None
    db.commit()
    return {"token": raw, "message": "Copy once; keep in local firmware secrets only; previous token is revoked"}


def device_auth(home_id: int, token: str | None, db: Session) -> Home:
    h = db.get(Home, home_id)
    if not h or not h.device_token_hash or not token:
        raise HTTPException(401, "Device not authorised")
    if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), h.device_token_hash):
        raise HTTPException(401, "Device not authorised")
    return h


@app.post("/api/device/{home_id}/heartbeat")
def heartbeat(home_id: int, db: DB, x_device_token: Annotated[str | None, Header()] = None):
    h = device_auth(home_id, x_device_token, db)
    h.device_last_seen = utcnow()
    db.commit()
    return {"ok": True, "server_time": utcnow().isoformat() + "Z"}


@app.post("/api/device/{home_id}/events", status_code=201)
def device_event(home_id: int, data: DeviceEventBody, db: DB, x_device_token: Annotated[str | None, Header()] = None):
    h = device_auth(home_id, x_device_token, db)
    h.device_last_seen = utcnow()
    e = Event(home_id=home_id, module=data.module, kind=data.kind, message=data.message, source="device")
    db.add(e)
    db.commit()
    return {"ok": True, "id": e.id, "stored_as": "observation_only"}


app.mount(
    "/app",
    StaticFiles(directory=ROOT.parent / "mobile_flutter" / "build" / "web", html=True, check_dir=False),
    name="caregiver-app",
)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api"):
        raise HTTPException(404, "Not found")
    return FileResponse(ROOT / "static" / "index.html")
