import logging
import threading

import config
import rag.store as store
from chat import chat_bp
from documents import documents_bp
from flask import Flask, jsonify
from llm import LLMConfigError, describe
from rag import stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

app = Flask(__name__)
app.register_blueprint(chat_bp, url_prefix="/api")
app.register_blueprint(documents_bp, url_prefix="/api")


@app.after_request
def add_cors_headers(response):
    # The Vite dev server proxies /api, but a deployed client may call this
    # origin directly, so honour CLIENT_ORIGIN from the environment.
    response.headers["Access-Control-Allow-Origin"] = config.CLIENT_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
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
    # The Flask debug reloader leaks processes on Windows (the old server keeps
    # the port open via SO_REUSEADDR), so it is opt-in through DEBUG=1.
    app.run(debug=config.DEBUG, port=config.PORT)
