import asyncio
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config_manager import ConfigManager
from ai_client import AIClient
from email_processor import EmailProcessor
from style_analyzer import StyleAnalyzer
from imap_client import IMAPClient

app = FastAPI(title="Email AI Assistant")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

cfg = ConfigManager()
processor = EmailProcessor(cfg)
analyzer = StyleAnalyzer(cfg)

_subscribers: list[asyncio.Queue] = []
_is_processing = False
_current_task: asyncio.Task | None = None


def _broadcast(event: dict):
    data = json.dumps(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


async def _push(event: dict):
    _broadcast(event)


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/config")
async def get_config():
    config = cfg.get_config()
    safe = json.loads(json.dumps(config))
    if safe.get("imap", {}).get("password"):
        safe["imap"]["password"] = "••••••••"
    if safe.get("ai", {}).get("cloud_api_key"):
        safe["ai"]["cloud_api_key"] = "••••••••"
    return safe


@app.post("/api/config")
async def save_config(data: dict):
    current = cfg.get_config()
    if data.get("imap", {}).get("password") == "••••••••":
        data["imap"]["password"] = current.get("imap", {}).get("password", "")
    if data.get("ai", {}).get("cloud_api_key") == "••••••••":
        data["ai"]["cloud_api_key"] = current.get("ai", {}).get("cloud_api_key", "")
    cfg.save_config(data)
    return {"status": "saved"}


@app.get("/api/style")
async def get_style():
    return cfg.get_style_profile()


@app.post("/api/style")
async def update_style(data: dict):
    cfg.save_style_profile(data)
    return {"status": "saved"}


@app.get("/api/history")
async def get_history():
    return cfg.get_history()


@app.get("/api/status")
async def get_status():
    return {"processing": _is_processing}


@app.post("/api/cancel")
async def cancel():
    global _current_task
    if _current_task and not _current_task.done():
        _current_task.cancel()
        return {"status": "cancelled"}
    return {"status": "nothing_running"}


@app.post("/api/clear-processed")
async def clear_processed():
    from config_manager import PROCESSED_FILE
    if PROCESSED_FILE.exists():
        PROCESSED_FILE.unlink()
    return {"status": "cleared"}


@app.post("/api/test-imap")
async def test_imap():
    config = cfg.get_config()
    try:
        folders = await asyncio.to_thread(_list_folders, config)
        return {"ok": True, "folders": folders}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/test-ai")
async def test_ai():
    config = cfg.get_config()
    ai = AIClient(config)
    result = await ai.test_connection()
    return result


@app.post("/api/analyze")
async def analyze_emails():
    global _is_processing, _current_task
    if _is_processing:
        raise HTTPException(status_code=409, detail="Already processing")
    _current_task = asyncio.create_task(_run_analysis())
    return {"status": "started"}


@app.post("/api/style/analyze")
async def analyze_style(data: dict = {}):
    global _is_processing, _current_task
    if _is_processing:
        raise HTTPException(status_code=409, detail="Already processing")
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    subject_filter = data.get("subject_filter") or None
    _current_task = asyncio.create_task(_run_style_analysis(start_date, end_date, subject_filter))
    return {"status": "started"}


@app.get("/api/stream")
async def stream():
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(queue)

    async def generate():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"heartbeat\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_analysis():
    global _is_processing
    _is_processing = True
    queue = _AsyncBroadcastAdapter()
    try:
        result = await processor.process(queue)
        await _push({
            "type": "done",
            "message": f"Done! {result['drafts_saved']} draft(s) saved, {result['errors']} error(s).",
            "result": result,
        })
    except asyncio.CancelledError:
        await _push({"type": "error", "message": "Cancelled."})
    except Exception as e:
        logger.exception("Email analysis failed")
        msg = str(e) or f"{type(e).__name__} (no message)"
        await _push({"type": "error", "message": msg})
    finally:
        _is_processing = False


async def _run_style_analysis(start_date: str = None, end_date: str = None, subject_filter: str = None):
    global _is_processing
    _is_processing = True
    queue = _AsyncBroadcastAdapter()
    try:
        result = await analyzer.analyze(queue, start_date=start_date, end_date=end_date, subject_filter=subject_filter)
        await _push({
            "type": "done",
            "message": f"Style analysis complete! Analyzed {result['emails_analyzed']} emails.",
            "result": result,
        })
    except asyncio.CancelledError:
        await _push({"type": "error", "message": "Cancelled."})
    except Exception as e:
        logger.exception("Style analysis failed")
        msg = str(e) or f"{type(e).__name__} (no message)"
        await _push({"type": "error", "message": msg})
    finally:
        _is_processing = False


def _list_folders(config: dict):
    with IMAPClient(config) as client:
        return client.list_folders()


class _AsyncBroadcastAdapter:
    async def put(self, event: dict):
        await _push(event)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=7890, reload=False)
