"""Local administrator recovery. No public token-issuance endpoint."""
import argparse
import subprocess
from urllib.parse import quote
from sqlalchemy import select
from main import SessionLocal, User, password_reset_token, valid_email

parser=argparse.ArgumentParser(description='Open a one-time HomeCue password recovery page for an existing account.')
parser.add_argument('--email',required=True)
args=parser.parse_args()
with SessionLocal() as db:
    user=db.scalar(select(User).where(User.email==valid_email(args.email)))
    if user is None:
        raise SystemExit('No account exists for that email. Use Create account instead.')
    token=password_reset_token(user)
    # Fragment stays in the browser; it is not sent in server URLs or access logs.
    subprocess.run(['open','http://127.0.0.1:8000/reset-password#token='+quote(token,safe='')],check=True)
    print('Opened a one-time password recovery page. It expires in 15 minutes. No password has been changed yet.')
