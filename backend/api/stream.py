import json, asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from backend.event_bus import event_bus

router = APIRouter()

@router.get("/projects/{project_id}/stream")
async def stream_project(project_id: int, request: Request):
    q = event_bus.subscribe(project_id)

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(project_id, q)

    return StreamingResponse(generator(), media_type="text/event-stream")
