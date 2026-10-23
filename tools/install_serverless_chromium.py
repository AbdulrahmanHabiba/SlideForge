"""Bundle a pinned, integrity-checked serverless Chromium during the Vercel build."""
import base64
import hashlib
import io
import tarfile
from pathlib import Path
from urllib.request import urlopen

VERSION = '153.0.0'
URL = f'https://registry.npmjs.org/@sparticuz/chromium/-/chromium-{VERSION}.tgz'
INTEGRITY = 'jiGWqSvPMdu4+P9TilYqAR7yEGPEHINx+lCvE/NqNO/EHYzF/x1hUiI5T6ioVIt7dEy7n88byyT0vk+dnsgQwA=='
TARGET = Path(__file__).resolve().parents[1] / 'app' / 'browser_bin'
FILES = {'chromium.br', 'al2023.tar.br', 'fonts.tar.br', 'swiftshader.tar.br'}


def install():
    with urlopen(URL, timeout=90) as response:
        archive = response.read(120 * 1024 * 1024 + 1)
    if len(archive) > 120 * 1024 * 1024:
        raise RuntimeError('Browser package exceeds the build size limit')
    if base64.b64encode(hashlib.sha512(archive).digest()).decode() != INTEGRITY:
        raise RuntimeError('Browser package integrity check failed')
    TARGET.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as package:
        for filename in sorted(FILES):
            member = package.getmember('package/bin/' + filename)
            if not member.isfile():
                raise RuntimeError('Unexpected browser package entry')
            with package.extractfile(member) as source:
                (TARGET / filename).write_bytes(source.read())
        with package.extractfile('package/LICENSE') as source:
            (TARGET / 'LICENSE.Sparticuz').write_bytes(source.read())
    print(f'Bundled serverless Chromium {VERSION}: {sum(p.stat().st_size for p in TARGET.iterdir())} compressed bytes')


if __name__ == '__main__':
    install()
