from __future__ import annotations

import logging
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from autofag.auth.browser import PlaywrightStudentwebPage
from autofag.config import AppConfig
from autofag.presentation import RichPresenter
from autofag.studentweb.page import NotAuthenticated, PageUnavailable

PAGE = "<html><body><p>autofag smoke</p></body></html>"


def serve(directory: Path) -> ThreadingHTTPServer:
    (directory / "index.html").write_text(PAGE)
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with TemporaryDirectory() as workspace:
        root = Path(workspace)
        server = serve(root)
        host, port = server.server_address[:2]

        config = AppConfig()
        config.auth.headless = True
        config.auth.profile_dir = root / "profile"
        config.studentweb.base_url = f"http://{host}:{port}/"
        config.studentweb.courses_path = "index.html"

        page = PlaywrightStudentwebPage(config, logging.getLogger("autofag"), RichPresenter())
        try:
            page.open()
        except NotAuthenticated:
            return 0
        except PageUnavailable as error:
            print(f"nettleseren startet ikke: {error}", file=sys.stderr)
            return 1
        finally:
            page.close()
            server.shutdown()

    print("siden ble lest uten at innloggingssjekken slo til", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
