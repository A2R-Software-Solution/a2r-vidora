"""Explicit production release: inspect, back up, then apply the additive migration.

Run from functions with --apply to mutate. Secret values/errors are never printed.
Backups contain private data; keep secrets/ private and outside deployment artifacts.
"""
import argparse
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

PROJECT = "vidoraai-2bbce"
EXPECTED = "5a08b732d74f"
TARGET = "6c10a9e721df"


async def verify_concurrency(url):
    import hashlib
    import uuid
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.distributed_rate_limit import admission_statement
    key = "release-check:" + uuid.uuid4().hex
    digest = hashlib.sha256(key.encode()).hexdigest()
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"statement_cache_size": 0})
    async def attempt():
        async with engine.begin() as db:
            return (await db.execute(admission_statement(key, 5, 3600))).scalar_one_or_none() is not None
    try:
        results = await asyncio.gather(*(attempt() for _ in range(12)))
        if sum(results) != 5:
            raise RuntimeError("Concurrent budget assertion failed")
        print("Shared database concurrency: 5 admitted, 7 rejected across 12 connections.")
    finally:
        async with engine.begin() as db:
            await db.execute(text("DELETE FROM rate_limit_buckets WHERE scope_key=:key"), {"key": digest})
        await engine.dispose()


async def revision(url):
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as db:
            return (await db.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify-concurrency", action="store_true")
    args = parser.parse_args()
    os.chdir(Path(__file__).resolve().parents[1])
    cli = shutil.which("gcloud")
    secret = subprocess.run([cli, "secrets", "versions", "access", "latest", "--secret=DATABASE_URL", f"--project={PROJECT}"], capture_output=True, text=True, timeout=60)
    if secret.returncode:
        raise RuntimeError("Secret access failed; no migration attempted")
    url = secret.stdout.strip()
    versions = asyncio.run(revision(url))
    print("Database revision:", versions)
    if versions == [TARGET]:
        print("Already migrated; no changes.")
        if args.verify_concurrency:
            asyncio.run(verify_concurrency(url))
        return
    if versions != [EXPECTED]:
        raise RuntimeError("Unexpected schema revision; refusing migration")
    if not args.apply:
        print("Read-only inspection complete; use --apply for backup and migration.")
        return
    parsed = make_url(url)
    backup_dir = Path("secrets/release-backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".dump")
    env = os.environ.copy()
    env.update(PGHOST=parsed.host or "", PGPORT=str(parsed.port or 5432), PGUSER=parsed.username or "", PGPASSWORD=parsed.password or "", PGDATABASE=parsed.database or "", PGSSLMODE="require", PGCONNECT_TIMEOUT="20")
    result = subprocess.run([shutil.which("pg_dump"), "--format=custom", "--no-owner", "--no-acl", f"--file={backup}"], env=env, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError("Backup failed; no migration attempted")
    print("Private backup saved:", backup)
    env["DATABASE_URL"] = url
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", TARGET], env=env, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Migration failed; deployment must not proceed")
    if asyncio.run(revision(url)) != [TARGET]:
        raise RuntimeError("Migration verification failed")
    print("Migration verified:", TARGET)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Release database step failed:", type(exc).__name__, "(details suppressed to protect credentials)")
        raise SystemExit(1) from None
