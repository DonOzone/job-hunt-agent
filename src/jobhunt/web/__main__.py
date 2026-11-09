from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the authenticated Job Hunt API and built web application")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8650)
    parser.add_argument("--data-dir", help="isolated server state, separate from CLI profiles")
    parser.add_argument("--no-worker", action="store_true", help="disable this process's background task worker")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("JOBHUNT_WEB_SECRET"):
        parser.error("Set a stable random JOBHUNT_WEB_SECRET before binding outside loopback")
    try:
        import uvicorn

        from .api import create_app
    except ImportError as exc:
        parser.error(f"Web dependencies are missing ({exc.name}); install job-hunt-agent[web,docs]")
    uvicorn.run(create_app(args.data_dir, start_worker=not args.no_worker), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
