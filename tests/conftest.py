import os
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'Client'))


@pytest.fixture(scope='session', autouse=True)
def test_signing_keypair(tmp_path_factory):
    """Cặp khóa RSA tạm cho test: không bao giờ dùng private key thật của nhà phát triển."""
    import license_manager

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    key_file = tmp_path_factory.mktemp('keys') / 'license_private.pem'
    key_file.write_bytes(private_pem)

    mp = pytest.MonkeyPatch()
    mp.setenv('TTSG_LICENSE_PRIVATE_KEY', str(key_file))
    mp.setattr(license_manager, 'DEFAULT_PUBLIC_KEY_PEM', public_pem)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def isolated_web_data_dir(tmp_path, monkeypatch):
    """Mỗi test có thư mục data/ riêng (license, .trial.json, mật khẩu ban đầu) — không đụng data/ thật."""
    import web_server
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    monkeypatch.setattr(web_server, '_data_dir', lambda: str(data_dir))
    return data_dir
