"""Lắng nghe N-EVENT-REPORT xác nhận Storage Commitment gửi VỀ từ PACS Server,
sau khi Gateway đã gửi N-ACTION yêu cầu commit (xem dicom_sender.py).

PACS sẽ mở một association MỚI, riêng biệt, kết nối ngược lại Gateway theo
AE Title/IP/Port đã đăng ký sẵn phía PACS admin, để báo danh sách SOPInstanceUID
đã commit thành công (ReferencedSOPSequence) hoặc thất bại (FailedSOPSequence).

Cần mở Inbound Firewall cho đúng listen_port cấu hình, và phải được PACS admin
đăng ký AE Title + IP + port này làm địa chỉ callback Storage Commitment cho
AE Title `calling_ae_title` của Gateway — nếu không PACS sẽ không biết gửi
N-EVENT-REPORT về đâu.
"""
import threading

from pynetdicom import AE, evt
from pynetdicom.sop_class import StorageCommitmentPushModel


class StorageCommitmentListener:
    def __init__(self, config, logger):
        sc_cfg = (config.get('pacs', {}) or {}).get('storage_commitment', {}) or {}
        self.enabled = sc_cfg.get('enabled', False)
        self.listen_port = int(sc_cfg.get('listen_port', 105))
        self.ae_title = sc_cfg.get('listen_ae_title') or config['pacs']['calling_ae_title']
        self.logger = logger
        self._ae = None
        self._server = None
        self._thread = None

    def start(self):
        if not self.enabled:
            return
        self._ae = AE(ae_title=self.ae_title)
        self._ae.add_supported_context(StorageCommitmentPushModel)
        handlers = [(evt.EVT_N_EVENT_REPORT, self._on_n_event_report)]

        self._thread = threading.Thread(target=self._run, args=(handlers,), daemon=True)
        self._thread.start()
        if self.logger:
            self.logger.info(
                f"Storage Commitment Listener đang lắng nghe trên cổng {self.listen_port} "
                f"(AE Title: {self.ae_title}) — chờ N-EVENT-REPORT xác nhận từ PACS"
            )

    def _run(self, handlers):
        try:
            self._server = self._ae.start_server(
                ('0.0.0.0', self.listen_port), evt_handlers=handlers, block=True
            )
        except Exception:
            if self.logger:
                self.logger.exception(
                    f"Không khởi động được Storage Commitment Listener trên cổng {self.listen_port} "
                    f"(kiểm tra port có bị chiếm hoặc thiếu quyền không)"
                )

    def _on_n_event_report(self, event):
        ds = event.event_information
        transaction_uid = getattr(ds, 'TransactionUID', 'UNKNOWN')

        try:
            success_seq = list(getattr(ds, 'ReferencedSOPSequence', []) or [])
            failure_seq = list(getattr(ds, 'FailedSOPSequence', []) or [])

            for item in success_seq:
                sop_uid = getattr(item, 'ReferencedSOPInstanceUID', '?')
                if self.logger:
                    self.logger.info(
                        f"[StorageCommitment] PACS XÁC NHẬN ĐÃ LƯU (TransactionUID={transaction_uid}): "
                        f"SOPInstanceUID={sop_uid}"
                    )

            for item in failure_seq:
                sop_uid = getattr(item, 'ReferencedSOPInstanceUID', '?')
                reason = getattr(item, 'FailureReason', '?')
                if self.logger:
                    self.logger.error(
                        f"[StorageCommitment] PACS TỪ CHỐI COMMIT (TransactionUID={transaction_uid}): "
                        f"SOPInstanceUID={sop_uid} FailureReason=0x{reason:04X}"
                        if isinstance(reason, int) else
                        f"[StorageCommitment] PACS TỪ CHỐI COMMIT (TransactionUID={transaction_uid}): "
                        f"SOPInstanceUID={sop_uid} FailureReason={reason}"
                    )

            if not success_seq and not failure_seq and self.logger:
                self.logger.warning(
                    f"[StorageCommitment] Nhận N-EVENT-REPORT (TransactionUID={transaction_uid}) "
                    f"nhưng không có danh sách SOPInstanceUID nào kèm theo"
                )
        except Exception:
            if self.logger:
                self.logger.exception("Lỗi xử lý N-EVENT-REPORT Storage Commitment")

        return 0x0000

    def stop(self):
        if self._server:
            self._server.shutdown()
