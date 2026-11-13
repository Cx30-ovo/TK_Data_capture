"""Optional supervised entry point; importing it never starts the application."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys


@contextmanager
def service_lock(path):
    """Hold an OS lock for the process lifetime; stale files are harmless."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description='Run the monitor as a single supervised process')
    parser.add_argument('--host', choices=('127.0.0.1', 'localhost'), default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8081)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    # Keep the existing deployment's risk cooldown cap; never clear state on restart.
    os.environ.setdefault('RISK_CONTROL_MAX_COOLDOWN_SECONDS', '10800')
    # Preserve the venv path itself (its Python may be a symlink on macOS).
    paths = [str(Path(sys.executable).parent)]
    paths.extend(str(path) for path in (Path('/opt/homebrew/bin'), Path('/usr/local/bin')) if path.is_dir())
    os.environ['PATH'] = os.pathsep.join(paths + [os.environ.get('PATH', '')])
    with service_lock(root / 'browser_data' / 'monitor-service.lock'):
        import uvicorn
        uvicorn.run('api.main:app', host=args.host, port=args.port, workers=1)


if __name__ == '__main__':
    main()
