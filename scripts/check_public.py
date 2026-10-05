"""Check public text for accidental personal paths, emails and private files."""
import re
import subprocess
from pathlib import Path

FORBIDDEN = re.compile(r'(?:/(?:Users|home)/[A-Za-z0-9_.-]+|[A-Z]:\\Users\\[A-Za-z0-9_.-]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})')
PRIVATE_NAMES = {'CHANGES.log', 'AGENTS.md', 'CLAUDE.md', 'HANDOFF.md', 'STATE.md', 'PLAN.md', 'NOTES.md'}


def violations(name, text):
    problems = []
    if Path(name).name in PRIVATE_NAMES or any(part in ('.claude', '.codex') for part in Path(name).parts):
        problems.append('private process file')
    for match in FORBIDDEN.finditer(text):
        value = match.group()
        if value.endswith(('@example.com', '@example.invalid', '@users.noreply.github.com')):
            continue
        problems.append('personal path or email')
    return problems


def main():
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    failed = []
    for name in filter(None, names):
        data = (root / name).read_bytes()
        if b'\0' in data:
            continue
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            continue
        problems = violations(name, text)
        if problems:
            failed.append((name, sorted(set(problems))))
    for name, problems in failed:
        print(name + ': ' + ', '.join(problems))
    if failed:
        raise SystemExit(1)
    print('Public text check passed.')


if __name__ == '__main__':
    main()
