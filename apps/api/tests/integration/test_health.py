import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_endpoints_report_status(app) -> None:
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            live = await client.get('/api/v1/health/live')
            ready = await client.get('/api/v1/health/ready')
            status = await client.get('/api/v1/health/status')

    assert live.status_code == 200
    assert live.json() == {'status': 'ok'}
    assert ready.status_code == 200
    assert ready.json()['ok'] is False
    assert status.status_code == 200
    assert status.json()['postgres']['ok'] is True
    assert status.json()['redis']['ok'] is True
    assert status.json()['temporal']['ok'] is False
