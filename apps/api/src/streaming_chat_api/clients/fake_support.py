from __future__ import annotations

from random import Random

import httpx


class FakeSupportClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http_client = http_client
        self._rng = Random(7)

    async def lookup_order_status(self, order_id: str) -> dict[str, str]:
        statuses = ['processing', 'awaiting-shipment', 'delivered']
        status = statuses[self._rng.randint(0, len(statuses) - 1)]
        return {
            'order_id': order_id,
            'status': status,
            'eta': '2 business days' if status != 'delivered' else 'completed',
        }

    async def check_platform_health(self, service_name: str) -> dict[str, str]:
        return {
            'service': service_name,
            'status': 'operational',
            'region': 'west-europe',
        }

    async def search_help_articles(self, question: str) -> list[dict[str, str]]:
        return [
            {
                'title': 'Troubleshooting streaming delays',
                'summary': f'Help-center match for: {question}',
                'url': 'https://example.com/help/streaming-delays',
            },
            {
                'title': 'How session-based support chats work',
                'summary': 'Overview of session history and reconnect support.',
                'url': 'https://example.com/help/session-chats',
            },
        ]
