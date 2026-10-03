# Server_python_has_php

A lightweight web server built on the Python standard library, supporting both **static files** and **PHP scripts**.
No Apache / Nginx required — with Python and `php-cgi` installed, a single command spins up a local website that can execute PHP.

## Features

- Pure Python standard library, zero third-party dependencies
- Static file serving (HTML / CSS / JS / images, etc.)
- PHP support (executed via `php-cgi`)
- Supports `GET` / `POST` / `HEAD` / `PUT` / `DELETE`
- Multi-threaded, handles multiple requests concurrently
- Command-line arguments for port, directory, and logging
- Cross-platform (Windows / Linux / macOS)

## Requirements

| Dependency | Notes |
|------------|-------|
| Python | 3.7+ |
| PHP (php-cgi) | Required to execute `.php` files; not needed for static-only use |

### Installing php-cgi

**Windows**
1. Download PHP from https://windows.php.net/download/ (the Non Thread Safe zip package is fine).
2. Extract to e.g. `C:\php`; it contains `php-cgi.exe`.
3. Add `C:\php` to the system `PATH`, or specify the path manually in the script later.

**Ubuntu / Debian**
```bash
sudo apt install php-cgi
```

**macOS**
```bash
brew install php
```

Verify the installation:
```bash
php-cgi -v
```
If a version number is printed, it works.

## Quick Start

### 1. Save the script

Save `server.py` to any directory.

### 2. Start

```bash
python server.py port=80 dir=C:\网站 VERBOSE=True
```

Open http://localhost/ in your browser.

### 3. Stop

Press `Ctrl+C` in the terminal.

## Command-Line Arguments

Arguments use the form `key=value`, separated by spaces, in any order, all optional.

| Argument | Default | Description |
|----------|---------|-------------|
| `port` | `80` | Listening port |
| `dir` | Current directory | Website root directory |
| `VERBOSE` | `True` | Whether to print request logs; accepts `True` / `False` (case-insensitive) |

### Examples

```bash
# Full form
python server.py port=80 dir=C:\网站 VERBOSE=True

# Different port, logging off
python server.py port=8080 dir=./www VERBOSE=False

# Directory only, defaults for the rest
python server.py dir=C:\网站

# All defaults (current directory, port 80)
python server.py
```

## Directory Structure

```
your-website-root/
├── index.html          # Static file, returned as-is
├── style.css
├── app.js
├── info.php            # PHP file, will be executed
└── sub/
    └── test.php
```

## Usage Examples

### Static page `index.html`

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Home</title></head>
<body><h1>Hello, static world</h1></body>
</html>
```

Visit: http://localhost/index.html

### PHP page `info.php`

```php
<?php
header('Content-Type: text/html; charset=utf-8');
echo "Current time: " . date("Y-m-d H:i:s");
phpinfo();
```

Visit: http://localhost/info.php

### Form handling `form.php`

```php
<?php
header('Content-Type: text/html; charset=utf-8');
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name = $_POST['name'] ?? '(empty)';
    echo "Hello, " . htmlspecialchars($name);
} else {
    echo '<form method="post">
            <input name="name" placeholder="Enter your name">
            <button type="submit">Submit</button>
          </form>';
}
```

## Configuring the PHP Path

By default the script locates `php-cgi` via `PATH`:

```python
PHP_CGI = shutil.which('php-cgi') or shutil.which('php-cgi.exe') or 'php-cgi'
```

If it is not on the system PATH, open `server.py` and set an absolute path:

```python
# Windows
PHP_CGI = r'C:\php\php-cgi.exe'

# Linux / macOS
PHP_CGI = '/usr/bin/php-cgi'
```

## How It Works

```
Request ──► Check extension ──► .php ? ──► Invoke php-cgi ──► Return result
                                  │
                                  └──► No ──► Read file and return directly
```

- Static files: read from disk → send as-is.
- PHP files: build CGI environment variables → call `php-cgi` → parse output → return.

## FAQ

| Symptom | Cause / Fix |
|---------|-------------|
| `500 php-cgi not found` | PHP not installed or not on PATH; see "Configuring the PHP Path" |
| PHP source code shown in browser | Request did not take the PHP branch; check that the extension is `.php` |
| `Security Alert! The PHP CGI cannot be accessed directly` | Missing `REDIRECT_STATUS` env var; the script sets it — do not remove |
| Garbled non-ASCII text | Add `header('Content-Type: text/html; charset=utf-8');` in PHP |
| Port in use / permission denied | Use another port; port 80 on Linux/macOS requires `sudo` |
| No request logs | Check that `VERBOSE=True` |

## Limitations and Notes

- **For development and debugging only** — not suitable for production.
- No HTTPS, no access control, no connection reuse optimization.
- For production, use **Nginx + PHP-FPM** or **Apache**.
- The script executes PHP code under the website directory — **do not expose it to the public internet**.

## License

MIT
