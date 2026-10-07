from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

for candidate in (PROJECT_ROOT / '.env', PROJECT_ROOT / '.env.local', Path.cwd() / '.env', Path.cwd() / '.env.local'):
    if candidate.exists():
        load_dotenv(candidate, override=False)


def env(name: str, default: str = '') -> str:
    return os.getenv(name, default).strip()


APP_NAME = env('APP_NAME', 'Arc')
QLOO_API_KEY = env('QLOO_API_KEY')
QLOO_BASE_URL = env('QLOO_BASE_URL', 'https://hackathon.api.qloo.com').rstrip('/')
QLOO_TIMEOUT_SECONDS = float(env('QLOO_TIMEOUT_SECONDS', '25') or '25')
GEMINI_API_KEY = env('GEMINI_API_KEY')
GEMINI_MODEL = env('GEMINI_MODEL', 'gemini-2.5-pro')
GEMINI_TIMEOUT_SECONDS = float(env('GEMINI_TIMEOUT_SECONDS', '120') or '120')
MAX_DOCUMENT_BYTES = int(env('MAX_DOCUMENT_BYTES', '12000000') or '12000000')
MAX_DOCUMENTS_PER_ANALYSIS = int(env('MAX_DOCUMENTS_PER_ANALYSIS', '8') or '8')
MAX_TOOL_TURNS = int(env('MAX_TOOL_TURNS', '12') or '12')


def missing_credentials() -> list[str]:
    return [name for name, value in [('GEMINI_API_KEY', GEMINI_API_KEY), ('QLOO_API_KEY', QLOO_API_KEY)] if not value]
