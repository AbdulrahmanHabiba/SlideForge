"""Load serverless Chromium using streamed decompression within /tmp limits."""
from __future__ import annotations
import io
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

class _BrotliReader(io.RawIOBase):
    def __init__(self, path):
        import brotli
        self.source = path.open('rb')
        self.decoder = brotli.Decompressor()
        self.buffer = bytearray()
        self.eof = False

    def readable(self):
        return True

    def read(self, size=-1):
        while not self.eof and (size < 0 or len(self.buffer) < size):
            chunk = self.source.read(64 * 1024)
            if chunk:
                self.buffer.extend(self.decoder.process(chunk))
            else:
                self.eof = True
                if not self.decoder.is_finished():
                    raise RuntimeError('Incomplete bundled browser asset')
        count = len(self.buffer) if size < 0 else min(size, len(self.buffer))
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def close(self):
        self.source.close()
        super().close()

def launch_options() -> dict:
    assets = Path(__file__).parent / 'browser_bin'
    if not (assets / 'chromium.br').is_file():
        return {}
    root = Path(tempfile.gettempdir()) / 'slideforge-chromium-153'
    ready = root / '.ready'
    if not ready.exists():
        root.mkdir(parents=True, exist_ok=True)
        for filename in ['chromium.br', 'fonts.tar.br', 'swiftshader.tar.br', 'al2023.tar.br']:
            with _BrotliReader(assets / filename) as decoded:
                if filename == 'chromium.br':
                    executable = root / 'chromium'
                    with executable.open('wb') as output:
                        shutil.copyfileobj(decoded, output, length=1024 * 1024)
                    executable.chmod(0o700)
                else:
                    destination = root if filename.startswith('swiftshader') else root / filename.split('.')[0]
                    destination.mkdir(exist_ok=True)
                    with tarfile.open(fileobj=decoded, mode='r|') as archive:
                        archive.extractall(destination, filter='data')
        ready.write_text('153.0.0')
    env = dict(os.environ)
    env['FONTCONFIG_PATH'] = str(root / 'fonts')
    env['XDG_CACHE_HOME'] = str(root / 'cache')
    env['LD_LIBRARY_PATH'] = ':'.join([str(root / 'al2023' / 'lib'), str(root), env.get('LD_LIBRARY_PATH', '')])
    return {'executable_path': str(root / 'chromium'), 'env': env,
            'args': ['--single-process', '--no-zygote', '--disable-dev-shm-usage', '--disable-features=IsolateOrigins,site-per-process', '--in-process-gpu', '--use-gl=angle', '--use-angle=swiftshader']}
