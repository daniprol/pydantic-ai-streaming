from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.docker
@pytest.mark.asyncio
async def test_alembic_migration_creates_chat_tables(postgres_dsn: str) -> None:
    project_root = Path(__file__).resolve().parents[4]
    api_dir = project_root / 'apps' / 'api'
    engine = create_async_engine(postgres_dsn)

    try:
        for attempt in range(1, 11):
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('drop schema public cascade'))
                    await connection.execute(text('create schema public'))
                break
            except Exception:
                if attempt == 10:
                    raise
                await asyncio.sleep(1)

        env = {
            **os.environ,
            'ALEMBIC_DATABASE_URL': postgres_dsn,
            'DATABASE_URL': postgres_dsn,
        }
        subprocess.run(
            [
                'uv',
                'run',
                'alembic',
                '-c',
                'alembic.ini',
                'upgrade',
                'head',
            ],
            cwd=api_dir,
            check=True,
            env=env,
        )

        async with engine.begin() as connection:
            tables = set(
                await connection.scalars(
                    text(
                        "select tablename from pg_tables where schemaname = 'public' order by tablename"
                    )
                )
            )

        assert 'alembic_version' in tables
        assert 'chat_conversation' in tables
        assert 'chat_message' in tables
        assert 'chat_pending_tool_call' in tables
    finally:
        await engine.dispose()
