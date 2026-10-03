#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Usage:
    python server.py port=80 dir=C:\website VERBOSE=True
    python server.py port=8080 dir=./www VERBOSE=False

Arguments:
    port    Listening port, default 80
    dir     Website root directory, default current directory
    VERBOSE Whether to print request logs, accepts True/False (case-insensitive), default True
"""

import os
import sys
import shutil
import subprocess
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


# ---------------- Default configuration ----------------

DEFAULT_PORT = 80
DEFAULT_DIR = os.getcwd()

# Path to the php-cgi executable. If it is already on PATH, keep 'php-cgi';
# otherwise set an absolute path, e.g. Windows: r'C:\php\php-cgi.exe'
PHP_CGI = shutil.which('php-cgi') or shutil.which('php-cgi.exe') or 'php-cgi'

# Runtime log switch (overridden by command-line arguments)
VERBOSE = True


# ---------------- Argument parsing ----------------

def parse_args(argv):
    """
    Parse arguments of the form key=value.
    Returns a dict with keys normalized to lowercase (port/dir/verbose).
    """
    opts = {}
    for arg in argv:
        if '=' not in arg:
            print(f"Ignoring unrecognized argument: {arg}")
            continue
        key, value = arg.split('=', 1)
        opts[key.strip().lower()] = value.strip()
    return opts


def to_bool(value, default=True):
    """Convert True/False etc. to bool, case-insensitive."""
    if value is None:
        return default
    return value.strip().lower() in ('true', '1', 'yes', 'on', 'y', 't')


# ---------------- Helper functions ----------------

def build_cgi_env(handler, script_path, path_info, query_string, content_length):
    """Build the environment variables passed to php-cgi (CGI/1.1 convention)."""
    env = os.environ.copy()

    server_name, server_port = handler.server.server_address[:2]
    if not isinstance(server_name, str):
        server_name = 'localhost'

    env.update({
        'GATEWAY_INTERFACE': 'CGI/1.1',
        'SERVER_PROTOCOL':   handler.protocol_version,
        'SERVER_SOFTWARE':   'python-http-server-php',
        'REQUEST_METHOD':    handler.command,
        'REQUEST_URI':       handler.path,
        'QUERY_STRING':      query_string,
        'SCRIPT_NAME':       handler.path.split('?', 1)[0],
        'SCRIPT_FILENAME':   script_path,
        'PATH_INFO':         path_info,
        'DOCUMENT_ROOT':     handler.directory,
        'SERVER_NAME':       server_name,
        'SERVER_PORT':       str(server_port),
        'REMOTE_ADDR':       handler.client_address[0],
        'REMOTE_PORT':       str(handler.client_address[1]),
        'CONTENT_LENGTH':    str(content_length),
        'CONTENT_TYPE':      handler.headers.get('Content-Type', ''),
        'REDIRECT_STATUS':   '1',   # required by php-cgi
    })

    for key, value in handler.headers.items():
        name = 'HTTP_' + key.upper().replace('-', '_')
        if name in ('HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH'):
            continue
        env[name] = value

    return env


def split_php_output(raw):
    """Split php-cgi output into (list of headers, body bytes)."""
    for sep in (b'\r\n\r\n', b'\n\n'):
        idx = raw.find(sep)
        if idx != -1:
            header_blob = raw[:idx]
            body = raw[idx + len(sep):]
            headers = []
            for line in header_blob.replace(b'\r\n', b'\n').split(b'\n'):
                if b':' in line:
                    k, v = line.split(b':', 1)
                    headers.append((k.decode('latin-1').strip(),
                                    v.decode('latin-1').strip()))
            return headers, body
    return [], raw


# ---------------- Request handler ----------------

class PHPHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Combined static file + PHP handler."""

    server_version = 'PHPHTTP/1.0'

    @staticmethod
    def _is_php(path):
        p = path.split('?', 1)[0].lower()
        return p.endswith(('.php', '.php5', '.phtml'))

    def _handle_php(self):
        parsed = urllib.parse.urlparse(self.path)
        url_path = urllib.parse.unquote(parsed.path)
        query = parsed.query

        rel = url_path.lstrip('/').replace('/', os.sep)
        doc_root = self.directory or os.getcwd()
        parts = rel.split(os.sep) if rel else []

        script_rel = None
        path_info = ''
        for i in range(len(parts), 0, -1):
            candidate = os.path.join(doc_root, *parts[:i])
            if os.path.isfile(candidate) and candidate.lower().endswith(
                    ('.php', '.php5', '.phtml')):
                script_rel = candidate
                path_info = '/' + '/'.join(parts[i:]) if i < len(parts) else ''
                break

        if script_rel is None:
            self.send_error(404, 'PHP script not found')
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            content_length = 0
        body = self.rfile.read(content_length) if content_length else b''

        env = build_cgi_env(self, script_rel, path_info, query, content_length)

        try:
            proc = subprocess.run(
                [PHP_CGI],
                input=body,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=os.path.dirname(script_rel) or doc_root,
                timeout=60,
            )
        except FileNotFoundError:
            self.send_error(
                500,
                f'php-cgi not found (tried: {PHP_CGI}). '
                f'Please install PHP or set the PHP_CGI path.'
            )
            return
        except subprocess.TimeoutExpired:
            self.send_error(504, 'PHP script timed out')
            return

        if proc.returncode != 0 and not proc.stdout:
            self.send_error(
                500,
                f'php-cgi error: {proc.stderr.decode("utf-8", "replace")}'
            )
            return

        headers, out_body = split_php_output(proc.stdout)

        self.send_response(200)
        has_content_type = False
        has_content_length = False
        for k, v in headers:
            lk = k.lower()
            if lk == 'status':
                try:
                    code = int(v.split()[0])
                    self.send_response_only(code)
                except (ValueError, IndexError):
                    pass
                continue
            if lk == 'content-type':
                has_content_type = True
            if lk == 'content-length':
                has_content_length = True
            self.send_header(k, v)

        if not has_content_type:
            self.send_header('Content-Type', 'text/html; charset=utf-8')
        if not has_content_length:
            self.send_header('Content-Length', str(len(out_body)))

        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(out_body)

    def do_GET(self):
        if self._is_php(self.path):
            return self._handle_php()
        return super().do_GET()

    def do_HEAD(self):
        if self._is_php(self.path):
            return self._handle_php()
        return super().do_HEAD()

    def do_POST(self):
        if self._is_php(self.path):
            return self._handle_php()
        self.send_error(501, 'POST only supported for PHP')

    def do_PUT(self):
        if self._is_php(self.path):
            return self._handle_php()
        self.send_error(501, 'PUT only supported for PHP')

    def do_DELETE(self):
        if self._is_php(self.path):
            return self._handle_php()
        self.send_error(501, 'DELETE only supported for PHP')

    def log_message(self, fmt, *args):
        if VERBOSE:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(),
                                            fmt % args))


# ---------------- Entry point ----------------

def main():
    global VERBOSE

    opts = parse_args(sys.argv[1:])

    # Port
    try:
        port = int(opts.get('port', DEFAULT_PORT))
    except ValueError:
        print(f"Invalid port: {opts.get('port')}")
        sys.exit(1)

    # Directory
    root = os.path.abspath(opts.get('dir', DEFAULT_DIR))
    if not os.path.isdir(root):
        print(f"Directory does not exist: {root}")
        sys.exit(1)

    # VERBOSE: lowercase before checking
    VERBOSE = to_bool(opts.get('verbose'), default=True)

    os.chdir(root)

    print(f"PHP_CGI      : {PHP_CGI}")
    print(f"DOCUMENT_ROOT: {root}")
    print(f"VERBOSE      : {VERBOSE}")
    print(f"Listening on : http://localhost:{port}/")
    print("Press Ctrl+C to stop\n")

    handler = partial(PHPHTTPRequestHandler, directory=root)
    httpd = ThreadingHTTPServer(('0.0.0.0', port), handler)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
