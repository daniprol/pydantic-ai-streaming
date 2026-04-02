from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine.url import make_url


LOCAL_SERVICE_HOSTS = {
    'postgres': '127.0.0.1',
}


def is_running_in_docker() -> bool:
    return Path('/.dockerenv').exists()


def normalize_local_service_url(url: str) -> str:
    if is_running_in_docker():
        return url

    parsed_url = make_url(url)
    local_host = LOCAL_SERVICE_HOSTS.get(parsed_url.host)
    if local_host is None:
        return url

    return parsed_url.set(host=local_host).render_as_string(hide_password=False)
