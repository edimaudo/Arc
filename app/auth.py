from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import quote

from fastapi import HTTPException, Request

from app.db import create_user_record, get_user_by_email, get_user_by_id, claim_legacy_analyses_for_first_user

PBKDF2_ITERATIONS = 310_000
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def normalize_email(email: str) -> str:
    return email.strip().lower()

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.fullmatch(normalize_email(email)))

def safe_next_path(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/dashboard"
    if value.startswith(("/login", "/signup", "/logout")):
        return "/dashboard"
    return value

def set_user_session(request: Request, user: dict) -> None:
    request.session.clear()
    request.session["user_id"] = user["user_id"]
    request.session["user_email"] = user["email"]
    request.session["display_name"] = user.get("display_name", "")

def clear_user_session(request: Request) -> None:
    request.session.clear()

def signup_user(email: str, password: str, display_name: str = "") -> dict:
    email = normalize_email(email)
    if not valid_email(email):
        raise ValueError("Enter a valid email address.")
    if len(password) < 10:
        raise ValueError("Use a password with at least 10 characters.")
    if len(password) > 256:
        raise ValueError("Password must be 256 characters or fewer.")
    if len(display_name.strip()) > 100:
        raise ValueError("Name must be 100 characters or fewer.")
    user_id = secrets.token_urlsafe(18)
    try:
        create_user_record(user_id, email, display_name, hash_password(password))
    except Exception as exc:
        # SQLite reports uniqueness violations differently across runtime versions.
        if get_user_by_email(email):
            raise ValueError("An account already exists for this email. Sign in instead.") from exc
        raise
    claim_legacy_analyses_for_first_user(user_id)
    return get_user_by_id(user_id) or {"user_id": user_id, "email": email, "display_name": display_name.strip()}

def authenticate_user(email: str, password: str) -> dict | None:
    user = get_user_by_email(normalize_email(email))
    if not user or not verify_password(password, user.get("password_hash", "")):
        return None
    return {"user_id": user["user_id"], "email": user["email"], "display_name": user.get("display_name", "")}

def require_authenticated(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
        login_url = "/login?next=" + quote(next_path, safe="/")
        is_api = "/api/" in request.url.path or request.url.path.endswith(("/run", "/ask"))
        if is_api:
            raise HTTPException(status_code=401, detail={"message": "Sign in to continue.", "login_url": login_url})
        raise HTTPException(status_code=303, detail="Sign in to continue.", headers={"Location": login_url})
    user = get_user_by_id(str(user_id))
    if not user:
        request.session.clear()
        login_url = "/login?next=" + quote(request.url.path, safe="/")
        raise HTTPException(status_code=303, detail="Sign in to continue.", headers={"Location": login_url})
    request.state.user = user
    return user
