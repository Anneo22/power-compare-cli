"""Run documented CLI examples on temporary synthetic ride files."""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    files = [base / 'trainer.csv', base / 'crank.csv']
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for path, bias in zip(files, (0, 5)):
        rows = ['timestamp,power,cadence']
        for i in range(180):
            watts = (140 if i < 90 else 200) + bias
            rows.append(f'{(start + timedelta(seconds=i)).isoformat()},{watts},90')
        path.write_text('\n'.join(rows) + '\n')
    command = [sys.executable, '-m', 'power_compare', 'compare', *map(str, files), '--window', '30:90', '--window', '120:180', '--out', str(base / 'comparison')]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    assert abs(report['comparisons'][0]['whole']['difference_w'] - 5) < 1e-9
    assert (base / 'comparison.html').is_file() and (base / 'comparison.json').is_file()
    protocol = subprocess.run([sys.executable, '-m', 'power_compare', 'protocol', '--issue', 'mismatch', '--controller', 'computer', '--meter', 'trainer', '--meter', 'crank'], check=True, capture_output=True, text=True)
    assert json.loads(protocol.stdout)
print('README CLI examples passed with known +5 W synthetic bias.')
