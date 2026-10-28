#!/usr/bin/env python3
"""Build a small repository full of ghosts, with a believable history.

    python examples/make_demo_repo.py /tmp/demo-repo

Includes: files that were deleted (the ghosts), a file that was renamed and
survives (must NOT be a ghost), a renamed-then-deleted file (its life before
the rename counts), and a deleted binary (skipped).
"""
import os
import shutil
import subprocess
import sys

FTP = '''import ftplib

def upload_report(host, user, password, path):
    """Push the nightly report to the partner's FTP server."""
    with ftplib.FTP(host) as ftp:
        ftp.login(user, password)
        with open(path, "rb") as fh:
            ftp.storbinary("STOR report.csv", fh)

def retry_upload(*args, tries=3):
    for _ in range(tries):
        try:
            return upload_report(*args)
        except OSError:
            pass
'''
SHIM = '''// Makes IE8 behave. Mostly.
function $(sel) { return document.querySelectorAll(sel); }
function ajaxCompat(url, cb) {
  var x = new XMLHttpRequest();
  x.onload = function () { cb(x.responseText); };
  x.open("GET", url); x.send();
}
'''
CAPTCHA = '''import random

class Captcha:
    def issue(self):
        a, b = random.randint(1, 9), random.randint(1, 9)
        return f"What is {a}+{b}?", a + b

def verify(answer, expected):
    return int(answer) == expected
'''
HEROKU = '''#!/bin/sh
git push heroku main
heroku run python manage.py migrate
echo "deployed. pray."
'''
ROADMAP = "# Roadmap 2020\n- Ship the blockchain feature\n- Dark mode (maybe)\n- Rewrite everything in Rust\n"
LOGGER = '''const winston = require('winston');

function makeLogger(name) {
  return winston.createLogger({ level: 'info', defaultMeta: { name } });
}

module.exports = { makeLogger };
'''
UTIL = "def slugify(s):\n    return s.lower().replace(' ', '-')\n\ndef clamp(x, lo, hi):\n    return max(lo, min(hi, x))\n"

# (date, author, message, {"write": {path: text}, "append": {path: text}, "rm": [paths], "mv": [(a, b)]})
STEPS = [
    ("2018-05-02", "Luis", "add logger", {"write": {"lib/old_logger.js": LOGGER}}),
    ("2018-09-14", "Luis", "logger: add default meta", {"append": {"lib/old_logger.js": "// TODO: log levels from env\n"}}),
    ("2019-02-01", "Ana", "add util helpers", {"write": {"src/util.py": UTIL}}),
    ("2019-03-04", "Ana", "add ftp uploader for partner reports", {"write": {"legacy/ftp_uploader.py": FTP}}),
    ("2019-03-05", "Ana", "add ie8 jquery shim", {"write": {"src/jquery_shim.js": SHIM}}),
    ("2019-04-01", "Luis", "add math captcha", {"write": {"src/captcha_v1.py": CAPTCHA}}),
    ("2019-05-01", "Ana", "add logo", {"write": {"assets/logo.bin": b"\x00\x01\x02\x89PNG"}}),
    ("2019-06-10", "Ana", "add heroku deploy script", {"write": {"scripts/deploy_to_heroku.sh": HEROKU}}),
    ("2020-01-06", "Marta", "add 2020 roadmap", {"write": {"docs/roadmap_2020.md": ROADMAP}}),
    ("2020-06-01", "Luis", "rename logger", {"mv": [("lib/old_logger.js", "lib/logger.js")]}),
    ("2021-01-04", "Marta", "roadmap is a lie, deleting", {"rm": ["docs/roadmap_2020.md"]}),
    ("2021-02-01", "Marta", "add app", {"write": {"src/app.py": "from src.helpers import slugify\n\nprint(slugify('Hello World'))\n"}}),
    ("2021-03-10", "Ana", "rename util to helpers", {"mv": [("src/util.py", "src/helpers.py")]}),
    ("2022-08-30", "Luis", "drop IE8 support, finally", {"rm": ["src/jquery_shim.js"]}),
    ("2023-01-12", "Ana", "we left heroku", {"rm": ["scripts/deploy_to_heroku.sh"]}),
    ("2023-02-01", "Ana", "remove logo", {"rm": ["assets/logo.bin"]}),
    ("2023-11-09", "Marta", "remove ftp, partner moved to S3", {"rm": ["legacy/ftp_uploader.py"]}),
    ("2024-02-14", "Marta", "replace captcha with hCaptcha", {"rm": ["src/captcha_v1.py"]}),
    ("2024-09-30", "Ana", "logging moved to pino", {"rm": ["lib/logger.js"]}),
]
for i in range(1, 6):
    STEPS.append((f"2019-{7 + (i - 1) // 2:02d}-{10 + i}", "Ana", f"ftp: fix timeout ({i})", {"append": {"legacy/ftp_uploader.py": f"# patch {i}\n"}}))
for i in range(1, 4):
    STEPS.append((f"2020-{i:02d}-15", "Luis", f"shim: ie8 quirk {i}", {"append": {"src/jquery_shim.js": f"// ie fix {i}\n"}}))
for i in range(1, 3):
    STEPS.append((f"2021-{i:02d}-20", "Luis", "captcha: harder sums", {"append": {"src/captcha_v1.py": f"# tweak {i}\n"}}))


def build(dest: str) -> str:
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)

    def git(*args, date=None, author="Ana"):
        env = dict(os.environ, GIT_AUTHOR_NAME=author, GIT_COMMITTER_NAME=author,
                   GIT_AUTHOR_EMAIL=f"{author.lower()}@example.com", GIT_COMMITTER_EMAIL=f"{author.lower()}@example.com")
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00"
        subprocess.run(["git", "-C", dest, *args], check=True, env=env, capture_output=True)

    git("init", "-q", "-b", "main")
    for date, author, msg, ops in sorted(STEPS, key=lambda s: s[0]):
        for path, content in ops.get("write", {}).items():
            full = os.path.join(dest, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb" if isinstance(content, bytes) else "w", **({} if isinstance(content, bytes) else {"encoding": "utf-8"})) as f:
                f.write(content)
        for path, text in ops.get("append", {}).items():
            with open(os.path.join(dest, path), "a", encoding="utf-8") as f:
                f.write(text)
        for a, b in ops.get("mv", []):
            os.makedirs(os.path.dirname(os.path.join(dest, b)), exist_ok=True)
            os.replace(os.path.join(dest, a), os.path.join(dest, b))
        for path in ops.get("rm", []):
            os.remove(os.path.join(dest, path))
        git("add", "-A")
        git("commit", "-q", "-m", msg, date=date, author=author)
    return dest


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "demo-repo"
    print(f"demo repo ready in {build(target)}")
