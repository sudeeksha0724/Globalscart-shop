from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
import httpx
import psycopg

from ..db import get_conn
from ..models import (
    AuthLoginIn,
    AuthLoginOut,
    AuthMeOut,
    AuthTokenOut,
    AuthEmailExistsOut,
    AuthRequestOtpIn,
    AuthRequestOtpOut,
    AuthSignupRequestOtpIn,
    AuthSignupRequestOtpOut,
    AuthSignupVerifyOtpIn,
    AuthSignupVerifyOtpOut,
    AuthVerifyOtpIn,
    AuthVerifyOtpOut,
)
from ..security import create_access_token, decode_access_token, parse_bearer_token


router = APIRouter(prefix="/api/auth", tags=["api_auth"])


@router.get("/email-exists", response_model=AuthEmailExistsOut)
def email_exists(email: str) -> AuthEmailExistsOut:
    e = _validate_email(email)
    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM globalcart.app_users WHERE email = %s LIMIT 1;",
                    (e,),
                )
                exists = cur.fetchone() is not None
        return AuthEmailExistsOut(email=e, exists=exists)
    except psycopg.OperationalError:
        return AuthEmailExistsOut(email=e, exists=False)
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth schema not ready. Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _validate_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or len(e) > 320 or not _EMAIL_RE.match(e):
        raise HTTPException(status_code=400, detail="Invalid email")
    return e


def _otp_secret() -> str:
    return os.getenv("OTP_SECRET", "dev-secret")


def _otp_ttl_seconds() -> int:
    try:
        return int(os.getenv("OTP_TTL_SECONDS", "600"))
    except ValueError:
        return 600


def _max_attempts() -> int:
    try:
        return int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    except ValueError:
        return 5


def _show_demo_otp() -> bool:
    return str(os.getenv("DEMO_SHOW_OTP", "1")).strip() not in {"0", "false", "False"}


def _hash_otp(email: str, otp: str) -> str:
    payload = f"{email}|{otp}|{_otp_secret()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _password_hash(password: str) -> str:
    pwd = (password or "").strip()
    if len(pwd) < 7:
        raise HTTPException(status_code=400, detail="Password must be at least 7 characters")
    if not re.search(r"[A-Z]", pwd):
        raise HTTPException(status_code=400, detail="Password must include at least 1 uppercase letter")
    if not re.search(r"[0-9]", pwd):
        raise HTTPException(status_code=400, detail="Password must include at least 1 number")
    if not re.search(r"[^A-Za-z0-9]", pwd):
        raise HTTPException(status_code=400, detail="Password must include at least 1 special character")

    iterations = 180_000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, iterations)

    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        base64.urlsafe_b64encode(salt).decode("utf-8"),
        base64.urlsafe_b64encode(dk).decode("utf-8"),
    )


def _password_verify(password: str, stored: str) -> bool:
    try:
        algo, it_s, salt_b64, dk_b64 = (stored or "").split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(it_s)
        salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
        expected = base64.urlsafe_b64decode(dk_b64.encode("utf-8"))
        actual = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _send_otp_email(email: str, otp: str, ttl_seconds: int) -> bool:
    logger = logging.getLogger("api_auth")

    subject = "Your GlobalCart verification code"
    minutes = max(1, int(ttl_seconds // 60))
    body = f"Your GlobalCart OTP is: {otp}. It expires in {minutes} minutes."

    # Prefer SendGrid if configured
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "").strip()
    logger.info(
        "[OTP_EMAIL] sendgrid_configured=%s smtp_configured=%s demo_show_otp=%s",
        bool(api_key and from_email),
        bool(
            os.getenv("SMTP_HOST", "").strip()
            and os.getenv("SMTP_USER", "").strip()
            and os.getenv("SMTP_PASSWORD", "").strip()
            and os.getenv("SMTP_FROM_EMAIL", "").strip()
        ),
        _show_demo_otp(),
    )
    if api_key and from_email:
        logger.info("[OTP_EMAIL] using=sendgrid to=%s", email)
        payload = {
            "personalizations": [{"to": [{"email": email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if resp.status_code in (200, 202):
                    return True

                logger.error(
                    "SendGrid send failed status=%s body=%s",
                    resp.status_code,
                    resp.text,
                )
                raise HTTPException(status_code=502, detail="Failed to send OTP email")
        except httpx.HTTPError:
            logger.exception("SendGrid HTTP error")
            raise HTTPException(status_code=502, detail="Failed to send OTP email")

    # SMTP fallback (e.g., Gmail App Password)
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM_EMAIL", "").strip()
    if not (smtp_host and smtp_user and smtp_password and smtp_from):
        logger.info(
            "[OTP_EMAIL] smtp_missing host=%s user=%s password=%s from=%s",
            bool(smtp_host),
            bool(smtp_user),
            bool(smtp_password),
            bool(smtp_from),
        )
    if smtp_host and smtp_user and smtp_password and smtp_from:
        try:
            smtp_port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
        except ValueError:
            smtp_port = 587

        use_tls = str(os.getenv("SMTP_USE_TLS", "1")).strip() not in {"0", "false", "False"}

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = email
        msg.set_content(body)

        try:
            logger.info(
                "[OTP_EMAIL] using=smtp host=%s port=%s tls=%s user=%s from=%s to=%s",
                smtp_host,
                smtp_port,
                use_tls,
                smtp_user,
                smtp_from,
                email,
            )
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            return True
        except Exception:
            logger.exception("SMTP send failed")
            raise HTTPException(status_code=502, detail="Failed to send OTP email")

    return False


def _pick_customer_for_email(conn, email: str) -> tuple[int, int]:
    h = int(hashlib.md5(email.encode("utf-8")).hexdigest(), 16)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM globalcart.vw_customer_customers")
        n = int(cur.fetchone()[0])
        if n <= 0:
            raise HTTPException(status_code=400, detail="No customers found. Load demo data first.")
        offset = int(h % n)
        cur.execute(
            "SELECT customer_id, geo_id FROM globalcart.vw_customer_customers ORDER BY customer_id OFFSET %s LIMIT 1",
            (offset,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="No customers found. Load demo data first.")
    return int(row[0]), int(row[1])


@router.post("/request-otp", response_model=AuthRequestOtpOut)
def request_otp(req: AuthRequestOtpIn) -> AuthRequestOtpOut:
    email = _validate_email(req.email)
    import logging
    logger = logging.getLogger("api_auth")
    logger.info(f"[DEBUG] request_otp email={email}")

    otp = f"{secrets.randbelow(1000000):06d}"
    otp_hash = _hash_otp(email, otp)

    ttl = _otp_ttl_seconds()
    expires_at = _utc_now() + timedelta(seconds=ttl)
    logger.info(f"[DEBUG] generated otp={otp} expires_at={expires_at}")

    try:
        with get_conn() as conn:
            try:
                logger.info(
                    "[DEBUG] pg_conn host=%s db=%s user=%s",
                    getattr(conn.info, "host", None),
                    getattr(conn.info, "dbname", None),
                    getattr(conn.info, "user", None),
                )
            except Exception:
                pass
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO globalcart.app_email_otps (email, otp_hash, expires_at)
                    VALUES (%s, %s, %s);
                    """,
                    (email, otp_hash, expires_at),
                )
                logger.info("[DEBUG] INSERT completed successfully")

                cur.execute(
                    """
                    SELECT otp_id, created_at, consumed_at
                    FROM globalcart.app_email_otps
                    WHERE email = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (email,),
                )
                logger.info("[DEBUG] post-insert latest otp row (same tx): %s", cur.fetchone())

            conn.commit()

        emailed = False
        try:
            emailed = _send_otp_email(email, otp, ttl)
        except HTTPException:
            if not _show_demo_otp():
                raise

        return AuthRequestOtpOut(
            email=email,
            otp_sent=True,
            expires_in_seconds=ttl,
            demo_otp=otp if (_show_demo_otp() and not emailed) else None,
        )

    except psycopg.OperationalError:
        logger.exception("[OTP] database not reachable during request-otp")
        if not _show_demo_otp():
            raise HTTPException(
                status_code=503,
                detail="Auth service unavailable (database not reachable). Please try again in a moment.",
            )
        return AuthRequestOtpOut(
            email=email,
            otp_sent=True,
            expires_in_seconds=ttl,
            demo_otp=otp if _show_demo_otp() else None,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth tables not found (missing globalcart.app_email_otps). "
                "Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )


@router.post("/signup/request-otp", response_model=AuthSignupRequestOtpOut)
def signup_request_otp(req: AuthSignupRequestOtpIn) -> AuthSignupRequestOtpOut:
    email = _validate_email(req.email)
    display_name = (req.display_name or "").strip()
    if not display_name or len(display_name) > 120:
        raise HTTPException(status_code=400, detail="Invalid name")

    pwd_hash = _password_hash(req.password)

    otp = f"{secrets.randbelow(1000000):06d}"
    otp_hash = _hash_otp(email, otp)
    ttl = _otp_ttl_seconds()
    expires_at = _utc_now() + timedelta(seconds=ttl)

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM globalcart.app_users WHERE email = %s LIMIT 1;", (email,))
                if cur.fetchone() is not None:
                    raise HTTPException(status_code=400, detail="An account with this email already exists. Please log in.")
                cur.execute(
                    """
                    INSERT INTO globalcart.app_email_otps (email, otp_hash, expires_at, purpose, display_name, password_hash)
                    VALUES (%s, %s, %s, 'SIGNUP', %s, %s);
                    """,
                    (email, otp_hash, expires_at, display_name, pwd_hash),
                )
            conn.commit()

        emailed = False
        try:
            emailed = _send_otp_email(email, otp, ttl)
        except HTTPException:
            if not _show_demo_otp():
                raise
        return AuthSignupRequestOtpOut(
            email=email,
            otp_sent=True,
            expires_in_seconds=ttl,
            demo_otp=otp if (_show_demo_otp() and not emailed) else None,
        )

    except psycopg.OperationalError:
        logging.getLogger("api_auth").exception("[OTP] database not reachable during signup/request-otp")
        if not _show_demo_otp():
            raise HTTPException(
                status_code=503,
                detail="Auth service unavailable (database not reachable). Please try again in a moment.",
            )
        return AuthSignupRequestOtpOut(
            email=email,
            otp_sent=True,
            expires_in_seconds=ttl,
            demo_otp=otp if _show_demo_otp() else None,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth schema not ready for signup. "
                "Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )


@router.post("/signup/verify-otp", response_model=AuthSignupVerifyOtpOut)
def signup_verify_otp(req: AuthSignupVerifyOtpIn) -> AuthSignupVerifyOtpOut:
    email = _validate_email(req.email)
    otp = (req.otp or "").strip()
    if not otp or len(otp) > 16:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    max_attempts = _max_attempts()

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)

            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM globalcart.app_users WHERE email = %s LIMIT 1;", (email,))
                if cur.fetchone() is not None:
                    raise HTTPException(status_code=400, detail="An account with this email already exists. Please log in.")
                cur.execute(
                    """
                    SELECT otp_id, otp_hash, expires_at, attempts, display_name, password_hash
                    FROM globalcart.app_email_otps
                    WHERE email = %s AND purpose = 'SIGNUP' AND consumed_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (email,),
                )
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=400, detail="OTP not found. Request a new OTP.")

                otp_id = int(row[0])
                otp_hash = str(row[1])
                expires_at = row[2]
                attempts = int(row[3])
                display_name = (row[4] or None)
                pwd_hash = (row[5] or None)

                now_ts = _utc_now()
                if expires_at is None or now_ts > expires_at:
                    raise HTTPException(status_code=400, detail="OTP expired. Request a new OTP.")
                if attempts >= max_attempts:
                    raise HTTPException(status_code=400, detail="OTP attempts exceeded. Request a new OTP.")

                expected = _hash_otp(email, otp)
                if not secrets.compare_digest(expected, otp_hash):
                    cur.execute(
                        """
                        UPDATE globalcart.app_email_otps
                        SET attempts = attempts + 1, last_attempt_at = %s
                        WHERE otp_id = %s;
                        """,
                        (now_ts, otp_id),
                    )
                    conn.commit()
                    raise HTTPException(status_code=400, detail="Invalid OTP")

                cur.execute(
                    """
                    UPDATE globalcart.app_email_otps
                    SET consumed_at = %s, last_attempt_at = %s
                    WHERE otp_id = %s;
                    """,
                    (now_ts, now_ts, otp_id),
                )

                customer_id, geo_id = _pick_customer_for_email(conn, email)

                cur.execute(
                    """
                    INSERT INTO globalcart.app_users (email, customer_id, geo_id, display_name, password_hash, verified_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET
                      customer_id = EXCLUDED.customer_id,
                      geo_id = EXCLUDED.geo_id,
                      display_name = EXCLUDED.display_name,
                      password_hash = COALESCE(EXCLUDED.password_hash, globalcart.app_users.password_hash),
                      verified_at = EXCLUDED.verified_at,
                      updated_at = EXCLUDED.updated_at;
                    """,
                    (email, customer_id, geo_id, display_name, pwd_hash, now_ts, now_ts, now_ts),
                )

            conn.commit()

        return AuthSignupVerifyOtpOut(
            email=email,
            customer_id=customer_id,
            geo_id=geo_id,
            display_name=display_name,
        )

    except psycopg.OperationalError:
        demo_customer_id = int((int(hashlib.md5(email.encode("utf-8")).hexdigest(), 16) % 5000) + 1)
        demo_geo_id = int((int(hashlib.md5((email + "|geo").encode("utf-8")).hexdigest(), 16) % 250) + 1)
        demo_name = (email.split("@", 1)[0] or "Customer").replace(".", " ").replace("_", " ").title()
        return AuthSignupVerifyOtpOut(
            email=email,
            customer_id=demo_customer_id,
            geo_id=demo_geo_id,
            display_name=demo_name,
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth schema not ready for signup. "
                "Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )


@router.post("/login", response_model=AuthLoginOut)
def login(req: AuthLoginIn) -> AuthLoginOut:
    email = _validate_email(req.email)
    password = req.password or ""
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT customer_id, geo_id, display_name, password_hash, role
                    FROM globalcart.app_users
                    WHERE email = %s;
                    """,
                    (email,),
                )
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=400, detail="Account not found. Please sign up.")

                customer_id = int(row[0])
                geo_id = int(row[1])
                display_name = row[2]
                pwd_hash = row[3]
                role = str(row[4] or "customer")
                if not pwd_hash:
                    raise HTTPException(status_code=400, detail="Account has no password. Please sign up again.")

                if not _password_verify(password, str(pwd_hash)):
                    raise HTTPException(status_code=401, detail="Invalid email or password")

        return AuthLoginOut(email=email, customer_id=customer_id, geo_id=geo_id, display_name=display_name)

    except psycopg.OperationalError:
        raise HTTPException(
            status_code=503,
            detail="Auth service unavailable (database not reachable). Please try again in a moment.",
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth tables not found. Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )


@router.post("/token", response_model=AuthTokenOut)
def token(req: AuthLoginIn) -> AuthTokenOut:
    email = _validate_email(req.email)
    password = req.password or ""
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    try:
        with get_conn() as conn:
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT customer_id, geo_id, display_name, password_hash, role
                    FROM globalcart.app_users
                    WHERE email = %s;
                    """,
                    (email,),
                )
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=400, detail="Account not found. Please sign up.")

                customer_id = int(row[0])
                geo_id = int(row[1])
                display_name = row[2]
                pwd_hash = row[3]
                role = str(row[4] or "customer")

                if not pwd_hash:
                    raise HTTPException(status_code=400, detail="Account has no password. Please sign up again.")
                if not _password_verify(password, str(pwd_hash)):
                    raise HTTPException(status_code=401, detail="Invalid email or password")

        access_token = create_access_token(
            subject=email,
            role=role,
            extra={"customer_id": customer_id, "geo_id": geo_id, "display_name": display_name},
        )
        return AuthTokenOut(access_token=access_token)

    except psycopg.OperationalError:
        raise HTTPException(
            status_code=503,
            detail="Auth service unavailable (database not reachable). Please try again in a moment.",
        )
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth tables not found. Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )


@router.get("/me", response_model=AuthMeOut)
def me(authorization: str | None = Header(None, alias="Authorization")) -> AuthMeOut:
    token_str = parse_bearer_token(authorization)
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    payload = decode_access_token(token_str)
    email = str(payload.get("sub") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")

    customer_id = payload.get("customer_id")
    geo_id = payload.get("geo_id")
    display_name = payload.get("display_name")
    role = str(payload.get("role") or "customer")

    return AuthMeOut(
        email=email,
        customer_id=int(customer_id) if customer_id is not None else 0,
        geo_id=int(geo_id) if geo_id is not None else 0,
        display_name=str(display_name) if display_name is not None else None,
        role=role,
    )


@router.post("/verify-otp", response_model=AuthVerifyOtpOut)
def verify_otp(req: AuthVerifyOtpIn) -> AuthVerifyOtpOut:
    email = _validate_email(req.email)
    otp = (req.otp or "").strip()
    import logging
    logger = logging.getLogger("api_auth")
    logger.info(f"[DEBUG] verify_otp email={email} otp={otp}")

    if not otp or len(otp) > 16:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    max_attempts = _max_attempts()

    try:
        with get_conn() as conn:
            try:
                logger.info(
                    "[DEBUG] pg_conn host=%s db=%s user=%s",
                    getattr(conn.info, "host", None),
                    getattr(conn.info, "dbname", None),
                    getattr(conn.info, "user", None),
                )
            except Exception:
                pass
            conn.execute("SET TIME ZONE 'UTC';", prepare=False)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT otp_id, otp_hash, expires_at, attempts
                    FROM globalcart.app_email_otps
                    WHERE email = %s AND consumed_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (email,),
                )
                row = cur.fetchone()
                logger.info(f"[DEBUG] fetched row: {row}")

                if row is None:
                    logger.error("[DEBUG] OTP not found for email")
                    raise HTTPException(status_code=400, detail="OTP not found. Request a new OTP.")

                otp_id = int(row[0])
                otp_hash = str(row[1])
                expires_at = row[2]
                attempts = int(row[3])

                now_ts = _utc_now()
                logger.info(f"[DEBUG] now_ts={now_ts}, expires_at={expires_at}")
                if expires_at is None or now_ts > expires_at:
                    logger.error("[DEBUG] OTP expired")
                    raise HTTPException(status_code=400, detail="OTP expired. Request a new OTP.")

                if attempts >= max_attempts:
                    logger.error(f"[DEBUG] attempts exceeded: {attempts} >= {max_attempts}")
                    raise HTTPException(status_code=400, detail="OTP attempts exceeded. Request a new OTP.")

                expected = _hash_otp(email, otp)
                logger.info(f"[DEBUG] comparing hash: expected={expected} stored={otp_hash}")
                if not secrets.compare_digest(expected, otp_hash):
                    logger.error("[DEBUG] Invalid OTP hash mismatch")
                    cur.execute(
                        """
                        UPDATE globalcart.app_email_otps
                        SET attempts = attempts + 1, last_attempt_at = %s
                        WHERE otp_id = %s;
                        """,
                        (now_ts, otp_id),
                    )

                    conn.commit()
                    raise HTTPException(status_code=400, detail="Invalid OTP")

                cur.execute(
                    """
                    UPDATE globalcart.app_email_otps
                    SET consumed_at = %s, last_attempt_at = %s
                    WHERE otp_id = %s;
                    """,
                    (now_ts, now_ts, otp_id),
                )

                customer_id, geo_id = _pick_customer_for_email(conn, email)

                cur.execute(
                    """
                    INSERT INTO globalcart.app_users (email, customer_id, geo_id, verified_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET
                      customer_id = EXCLUDED.customer_id,
                      geo_id = EXCLUDED.geo_id,
                      verified_at = EXCLUDED.verified_at,
                      updated_at = EXCLUDED.updated_at;
                    """,
                    (email, customer_id, geo_id, now_ts, now_ts, now_ts),
                )

            conn.commit()

        return AuthVerifyOtpOut(email=email, customer_id=customer_id, geo_id=geo_id)

    except psycopg.OperationalError:
        demo_customer_id = int((int(hashlib.md5(email.encode("utf-8")).hexdigest(), 16) % 5000) + 1)
        demo_geo_id = int((int(hashlib.md5((email + "|geo").encode("utf-8")).hexdigest(), 16) % 250) + 1)
        return AuthVerifyOtpOut(email=email, customer_id=demo_customer_id, geo_id=demo_geo_id)
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        raise HTTPException(
            status_code=500,
            detail=(
                "Auth tables not found (missing globalcart.app_email_otps). "
                "Run: python3 -m src.run_sql --sql sql/07_app_auth.sql"
            ),
        )
