"""Local static preview only; this server never receives or processes PDFs."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent / 'dist'
    if not (folder / 'index.html').is_file():
        parser.error('Build the site first: cd web, npm ci, npm run build')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(SimpleHTTPRequestHandler, directory=str(folder)))
    except OSError as exc:
        parser.exit(1, f'Could not start the local preview on port {args.port}: {exc}. Try --port 4175.\n')
    print(f'Open http://127.0.0.1:{args.port}/ in your browser. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
