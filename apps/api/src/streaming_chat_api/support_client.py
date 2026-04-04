from __future__ import annotations


class FakeSupportClient:
    async def lookup_order_status(self, order_id: str) -> dict[str, str]:
        statuses = ['processing', 'awaiting-shipment', 'delivered']
        status = statuses[sum(order_id.encode('utf-8')) % len(statuses)]
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
                'title': 'How conversation history works',
                'summary': 'Overview of conversation persistence and reconnect support.',
                'url': 'https://example.com/help/conversation-history',
            },
        ]
