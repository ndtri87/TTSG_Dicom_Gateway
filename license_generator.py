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

# Master RSA 2048-bit Private Key dùng để ký số bản quyền
DEFAULT_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDQhxe/lwICweBx
PBzsaP47ZwtHO+UxGHvUyc+Ac+ipMyeae3qx0SVb7gaXMpmAwKRpEgTdUUKNwSzG
srEXISZI0rK4wf0szg7dDcTcVD+33/tyv7b1+eHD2diVAtmNZ8mWzrkr6RaF6NXL
E5hQpsngc+rsRbiFDoRJjgoHKAH4LwwMAVl0J2MIokMfYCuPi24Pdsooq/RIwXE0
rFvoO2NTjclgyeBjldjDKq1YBlR6nLu8axN23M7s2CmDucRgphhaBMk6gqJ1mIIn
8Zx6q7k/YBTFoSPVnTj9sMjgb5eSmJ2B1Tca4eqtIhrDoeZgrh9ZMBDVwwQz4xha
kVcu+N6lAgMBAAECggEAIEPu8EWw2XVfQZYgEZJzWASrMZP6dBzKOFQbp9AHfXq9
U4FsrCvk4HMVkPqS1uG37swLdaU3q5Bq2bnXffEyp8z2O3FEt9SQZzLUtZTRoSVm
lkxExo2qGbBQ+0mMGP2oqw2EiF9SDVlID1qSVFRiYzj8bh+hm/DxliIEujO+DkUN
vxJPUmRJbVBK/oR5NWN9tQxrb0dGy3mICTwGPU1eErv7RJ6e+giNKo4G3DCkiujX
s8xpetAYXFLoAajv01k+T+v8txDT1dYbdLBUah9ctT6znjh04yHidphRt7sDGwji
/R/Hf5PdPEQzsiRnmetbVWO29Ia3NOeupb3wTrjxhwKBgQDyM6IVC6/lZamueDH3
6Val9HiE41RAaWAADoTkqutBh4OCsNrgMx2jjlLzgO+ABdMufZq+q6JWzQQEBaZR
kHn3WT1o1a7+RKXj0LcDVcq1LUrW5FCW9od4m55zAC68Xv62HYYZ9oHjE6089yoB
bZ/G2gbPOLRti5r9atMMepq19wKBgQDcaFg9NUQ8GOYeW7xW+I0jRyGm/Y1fTp2m
2gm9drSciYE4JLVjdmxwQKPWHAV7AsHWIzr8UOZ/vOK3n418Eiyq6fmJFoPEifbQ
giBHAnmqeOwIP5qeBfsqcGqcQjZB4rphoRsHmU1dkat/iWOXSWVilrBFqMd0OD7t
XuIztvL5QwKBgCkh77LXS0YQH+MLcqEBtb91Z0paOSK/Qph/3r3e8Rkt5H27f1B4
Hd56+0dzbDk3xAevOSqMh4NqSfZM51QOz0fclftJ3vA7xFiOR6Z/WW+vg3g/Shh5
QcSP2Tb6nvVKxMM0/GNIZAKmgtNJvo6DiZEB0go7PRkljmrfS3xhDgk9AoGBAL6h
dShDaOf9tRKuzz/9q7zGagHPrTWwfkRwsxnukJoPh/byMPx80Z9pGQs3oznYkaRP
RlYy9pmm2gRteGbGJWISCiSal48msJV45sfkCSz7d1JPCMECdVEod9z8m4byvbdx
KzqwSizSsB0XzE5uScUyhfVJ3HDVsP+HIGgQJSiXAoGBANsYznUfU4IkzRTKXWWk
NCIfjkdXQl7slSIx+HhsFpRiAOEaUvOCdShOnzbo7mYT9NWArYAJYb8MeJ+y/O2W
rstQFirGfGszEWdht5VvyrgwI7Y9dZZeFSVFhhI9XmNt1ZNtEiLDcNwUWmiCKjB/
zweEYscq85L9lkKEGmJNpVUA
-----END PRIVATE KEY-----"""


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
    priv_key_pem = private_key_pem or DEFAULT_PRIVATE_KEY_PEM
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
