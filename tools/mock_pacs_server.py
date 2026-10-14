"""PACS Server giả lập để kiểm thử C-STORE cục bộ trước khi kết nối PACS
thật của bệnh viện. Nhận file DICOM và lưu vào thư mục output."""
import argparse
import os
import sys

from pynetdicom import AE, AllStoragePresentationContexts, evt
from pynetdicom.sop_class import Verification


def handle_store(event, output_dir):
    ds = event.dataset
    ds.file_meta = event.file_meta
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{ds.SOPInstanceUID}.dcm"
    filepath = os.path.join(output_dir, filename)
    ds.save_as(filepath, write_like_original=False)
    print(
        f"[MOCK PACS] Nhận file: {filepath} "
        f"(PatientID={getattr(ds, 'PatientID', '?')}, PatientName={getattr(ds, 'PatientName', '?')}, "
        f"SOPClassUID={getattr(ds, 'SOPClassUID', '?')})"
    )
    return 0x0000


def handle_echo(event):
    print("[MOCK PACS] Nhận C-ECHO")
    return 0x0000


def main():
    parser = argparse.ArgumentParser(description="Mock PACS server để test C-STORE cục bộ")
    parser.add_argument('--port', type=int, default=11112)
    parser.add_argument('--ae-title', default='PACS_SERVER')
    parser.add_argument('--output-dir', default='./data/mock_pacs_received')
    args = parser.parse_args()

    handlers = [
        (evt.EVT_C_STORE, lambda event: handle_store(event, args.output_dir)),
        (evt.EVT_C_ECHO, handle_echo),
    ]

    ae = AE(ae_title=args.ae_title)
    ae.supported_contexts = AllStoragePresentationContexts
    ae.add_supported_context(Verification)

    print(f"[MOCK PACS] Đang lắng nghe trên port {args.port} với AE Title '{args.ae_title}'...")
    print(f"[MOCK PACS] File nhận được sẽ lưu vào: {args.output_dir}")
    try:
        ae.start_server(('0.0.0.0', args.port), evt_handlers=handlers)
    except OSError as exc:
        print(f"[MOCK PACS] Không thể khởi động server: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
