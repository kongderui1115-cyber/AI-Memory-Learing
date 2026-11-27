"""Cross-platform Uvicorn entry with psycopg-compatible Windows event loops."""

import argparse
import asyncio
import sys


# Spawned reload workers import this module before creating their event loop.
def configure_event_loop():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


configure_event_loop()


def main():
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("app", nargs="?", default="app.main:app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(args.app, host=args.host, port=args.port, reload=args.reload, loop="none")


if __name__ == "__main__":
    main()
