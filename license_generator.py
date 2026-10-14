"""Công cụ phát hành Bản Quyền (License Generator CLI) dành riêng cho Nhà Phát Triển.
Sử dụng RSA 2048-bit Private Key để ký số và tạo file license.key cho khách hàng."""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# Private key KHÔNG BAO GIỜ được nhúng trong mã nguồn hay đóng gói vào bản build giao khách.
# Đọc từ biến môi trường TTSG_LICENSE_PRIVATE_KEY (đường dẫn file PEM) hoặc keys/license_private.pem
# (thư mục keys/ đã bị .gitignore). Hãy sao lưu file này ở nơi an toàn — mất nó là không ký được license mới.
PRIVATE_KEY_ENV = 'TTSG_LICENSE_PRIVATE_KEY'
DEFAULT_PRIVATE_KEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys', 'license_private.pem')


def load_private_key_pem() -> str:
    """Đọc RSA private key PEM dùng để ký license / bản vá."""
    key_path = os.environ.get(PRIVATE_KEY_ENV) or DEFAULT_PRIVATE_KEY_PATH
    if not os.path.isfile(key_path):
        raise FileNotFoundError(
            f"Không tìm thấy private key ký bản quyền tại '{key_path}'. "
            f"Đặt file vào keys/license_private.pem hoặc khai báo biến môi trường {PRIVATE_KEY_ENV}."
        )
    with open(key_path, 'r', encoding='utf-8') as f:
        return f.read()


def generate_license_data(
    customer_name: str,
    hardware_id: str,
    expiration_date: str = 'PERMANENT',
    allowed_modalities: list = None,
    max_stations: int = 50,
    plan_name: str = 'Bản Quyền Doanh Nghiệp (Enterprise Edition)',
    private_key_pem: str = None
) -> str:
    """Tạo dữ liệu bản quyền có chữ ký số RSA 2048-bit."""
    priv_key_pem = private_key_pem or load_private_key_pem()
    priv_key = load_pem_private_key(priv_key_pem.encode('utf-8'), password=None)

    data_payload = {
        'customer_name': customer_name.strip(),
        'hardware_id': hardware_id.strip().upper(),
        'expiration_date': expiration_date.strip(),
        'allowed_modalities': allowed_modalities or ['*'],
        'max_stations': int(max_stations),
        'plan_name': plan_name.strip(),
        'issued_at': datetime.now().isoformat(),
    }

    # Chuỗi JSON chuẩn hóa để ký
    canonical_bytes = json.dumps(data_payload, sort_keys=True).encode('utf-8')

    # Ký số RSA PKCS#1 v1.5 + SHA256
    signature = priv_key.sign(
        canonical_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    full_package = {
        'version': '1.0',
        'data': data_payload,
        'signature': base64.b64encode(signature).decode('utf-8')
    }

    # Mã hóa toàn bộ gói sang Base64
    final_json = json.dumps(full_package, indent=2)
    return base64.b64encode(final_json.encode('utf-8')).decode('utf-8')


def main():
    parser = argparse.ArgumentParser(description="TTSG DICOM Gateway - Commercial License Generator")
    parser.add_argument('--customer', required=True, help="Tên khách hàng / Bệnh viện (VD: 'BV Tâm Trí Sài Gòn')")
    parser.add_argument('--hwid', required=True, help="Mã Hardware ID của máy trạm (VD: 'TTSG-XXXX-XXXX-XXXX-XXXX' hoặc '*' cho mọi máy)")
    parser.add_argument('--exp', default='PERMANENT', help="Ngày hết hạn YYYY-MM-DD (hoặc 'PERMANENT')")
    parser.add_argument('--modalities', default='*', help="Danh sách modality cách nhau bởi dấu phẩy (VD: 'US,ES,ECG' hoặc '*')")
    parser.add_argument('--stations', type=int, default=50, help="Số lượng phòng khám tối đa cho phép (mặc định: 50)")
    parser.add_argument('--plan', default='Bản Quyền Doanh Nghiệp (Enterprise Edition)', help="Tên gói bản quyền")
    parser.add_argument('--out', default='data/license.key', help="Đường dẫn lưu file license.key")

    args = parser.parse_args()

    mods = [m.strip().upper() for m in args.modalities.split(',') if m.strip()]
    if '*' in mods or 'ALL' in mods:
        mods = ['*']

    lic_str = generate_license_data(
        customer_name=args.customer,
        hardware_id=args.hwid,
        expiration_date=args.exp,
        allowed_modalities=mods,
        max_stations=args.stations,
        plan_name=args.plan
    )

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(lic_str)

    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    print("=" * 65)
    print("[THANH CONG] DA TAO LICENSE BAN QUYEN THUONG MAI THANH CONG!")
    print(f"- Khach hang:   {args.customer}")
    print(f"- Hardware ID:  {args.hwid}")
    print(f"- Han dung:     {args.exp}")
    print(f"- Modalities:   {', '.join(mods)}")
    print(f"- Max Stations: {args.stations}")
    print(f"- Luu tai file: {out_path}")
    print("=" * 65)


if __name__ == '__main__':
    main()
