"""Kiểm tra nhanh kết nối C-ECHO tới PACS Server theo cấu hình trong
config.yaml, dùng trước khi chạy service thật để chắc chắn IP/Port/AE Title
và tường lửa mạng đã đúng."""
import sys

from pynetdicom import AE
from pynetdicom.sop_class import Verification

from utils import ConfigError, load_config

CONFIG_PATH = 'config.yaml'


def main():
    try:
        config = load_config(CONFIG_PATH)
    except ConfigError as exc:
        print(f"[LOI] Cau hinh sai: {exc}")
        sys.exit(1)

    pacs = config['pacs']
    print(f"Dang ket noi toi PACS {pacs['ip']}:{pacs['port']} (Called AE Title: {pacs['called_ae_title']})...")

    ae = AE(ae_title=pacs['calling_ae_title'])
    ae.add_requested_context(Verification)
    timeout = pacs.get('connect_timeout_sec', 10)
    ae.acse_timeout = timeout
    ae.network_timeout = timeout

    assoc = ae.associate(pacs['ip'], pacs['port'], ae_title=pacs['called_ae_title'])
    if not assoc.is_established:
        print("[THAT BAI] Khong thiet lap duoc ket noi voi PACS.")
        print("Kiem tra lai: IP/Port trong config.yaml, tuong lua mang, PACS co dang chay khong.")
        sys.exit(1)

    status = assoc.send_c_echo()
    assoc.release()

    if status and status.Status == 0x0000:
        print("[THANH CONG] PACS phan hoi C-ECHO binh thuong. Ket noi mang va AE Title dung.")
    else:
        code = getattr(status, 'Status', None)
        print(f"[THAT BAI] PACS tu choi C-ECHO (status={code}).")
        print("Kiem tra lai: Calling AE Title da duoc dang ky voi quan tri PACS chua.")
        sys.exit(1)


if __name__ == '__main__':
    main()
