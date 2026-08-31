"""Điểm khởi chạy: theo dõi thư mục nguồn, đóng gói DICOM và đẩy lên PACS.

Chạy nền trên Windows: script này được thiết kế để chạy vô hạn ở foreground
(vòng lặp chính chỉ chờ tín hiệu dừng). Để chạy như một Windows Service thật
sự (tự khởi động cùng hệ thống, tự restart khi crash), khuyến nghị wrap bằng
NSSM (`nssm install DicomGateway <python.exe> <đường dẫn main.py>`) thay vì
viết thêm code phụ thuộc pywin32 — đơn giản và ít rủi ro hơn khi vận hành.
"""
import json
import os
import queue
import shutil
import signal
import sys
import threading
import time
from datetime import datetime, timedelta

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from dicom_builder import DicomBuildError, build_dicom_from_file
from dicom_sender import DicomSender
from retry_worker import RetryWorker
from storage_commitment_listener import StorageCommitmentListener
from utils import (
    ConfigError,
    ProcessedRegistry,
    compute_file_hash,
    dedupe_destination,
    extract_metadata_from_filename,
    get_watch_folders_list,
    load_config,
    merge_ris_metadata,
    setup_logging,
    wait_for_stable_file,
)
from web_server import start_web_server_thread
from worklist_client import WorklistClient

SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf'}

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Đảm bảo thư mục làm việc luôn là thư mục ứng dụng (tránh lỗi khi chạy Service từ System32)
try:
    os.chdir(APP_DIR)
except Exception:
    pass

CONFIG_PATH = os.environ.get('DICOM_GATEWAY_CONFIG', os.path.join(APP_DIR, 'config.yaml'))



class InboxHandler(FileSystemEventHandler):
    """Chỉ đẩy đường dẫn file kèm modality của thư mục vào hàng đợi."""

    def __init__(self, work_queue, folder_modality='OT'):
        self.work_queue = work_queue
        self.folder_modality = folder_modality

    def on_created(self, event):
        self._maybe_enqueue(event.src_path, event.is_directory)

    def on_moved(self, event):
        self._maybe_enqueue(event.dest_path, event.is_directory)

    def _maybe_enqueue(self, path, is_directory):
        if is_directory:
            return
        if os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS:
            self.work_queue.put((path, self.folder_modality))


class GatewayWorker(threading.Thread):
    def __init__(self, config, work_queue, registry, sender, worklist_client, logger):
        super().__init__(daemon=True)
        self.config = config
        self.work_queue = work_queue
        self.registry = registry
        self.sender = sender
        self.worklist_client = worklist_client
        self.logger = logger
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                item = self.work_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                if isinstance(item, tuple):
                    path, folder_modality = item
                else:
                    path, folder_modality = item, 'OT'
                self._process(path, folder_modality)
            except Exception:
                self.logger.exception(f"Lỗi không mong đợi khi xử lý file: {item}")
            finally:
                self.work_queue.task_done()

    def _process(self, path, folder_modality='OT'):
        watcher_cfg = self.config['watcher']
        if not wait_for_stable_file(
            path, watcher_cfg['stability_check_interval_sec'], watcher_cfg['stability_check_count']
        ):
            self.logger.error(f"File không ổn định hoặc biến mất trước khi xử lý: {path}")
            return

        try:
            file_hash = compute_file_hash(path)
        except OSError as exc:
            self.logger.error(f"Không đọc được file để tính hash, bỏ qua: {path} ({exc})")
            return

        if self.registry.is_processed(file_hash):
            self.logger.warning(f"File trùng với dữ liệu đã xử lý thành công trước đó, chuyển vào duplicates: {path}")
            self._move_original(path, self.config['paths']['duplicates_folder'])
            self.registry.record_study(os.path.basename(path), {'patient_id': 'DUPLICATE'}, 'DUPLICATE', file_hash=file_hash)
            return

        filename = os.path.basename(path)
        metadata, warnings = extract_metadata_from_filename(
            filename, self.config['filename_pattern'], self.config['metadata']['default_value']
        )
        metadata['modality'] = folder_modality
        for w in warnings:
            self.logger.warning(f"{filename}: {w}")

        if self.worklist_client is not None:
            ris_data = self.worklist_client.lookup_patient(metadata['patient_id'])
            metadata = merge_ris_metadata(metadata, ris_data)

        try:
            dicom_path, sop_uid = build_dicom_from_file(path, metadata, self.config)
        except DicomBuildError as exc:
            self.logger.error(f"Đóng gói DICOM thất bại cho {path}: {exc}")
            self._move_original(path, self.config['paths']['failed_folder'])
            self.registry.record_study(filename, metadata, 'FAILED', file_hash=file_hash, last_error=str(exc))
            return

        # File nguồn được backup ngay khi đóng gói thành công, độc lập với
        # kết quả gửi PACS (xem PRD mục 5) — tránh mất dữ liệu nếu PACS lỗi.
        self._move_original(path, self.config['paths']['processed_folder'])

        success, error = self.sender.send(dicom_path)
        if success:
            is_unknown_meta = (metadata.get('patient_id') == 'UNKNOWN') or (metadata.get('accession_number') == 'UNKNOWN')
            if is_unknown_meta:
                self.logger.warning(f"Gửi PACS thành công nhưng thiếu metadata (PatientID={metadata.get('patient_id')}, Accession={metadata.get('accession_number')}). File có thể nằm trong mục Unmatched trên PACS.")
            else:
                self.logger.info(f"Gửi PACS thành công: {filename} (SOPInstanceUID={sop_uid})")
            self.registry.mark_processed(file_hash, filename, sop_uid)
            self.registry.record_study(filename, metadata, 'SUCCESS', sop_instance_uid=sop_uid, file_hash=file_hash)
            self._archive_dicom(dicom_path)
        else:
            self.logger.warning(f"Gửi PACS thất bại cho {filename}: {error}. Chuyển vào hàng đợi retry.")
            self.registry.record_study(filename, metadata, 'RETRYING', sop_instance_uid=sop_uid, file_hash=file_hash, last_error=error)
            self._enqueue_retry(dicom_path, file_hash, filename, sop_uid, error)

    def _move_original(self, path, dest_folder):
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = dedupe_destination(os.path.join(dest_folder, os.path.basename(path)))
        shutil.move(path, dest_path)

    def _archive_dicom(self, dicom_path):
        dest_folder = self.config['paths']['processed_folder']
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = dedupe_destination(os.path.join(dest_folder, os.path.basename(dicom_path)))
        shutil.move(dicom_path, dest_path)

    def _enqueue_retry(self, dicom_path, file_hash, filename, sop_uid, error):
        retry_folder = self.config['paths']['retry_queue_folder']
        os.makedirs(retry_folder, exist_ok=True)
        dest_dcm_path = dedupe_destination(os.path.join(retry_folder, os.path.basename(dicom_path)))
        shutil.move(dicom_path, dest_dcm_path)

        backoff_schedule = self.config['retry']['backoff_schedule_sec']
        sidecar = {
            'dicom_path': dest_dcm_path,
            'file_hash': file_hash,
            'original_filename': filename,
            'sop_instance_uid': sop_uid,
            'attempts': 1,
            'max_attempts': self.config['retry']['max_attempts'],
            'last_error': error,
            'next_attempt_at': (datetime.now() + timedelta(seconds=backoff_schedule[0])).isoformat(),
        }
        json_path = os.path.splitext(dest_dcm_path)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sidecar, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Đã xếp file vào hàng đợi retry: {dest_dcm_path}")


def main():
    start_time = time.time()
    try:
        config = load_config(CONFIG_PATH)
    except ConfigError as exc:
        print(f"[FATAL] Lỗi cấu hình: {exc}", file=sys.stderr)
        sys.exit(1)

    logger = setup_logging(config)
    logger.info("Khởi động DICOM Gateway Service")

    watch_folders_list = get_watch_folders_list(config)
    folder_paths = [f['path'] for f in watch_folders_list]

    for folder in (
        config['paths']['processed_folder'],
        config['paths']['failed_folder'],
        config['paths']['duplicates_folder'],
        config['paths']['dicom_staging_folder'],
        config['paths']['retry_queue_folder'],
        *folder_paths,
    ):
        os.makedirs(folder, exist_ok=True)

    registry = ProcessedRegistry(config['paths']['registry_db'])
    sender = DicomSender(config['pacs'], logger)
    retry_sender = DicomSender(config['pacs'], logger)
    worklist_client = WorklistClient(config['ris'], logger) if config['ris']['enabled'] else None
    if worklist_client is not None:
        logger.info(f"Tra cứu metadata qua RIS Worklist: {config['ris']['ip']}:{config['ris']['port']}")

    # Khởi tạo License Manager
    from license_manager import LicenseManager
    lic_path = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), 'data', 'license.key')
    license_manager = LicenseManager(license_path=lic_path)
    lic_summary = license_manager.get_summary()
    logger.info(f"[Bản Quyền] Trạng thái: {lic_summary.get('status')} | Gói: {lic_summary.get('plan_name')} | Khách hàng: {lic_summary.get('customer_name')} (Hardware ID: {lic_summary.get('hardware_id')})")

    work_queue = queue.Queue()
    worker = GatewayWorker(config, work_queue, registry, sender, worklist_client, logger)
    worker.start()

    retry_worker = RetryWorker(config, retry_sender, registry, logger)
    retry_worker.start()

    storage_commitment_listener = StorageCommitmentListener(config, logger)
    storage_commitment_listener.start()

    observer = Observer()
    for item in watch_folders_list:
        handler = InboxHandler(work_queue, folder_modality=item.get('modality', 'OT'))
        observer.schedule(handler, item['path'], recursive=False)
    observer.start()
    logger.info(f"Đang theo dõi các thư mục: {watch_folders_list}")

    # Khởi chạy Web Control Panel
    start_web_server_thread(config, CONFIG_PATH, retry_worker, logger, start_time, registry, license_manager)

    stop_event = threading.Event()

    def _handle_signal(signum, frame):
        logger.info(f"Nhận tín hiệu dừng ({signum}), đang tắt service...")
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass

    try:
        while not stop_event.is_set():
            stop_event.wait(1)
    finally:
        observer.stop()
        observer.join()
        worker.stop()
        retry_worker.stop()
        storage_commitment_listener.stop()
        sender.close()
        retry_sender.close()
        registry.close()
        logger.info("DICOM Gateway Service đã dừng.")


if __name__ == '__main__':
    main()
