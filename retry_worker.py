"""Tiến trình nền quét hàng đợi retry và gửi lại các file DICOM thất bại
trước đó, áp dụng backoff tăng dần và giới hạn số lần thử tối đa."""
import json
import os
import shutil
import threading
from datetime import datetime, timedelta

from utils import dedupe_destination


class RetryWorker(threading.Thread):
    def __init__(self, config, sender, registry, logger):
        super().__init__(daemon=True)
        self.retry_folder = config['paths']['retry_queue_folder']
        self.processed_folder = config['paths']['processed_folder']
        self.failed_folder = config['paths']['failed_folder']
        self.scan_interval = config['retry']['scan_interval_sec']
        self.backoff_schedule = config['retry']['backoff_schedule_sec']
        self.max_attempts = config['retry']['max_attempts']
        self.sender = sender
        self.registry = registry
        self.logger = logger
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                self._scan_once()
            except Exception:
                self.logger.exception("Lỗi không mong đợi trong retry worker")
            self._stop_event.wait(self.scan_interval)

    def _scan_once(self):
        if not os.path.isdir(self.retry_folder):
            return
        for name in sorted(os.listdir(self.retry_folder)):
            if not name.endswith('.json'):
                continue
            self._process_item(os.path.join(self.retry_folder, name))

    def _process_item(self, sidecar_path):
        try:
            with open(sidecar_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.error(f"Không đọc được sidecar retry {sidecar_path}: {exc}")
            return

        next_attempt_at = datetime.fromisoformat(meta['next_attempt_at'])
        if datetime.now() < next_attempt_at:
            return

        dcm_path = meta['dicom_path']
        if not os.path.exists(dcm_path):
            self.logger.error(f"File DICOM trong hàng đợi retry bị thiếu, bỏ sidecar: {dcm_path}")
            os.remove(sidecar_path)
            return

        success, error = self.sender.send(dcm_path)
        if success:
            self.logger.info(f"Gửi lại thành công: {dcm_path}")
            self.registry.mark_processed(
                meta['file_hash'], meta['original_filename'], meta.get('sop_instance_uid')
            )
            self._archive_success(dcm_path, sidecar_path)
            return

        meta['attempts'] += 1
        meta['last_error'] = error
        if meta['attempts'] >= self.max_attempts:
            self.logger.error(
                f"Vượt quá số lần thử lại tối đa ({self.max_attempts}), chuyển sang failed: {dcm_path} ({error})"
            )
            self._move_to_failed(dcm_path, sidecar_path)
            return

        idx = min(meta['attempts'] - 1, len(self.backoff_schedule) - 1)
        delay = self.backoff_schedule[idx]
        meta['next_attempt_at'] = (datetime.now() + timedelta(seconds=delay)).isoformat()
        with open(sidecar_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        self.logger.warning(
            f"Gửi lại thất bại ({meta['attempts']}/{self.max_attempts}), thử lại sau {delay}s: {dcm_path} ({error})"
        )

    def _archive_success(self, dcm_path, sidecar_path):
        os.makedirs(self.processed_folder, exist_ok=True)
        dest = dedupe_destination(os.path.join(self.processed_folder, os.path.basename(dcm_path)))
        shutil.move(dcm_path, dest)
        os.remove(sidecar_path)

    def _move_to_failed(self, dcm_path, sidecar_path):
        os.makedirs(self.failed_folder, exist_ok=True)
        dest = dedupe_destination(os.path.join(self.failed_folder, os.path.basename(dcm_path)))
        try:
            shutil.move(dcm_path, dest)
        except OSError as exc:
            self.logger.error(f"Không di chuyển được file vào failed: {dcm_path} ({exc})")
        os.remove(sidecar_path)
