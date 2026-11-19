import argparse
import logging
import sys

import config
from rag import rebuild
from rag.urls import cache_path, cache_url, read_urls

log = logging.getLogger("ingest")


def _fetch_urls(urls: list[str]) -> None:
    config.URL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for url in urls:
        wanted.add(cache_path(url).name)
        try:
            payload = cache_url(url)
        except ValueError as exc:
            log.warning("skipped: %s", exc)
            continue
        log.info("cached %s (%d chars)", url, len(payload["text"]))

    for stale in config.URL_CACHE_DIR.glob("*.json"):
        if stale.name not in wanted:
            stale.unlink()
            log.info("removed stale cache %s", stale.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the knowledge index.")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="skip fetching URLs from knowledge/urls.txt",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    if not args.local_only:
        urls = read_urls()
        log.info("fetching %d URL(s)", len(urls))
        _fetch_urls(urls)

    index = rebuild()
    for document in index["details"]:
        log.info("%s: %d chunk(s)", document["source"], document["chunks"])
    log.info(
        "index ready: %d chunk(s) from %d document(s), %d dim(s), built %s",
        index["chunks"],
        index["documents"],
        index["dimensions"],
        index["built_at"],
    )
    print(
        f"Index ready: {index['chunks']} chunk(s) from {index['documents']} "
        f"document(s), {index['dimensions']} dim(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
