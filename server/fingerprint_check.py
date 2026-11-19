"""Print the index fingerprint components for this checkout.

Run from the server folder:

    python fingerprint_check.py
    python fingerprint_check.py --json

Nothing is embedded and no files are written; this only hashes the sources and
shows the committed index's fingerprint so a local checkout and a Render shell
can be compared line by line.
"""

import argparse
import json
import sys

import config
from rag.index import compute_fingerprint, fingerprint_components


def _committed() -> dict | None:
    try:
        meta = json.loads((config.INDEX_DIR / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "fingerprint": meta.get("fingerprint"),
        "components": meta.get("fingerprint_components"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the index fingerprint components.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    components = fingerprint_components()
    fingerprint = compute_fingerprint(components)
    committed = _committed()

    if args.json:
        print(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "components": components,
                    "committed": committed,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(f"fingerprint: {fingerprint}")
    for key in ("INDEX_VERSION", "EMBED_MODEL", "RAG_CHUNK_CHARS", "RAG_CHUNK_OVERLAP"):
        print(f"{key}: {components[key]}")

    files = components["files"]
    print(f"files ({len(files)}):")
    for name in sorted(files):
        print(f"  {name}  {files[name]}")

    if committed is None:
        print("committed index: none")
    else:
        stored = committed["fingerprint"]
        state = "match" if stored == fingerprint else "MISMATCH"
        print(f"committed index: {stored} ({state})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
