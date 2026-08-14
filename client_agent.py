"""Client Agent - Chạy tại các máy trạm phòng khám kết nối thiết bị y tế (VLAN 10.4.140.x).
Tự động theo dõi thư mục local, nạp ảnh/PDF và đẩy về Gateway Server trung tâm.
Hỗ trợ chế độ Offline Buffer: Giữ hàng đợi tại máy local và tự gửi bù khi Server online.
"""
import os
import shutil
import sys
import time
import logging
import requests
import yaml

CONFIG_FILE = 'client_config.yaml'


def setup_logging():
    logger = logging.getLogger('ClientAgent')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


def load_client_config(cfg_path):
    if not os.path.exists(cfg_path):
        default_cfg = {
            'server_url': 'http://192.168.0.3:5000',
            'watch_folder': './export',
            'sent_folder': './export/sent',
            'failed_folder': './export/failed',
            'poll_interval_sec': 3,
            'max_retries': 10,
            'retry_delay_sec': 5,
        }
        with open(cfg_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(default_cfg, f, default_flow_style=False)
        return default_cfg
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def is_file_stable(file_path, checks=2, delay=1.0):
    try:
        last_size = -1
        for _ in range(checks):
            if not os.path.exists(file_path):
                return False
            size = os.path.getsize(file_path)
            if size == last_size and size > 0:
                return True
            last_size = size
            time.sleep(delay)
        return last_size > 0
    except Exception:
        return False


def send_file_to_server(server_url, file_path, logger):
    filename = os.path.basename(file_path)
    url = f"{server_url.rstrip('/')}/api/upload-manual"
    
    try:
        with open(file_path, 'rb') as f:
            files = {'files': (filename, f, 'application/octet-stream')}
            res = requests.post(url, files=files, timeout=15)
            
        if res.status_code == 200:
            data = res.json()
            if data.get('success'):
                logger.info(f"✅ Gửi thành công tới Gateway Server: {filename}")
                return True, data.get('message', 'Thành công')
            else:
                msg = data.get('message', 'Server từ chối xử lý')
                logger.warning(f"⚠️ Server từ chối file {filename}: {msg}")
                return False, msg
        else:
            msg = f"HTTP Error {res.status_code}"
            logger.warning(f"⚠️ Gửi thất bại file {filename}: {msg}")
            return False, msg
    except requests.exceptions.RequestException as exc:
        logger.warning(f"🔌 Không kết nối được Gateway Server ({url}): {exc}")
        return False, str(exc)


def move_file(src_path, dest_folder):
    os.makedirs(dest_folder, exist_ok=True)
    filename = os.path.basename(src_path)
    dest_path = os.path.join(dest_folder, filename)
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(filename)
        counter = 1
        while True:
            candidate = os.path.join(dest_folder, f"{base}_{counter}{ext}")
            if not os.path.exists(candidate):
                dest_path = candidate
                break
            counter += 1
    shutil.move(src_path, dest_path)
    return dest_path


def main():
    logger = setup_logging()
    logger.info("=== BẮT ĐẦU CLIENT AGENT TRẠM PHÒNG KHÁM ===")

    config = load_client_config(CONFIG_FILE)
    server_url = config.get('server_url', 'http://localhost:5000')
    watch_folder = config.get('watch_folder', './export')
    sent_folder = config.get('sent_folder', './export/sent')
    failed_folder = config.get('failed_folder', './export/failed')
    poll_interval = config.get('poll_interval_sec', 3)

    for folder in (watch_folder, sent_folder, failed_folder):
        os.makedirs(folder, exist_ok=True)

    logger.info(f"📍 Gateway Server: {server_url}")
    logger.info(f"📂 Thư mục theo dõi local: {os.path.abspath(watch_folder)}")
    logger.info(f"📁 Thư mục đã gửi: {os.path.abspath(sent_folder)}")
    logger.info("⏳ Đang lắng nghe file ảnh/PDF mới... Press Ctrl+C to exit.")

    retry_counts = {}

    while True:
        try:
            entries = os.listdir(watch_folder)
            for item in entries:
                file_path = os.path.join(watch_folder, item)
                if not os.path.isfile(file_path):
                    continue

                ext = os.path.splitext(item)[1].lower()
                if ext not in ('.png', '.jpg', '.jpeg', '.pdf'):
                    continue

                if not is_file_stable(file_path):
                    continue

                logger.info(f"🔍 Phát hiện file mới từ thiết bị: {item}")
                success, msg = send_file_to_server(server_url, file_path, logger)

                if success:
                    move_file(file_path, sent_folder)
                    if item in retry_counts:
                        del retry_counts[item]
                else:
                    count = retry_counts.get(item, 0) + 1
                    retry_counts[item] = count
                    max_retries = config.get('max_retries', 10)
                    if count >= max_retries:
                        logger.error(f"❌ File {item} thử lại quá {max_retries} lần không thành công. Chuyển vào failed!")
                        move_file(file_path, failed_folder)
                        del retry_counts[item]
                    else:
                        logger.info(f"🟠 Giữ file {item} trong hàng đợi offline local (Lần thử {count}/{max_retries})")

            time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Đã dừng Client Agent.")
            break
        except Exception as exc:
            logger.error(f"Lỗi không xác định trong Client Agent: {exc}")
            time.sleep(poll_interval)


if __name__ == '__main__':
    main()
