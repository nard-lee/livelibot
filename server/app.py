import logging
import threading

import config
import rag.store as store
from chat import chat_bp
from documents import documents_bp
from flask import Flask, jsonify, request
from llm import LLMConfigError, describe
from rag import stats
from werkzeug.middleware.proxy_fix import ProxyFix

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

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
    return jsonify({"status": "ok", "index": index, **llm_info})


def _warmup() -> None:
    try:
        store.warm()
    except Exception:
        log.exception("warmup failed")


if config.WARMUP:
    threading.Thread(target=_warmup, name="warmup", daemon=True).start()


if __name__ == "__main__":
    app.run(port=config.PORT, debug=False)
