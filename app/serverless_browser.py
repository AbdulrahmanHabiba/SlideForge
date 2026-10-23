"""Load Chromium's official serverless binaries without an extra Node runtime."""
from __future__ import annotations

import os
import tarfile
import tempfile
from pathlib import Path


def launch_options() -> dict:
    assets = Path(__file__).parent / 'browser_bin'
    if not (assets / 'chromium.br').is_file():
        return {}  # Local/Docker deployments use Playwright's installed browser.
    import brotli

    root = Path(tempfile.gettempdir()) / 'slideforge-chromium-153'
    ready = root / '.ready'
    if not ready.exists():
        root.mkdir(parents=True, exist_ok=True)
        for filename in ['chromium.br', 'fonts.tar.br', 'swiftshader.tar.br', 'al2023.tar.br']:
            decoder = brotli.Decompressor()
            with (assets / filename).open('rb') as source, tempfile.TemporaryFile() as decoded:
                while chunk := source.read(1024 * 1024):
                    decoded.write(decoder.process(chunk))
                if not decoder.is_finished():
                    raise RuntimeError('Incomplete bundled browser asset')
                decoded.seek(0)
                if filename == 'chromium.br':
                    executable = root / 'chromium'
                    with executable.open('wb') as output:
                        while chunk := decoded.read(1024 * 1024):
                            output.write(chunk)
                    executable.chmod(0o700)
                else:
                    destination = root if filename.startswith('swiftshader') else root / filename.split('.')[0]
                    destination.mkdir(exist_ok=True)
                    with tarfile.open(fileobj=decoded) as archive:
                        archive.extractall(destination, filter='data')
        ready.write_text('153.0.0')
    env = dict(os.environ)
    env['FONTCONFIG_PATH'] = str(root / 'fonts')
    env['XDG_CACHE_HOME'] = str(root / 'cache')
    env['LD_LIBRARY_PATH'] = ':'.join([str(root / 'al2023' / 'lib'), str(root), env.get('LD_LIBRARY_PATH', '')])
    return {'executable_path': str(root / 'chromium'), 'env': env,
            'args': ['--single-process', '--no-zygote', '--disable-dev-shm-usage', '--use-gl=angle', '--use-angle=swiftshader']}
