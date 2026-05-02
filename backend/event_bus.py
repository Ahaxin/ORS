import asyncio
from collections import defaultdict

class EventBus:
    def __init__(self):
        self._queues: dict[int, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, project_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[project_id].append(q)
        return q

    def unsubscribe(self, project_id: int, q: asyncio.Queue):
        self._queues[project_id].remove(q)

    async def publish(self, project_id: int, event: dict):
        for q in self._queues[project_id]:
            await q.put(event)

event_bus = EventBus()
