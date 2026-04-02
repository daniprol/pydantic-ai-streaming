from __future__ import annotations

import asyncio
from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from streaming_chat_api.db.base import Base
from streaming_chat_api.models import entities  # noqa: F401


API_ENV_FILE = Path(__file__).resolve().parents[1] / '.env'


def is_running_in_docker() -> bool:
    return Path('/.dockerenv').exists()


def get_database_url() -> str:
    load_dotenv(API_ENV_FILE)
    database_url = os.getenv('ALEMBIC_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL or ALEMBIC_DATABASE_URL is not set for Alembic migrations')

    if is_running_in_docker():
        return database_url

    url = make_url(database_url)
    if url.host == 'postgres':
        return url.set(host='127.0.0.1').render_as_string(hide_password=False)

    return database_url


config = context.config
config.set_main_option('sqlalchemy.url', get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
