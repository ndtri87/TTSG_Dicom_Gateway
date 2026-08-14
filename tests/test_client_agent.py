import os
import tempfile
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client_agent import is_file_stable, move_file, send_file_to_server  # noqa: E402


def test_is_file_stable():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"hello world")
        tmp_path = tmp.name

    try:
        assert is_file_stable(tmp_path, checks=1, delay=0.1) is True
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_move_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_file = os.path.join(tmp_dir, "test.png")
        with open(src_file, "wb") as f:
            f.write(b"data")

        dest_dir = os.path.join(tmp_dir, "sent")
        dest_path = move_file(src_file, dest_dir)

        assert not os.path.exists(src_file)
        assert os.path.exists(dest_path)
        assert os.path.basename(dest_path) == "test.png"


def test_send_file_to_server_success():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(b"fake image data")
        tmp_path = tmp.name

    logger = MagicMock()

    try:
        with patch("requests.post") as mock_post:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {"success": True, "message": "Gửi PACS thành công!"}
            mock_post.return_value = mock_res

            success, msg = send_file_to_server("http://127.0.0.1:5000", tmp_path, logger)

            assert success is True
            assert "thành công" in msg
            mock_post.assert_called_once()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
