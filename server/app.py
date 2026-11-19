import logging
import threading
from pathlib import Path

import config
import rag.store as store
from chat import chat_bp
from documents import documents_bp
from flask import Flask, abort, jsonify, request, send_from_directory
from llm import LLMConfigError, describe
from rag import stats
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import safe_join

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

CLIENT_DIST = config.BASE_DIR.parent / "client" / "dist"

app = Flask(__name__)
# Render terminates TLS in front of the app, so trust its X-Forwarded-For for
# the per-IP rate limit.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
app.register_blueprint(chat_bp, url_prefix="/api")
app.register_blueprint(documents_bp, url_prefix="/api")


@app.after_request
def add_cors_headers(response):
    if config.ALLOWED_ORIGIN and request.headers.get("Origin") == config.ALLOWED_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = config.ALLOWED_ORIGIN
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


@app.get("/api/hello")
def hello():
    return jsonify({"message": "Hello from Flask!"})


@app.get("/api/health")
def health():
    try:
        llm_info = describe()
    except LLMConfigError as exc:
        logging.getLogger(__name__).error("%s", exc)
        return jsonify({"status": "error", "error": str(exc)}), 500
    try:
        index = stats()
    except Exception:
        logging.getLogger(__name__).exception("index stats failed")
        return jsonify({"status": "degraded", "index": None, **llm_info}), 503
    if index.get("updating"):
        # Stay up (200) so the platform does not restart-loop the service.
        return jsonify({"status": "updating", "index": index, **llm_info})
    return jsonify({"status": "ok", "index": index, **llm_info})


@app.get("/")
@app.get("/<path:path>")
def client(path: str = "index.html"):
    """Serve the built Vite app; unknown paths fall back to index.html."""
    if path.startswith("api/"):
        abort(404)
    if CLIENT_DIST.is_dir():
        target = safe_join(str(CLIENT_DIST), path)
        if target and Path(target).is_file():
            return send_from_directory(CLIENT_DIST, path)
        if (CLIENT_DIST / "index.html").is_file():
            return send_from_directory(CLIENT_DIST, "index.html")
    abort(404)


def _warmup() -> None:
    try:
        store.warm()
    except Exception:
        log.exception("warmup failed")


if config.WARMUP:
    threading.Thread(target=_warmup, name="warmup", daemon=True).start()


if __name__ == "__main__":
    app.run(port=config.PORT, debug=False)
