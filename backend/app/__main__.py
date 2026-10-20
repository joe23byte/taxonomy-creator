"""Run the API server: ``python -m app`` (binds to localhost by default)."""
import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False, log_level="info")
