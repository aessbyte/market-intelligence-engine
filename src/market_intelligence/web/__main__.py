"""Run the optional ASGI adapter on localhost; deploy behind an HTTPS proxy."""

import argparse
import logging

import uvicorn

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Intelligence Engine web API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(create_app(), host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
