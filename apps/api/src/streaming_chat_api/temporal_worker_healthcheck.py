from __future__ import annotations

import asyncio

from streaming_chat_api.temporal_worker import check_temporal_worker_health


def main() -> None:
    asyncio.run(check_temporal_worker_health())


if __name__ == '__main__':
    main()
