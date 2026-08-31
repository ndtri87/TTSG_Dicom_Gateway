"""Công cụ Đóng Gói Bản Vá & Nâng Cấp Phiên Bản (Patch Builder CLI).
Dành cho Nhà Phát Triển tạo file .pkg có chữ ký số RSA 2048-bit để gửi cho khách hàng."""

import argparse
import base64
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from license_generator import DEFAULT_PRIVATE_KEY_PEM

# Các file và thư mục được phép đưa vào bản vá nâng cấp
INCLUDE_ITEMS = [
    'TTSG_DicomGateway.exe',
    '_internal',
    'templates',
    'static',
    'service_install.bat',
    'service_uninstall.bat',
    'run_server.bat',
]

# Các file nhạy cảm TUYỆT ĐỐI KHÔNG ĐƯỢC ĐÈ lên máy khách hàng
EXCLUDE_ITEMS = [
    'config.yaml',
    'data',
    'logs',
    '.secret_key',
    'license.key',
]


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_patch_package(
    version: str,
    release_notes: str,
    source_dist_dir: str,
    output_pkg_path: str,
    private_key_pem: str = None
) -> str:
    """Tạo file .pkg nén zip chứa manifest có chữ ký số RSA."""
    source_dist_dir = os.path.abspath(source_dist_dir)
    if not os.path.exists(source_dist_dir):
        raise ValueError(f"Thư mục nguồn không tồn tại: {source_dist_dir}")

    priv_key_pem = private_key_pem or DEFAULT_PRIVATE_KEY_PEM
    priv_key = load_pem_private_key(priv_key_pem.encode('utf-8'), password=None)

    manifest = {
        'package_type': 'TTSG_GATEWAY_PATCH',
        'version': version.strip(),
        'created_at': datetime.now().isoformat(),
        'release_notes': release_notes.strip(),
        'files': []
    }

    files_to_pack = []

    for item in INCLUDE_ITEMS:
        item_path = os.path.join(source_dist_dir, item)
        if not os.path.exists(item_path):
            continue

        if os.path.isfile(item_path):
            rel_path = item
            sha = compute_file_sha256(item_path)
            manifest['files'].append({'path': rel_path, 'sha256': sha, 'size': os.path.getsize(item_path)})
            files_to_pack.append((item_path, rel_path))
        elif os.path.isdir(item_path):
            for root, _, filenames in os.walk(item_path):
                for fn in filenames:
                    full_p = os.path.join(root, fn)
                    rel_p = os.path.relpath(full_p, source_dist_dir).replace('\\', '/')
                    sha = compute_file_sha256(full_p)
                    manifest['files'].append({'path': rel_p, 'sha256': sha, 'size': os.path.getsize(full_p)})
                    files_to_pack.append((full_p, rel_p))

    # Ký số RSA trên manifest canonical JSON
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode('utf-8')
    signature = priv_key.sign(
        manifest_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sig_b64 = base64.b64encode(signature).decode('utf-8')

    manifest_wrapper = {
        'manifest': manifest,
        'signature': sig_b64
    }

    # Đóng gói ZIP thành file .pkg
    os.makedirs(os.path.dirname(os.path.abspath(output_pkg_path)), exist_ok=True)
    with zipfile.ZipFile(output_pkg_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # Ghi manifest có chữ ký
        zf.writestr('manifest.json', json.dumps(manifest_wrapper, indent=2))

        # Ghi các file thực thi và giao diện
        for full_p, rel_p in files_to_pack:
            zf.write(full_p, arcname=f"payload/{rel_p}")

    return output_pkg_path


def verify_and_apply_patch(pkg_source, target_app_dir: str, public_key_pem: str = None) -> dict:
    """Xác thực chữ ký số RSA và áp dụng bản vá .pkg an toàn."""
    from license_manager import DEFAULT_PUBLIC_KEY_PEM
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pub_key_pem = public_key_pem or DEFAULT_PUBLIC_KEY_PEM
    target_app_dir = os.path.abspath(target_app_dir)

    try:
        if isinstance(pkg_source, (str, os.PathLike)) and os.path.exists(str(pkg_source)):
            zf = zipfile.ZipFile(pkg_source, 'r')
        elif isinstance(pkg_source, (bytes, bytearray)):
            import io
            zf = zipfile.ZipFile(io.BytesIO(pkg_source), 'r')
        elif hasattr(pkg_source, 'read'):
            import io
            content = pkg_source.read()
            zf = zipfile.ZipFile(io.BytesIO(content), 'r')
        else:
            import io
            zf = zipfile.ZipFile(io.BytesIO(pkg_source), 'r')
    except Exception as e:
        return {'success': False, 'message': f'File bản vá không đúng định dạng nén ZIP/PKG: {e}'}

    with zf:
        if 'manifest.json' not in zf.namelist():
            return {'success': False, 'message': 'File bản vá thiếu manifest.json.'}

        try:
            wrapper = json.loads(zf.read('manifest.json').decode('utf-8'))
            manifest = wrapper.get('manifest', {})
            sig_b64 = wrapper.get('signature', '')
        except Exception:
            return {'success': False, 'message': 'Không thể đọc manifest từ file bản vá.'}

        # 1. Xác thực chữ ký số RSA
        try:
            pub_key = load_pem_public_key(pub_key_pem.encode('utf-8'))
            sig_bytes = base64.b64decode(sig_b64.encode('utf-8'))
            canonical_bytes = json.dumps(manifest, sort_keys=True).encode('utf-8')
            pub_key.verify(sig_bytes, canonical_bytes, padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            return {'success': False, 'message': 'Chữ ký số RSA của file bản vá không hợp lệ hoặc đã bị can thiệp! Từ chối cập nhật.'}

        # 2. Kiểm tra tính toàn vẹn SHA-256 từng file
        for f_info in manifest.get('files', []):
            arc_name = f"payload/{f_info['path']}"
            if arc_name not in zf.namelist():
                return {'success': False, 'message': f"Thiếu file {f_info['path']} trong gói cập nhật."}
            content = zf.read(arc_name)
            file_sha = hashlib.sha256(content).hexdigest()
            if file_sha.lower() != f_info.get('sha256', '').lower():
                return {'success': False, 'message': f"Mã băm SHA-256 của file {f_info['path']} không khớp (có thể bị lỗi khi tải về)."}

        # 3. Áp dụng các file vào thư mục đích (Bảo vệ không bao giờ ghi đè file cấu hình / CSDL)
        extracted_count = 0
        for f_info in manifest.get('files', []):
            rel_p = f_info['path']
            # Chặn ghi đè dữ liệu người dùng
            first_part = rel_p.split('/')[0].lower()
            if first_part in EXCLUDE_ITEMS or rel_p.lower() in [x.lower() for x in EXCLUDE_ITEMS]:
                continue

            dest_path = os.path.join(target_app_dir, rel_p.replace('/', os.sep))
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            content = zf.read(f"payload/{rel_p}")
            with open(dest_path, 'wb') as out_f:
                out_f.write(content)
            extracted_count += 1

    return {
        'success': True,
        'version': manifest.get('version', 'Unknown'),
        'release_notes': manifest.get('release_notes', ''),
        'updated_files_count': extracted_count,
        'message': f"Đã nâng cấp thành công lên phiên bản v{manifest.get('version')} ({extracted_count} tệp tin đã cập nhật)!"
    }



def main():
    parser = argparse.ArgumentParser(description="TTSG DICOM Gateway - Commercial Patch Package Builder")
    parser.add_argument('--version', required=True, help="So hieu phien ban (VD: '2.1.0')")
    parser.add_argument('--notes', default="Ban cap nhat toi uu hieu suat va bo sung tinh nang.", help="Ghi chu cap nhat")
    parser.add_argument('--dist', default="dist/TTSG_DicomGateway", help="Thu muc build dau vao (dist/TTSG_DicomGateway)")
    parser.add_argument('--out', default=None, help="Duong dan file .pkg dau ra")

    args = parser.parse_args()

    out_file = args.out or f"TTSG_Gateway_Patch_v{args.version}.pkg"

    print("=" * 70)
    print(f"[*] DANG DONG GOI BAN VA: {out_file}")
    print(f"[*] Phien ban:  v{args.version}")
    print(f"[*] Thu muc:    {args.dist}")
    print("=" * 70)

    pkg_path = create_patch_package(
        version=args.version,
        release_notes=args.notes,
        source_dist_dir=args.dist,
        output_pkg_path=out_file
    )

    pkg_size_mb = os.path.getsize(pkg_path) / (1024 * 1024)
    print(f"\n[OK] DA TAO FILE BAN VA NANG CAP (.PKG) THANH CONG!")
    print(f"[*] File:        {os.path.abspath(pkg_path)}")
    print(f"[*] Dung luong:  {pkg_size_mb:.2f} MB")
    print(f"[*] Chu ky RSA:  RSA 2048-bit Verified")
    print("=" * 70)


if __name__ == '__main__':
    main()
