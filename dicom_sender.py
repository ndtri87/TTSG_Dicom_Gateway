"""DICOM C-STORE client: kết nối tới PACS Server và đẩy file DICOM lên."""
import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE

from dicom_builder import ENCAPSULATED_PDF_SOP_CLASS, SECONDARY_CAPTURE_SOP_CLASS
from pynetdicom.sop_class import StorageCommitmentPushModel, Verification

# UID cố định theo chuẩn DICOM PS3.4 J.3 cho SOP Instance của dịch vụ
# Storage Commitment Push Model (không phải UID tự sinh).
STORAGE_COMMITMENT_SOP_INSTANCE = '1.2.840.10008.1.20.1.1'


class DicomSender:
    def __init__(self, pacs_config, logger):
        self.ip = pacs_config['ip']
        self.port = pacs_config['port']
        self.called_ae_title = pacs_config['called_ae_title']
        self.calling_ae_title = pacs_config['calling_ae_title']
        self.timeout = pacs_config.get('connect_timeout_sec', 10)
        self.logger = logger

        # Storage Commitment: một số PACS (VD môi trường tích hợp GE MUSE) chỉ
        # thực sự index/hiển thị study sau khi nhận được xác nhận Storage
        # Commitment (N-ACTION/N-EVENT-REPORT), không chỉ dựa vào C-STORE
        # thành công. Mặc định TẮT vì cần PACS đã đăng ký sẵn cổng callback
        # cho AE Title của Gateway — xem storage_commitment_listener.py.
        sc_cfg = pacs_config.get('storage_commitment', {}) or {}
        self.storage_commitment_enabled = sc_cfg.get('enabled', False)

        from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
        from pynetdicom.sop_class import (
            SecondaryCaptureImageStorage,
            UltrasoundImageStorage,
            UltrasoundMultiFrameImageStorage,
            ComputedRadiographyImageStorage,
            DigitalXRayImageStorageForPresentation,
            EncapsulatedPDFStorage,
            VLEndoscopicImageStorage,
            VLPhotographicImageStorage,
        )
        transfer_syntaxes = [ExplicitVRLittleEndian, ImplicitVRLittleEndian]

        self.ae = AE(ae_title=self.calling_ae_title)
        sop_classes = [
            SecondaryCaptureImageStorage,
            UltrasoundImageStorage,
            UltrasoundMultiFrameImageStorage,
            ComputedRadiographyImageStorage,
            DigitalXRayImageStorageForPresentation,
            EncapsulatedPDFStorage,
            VLEndoscopicImageStorage,
            VLPhotographicImageStorage,
        ]
        for sop in sop_classes:
            self.ae.add_requested_context(sop, transfer_syntaxes)
        if self.storage_commitment_enabled:
            self.ae.add_requested_context(StorageCommitmentPushModel)
        self.ae.network_timeout = self.timeout
        self.ae.acse_timeout = self.timeout
        self.ae.dimse_timeout = self.timeout

    def test_connection(self):
        """Thực hiện C-ECHO tới PACS Server để kiểm tra kết nối."""
        ae = AE(ae_title=self.calling_ae_title)
        ae.add_requested_context(Verification)
        ae.acse_timeout = self.timeout
        ae.network_timeout = self.timeout
        ae.dimse_timeout = self.timeout
        try:
            assoc = ae.associate(self.ip, self.port, ae_title=self.called_ae_title)
            if not assoc.is_established:
                return False, "Không thiết lập được association với PACS Server"
            status = assoc.send_c_echo()
            assoc.release()
            if status and status.Status == 0x0000:
                return True, None
            return False, f"PACS từ chối C-ECHO với status: 0x{status.Status:04X}"
        except Exception as exc:
            return False, f"Lỗi kết nối C-ECHO PACS: {exc}"

    def send(self, dataset_path):
        """Gửi một file .dcm lên PACS. Trả về (success: bool, error: str|None).
        Nếu storage_commitment.enabled=true, sau C-STORE thành công sẽ gửi thêm
        N-ACTION yêu cầu Storage Commitment trong CÙNG association — kết quả
        không ảnh hưởng tới success/error trả về (C-STORE vẫn là tiêu chí chính),
        chỉ log lại để đối chiếu khi PACS gửi N-EVENT-REPORT xác nhận sau đó."""
        try:
            ds = pydicom.dcmread(dataset_path)
        except Exception as exc:
            return False, f"Không đọc được file DICOM: {exc}"

        try:
            assoc = self.ae.associate(self.ip, self.port, ae_title=self.called_ae_title)
        except Exception as exc:
            return False, f"Không thể kết nối PACS ({self.ip}:{self.port}): {exc}"

        if not assoc.is_established:
            return False, f"Không thiết lập được association với PACS Server ({self.ip}:{self.port}, AE: {self.called_ae_title})"

        try:
            status = assoc.send_c_store(ds)
        except Exception as exc:
            assoc.abort()
            return False, f"Lỗi khi gửi C-STORE: {exc}"

        if status is None:
            if assoc.is_alive():
                assoc.release()
            return False, "Không nhận được phản hồi C-STORE từ PACS"

        if status.Status != 0x0000:
            if assoc.is_alive():
                assoc.release()
            return False, f"PACS trả về status lỗi: 0x{status.Status:04X}"

        if self.storage_commitment_enabled and assoc.is_alive():
            # C-STORE đã thành công thật sự tới đây — Storage Commitment chỉ là bước
            # bổ sung để xác nhận sau. TUYỆT ĐỐI không để lỗi/exception ở bước này
            # (VD PACS từ chối context, không hỗ trợ SOP Class) biến kết quả C-STORE
            # đã thành công thành báo THẤT BẠI.
            try:
                self._request_storage_commitment(assoc, ds.SOPClassUID, ds.SOPInstanceUID)
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "[StorageCommitment] Lỗi không mong đợi khi gửi N-ACTION — "
                        "bỏ qua, không ảnh hưởng kết quả C-STORE đã thành công"
                    )

        if assoc.is_alive():
            assoc.release()

        return True, None

    def _request_storage_commitment(self, assoc, sop_class_uid, sop_instance_uid):
        """Gửi N-ACTION yêu cầu PACS xác nhận đã lưu trữ vĩnh viễn. Chỉ log kết
        quả — xác nhận thật sự (committed/failed) đến KHÔNG ĐỒNG BỘ qua
        N-EVENT-REPORT, cần storage_commitment_listener.py đang chạy để nhận."""
        transaction_uid = generate_uid()
        action_ds = Dataset()
        action_ds.TransactionUID = transaction_uid
        ref_sop = Dataset()
        ref_sop.ReferencedSOPClassUID = sop_class_uid
        ref_sop.ReferencedSOPInstanceUID = sop_instance_uid
        action_ds.ReferencedSOPSequence = [ref_sop]

        try:
            status, _ = assoc.send_n_action(
                action_ds, 1, StorageCommitmentPushModel, STORAGE_COMMITMENT_SOP_INSTANCE
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning(f"[StorageCommitment] Lỗi gửi N-ACTION cho SOPInstanceUID={sop_instance_uid}: {exc}")
            return

        # status có thể là Dataset rỗng (không có .Status) nếu PACS từ chối
        # presentation context của Storage Commitment ngay từ lúc thiết lập
        # association — dùng getattr thay vì status.Status để không bao giờ
        # crash vì AttributeError ở bước bổ sung này.
        status_code = getattr(status, 'Status', None) if status is not None else None

        if status is None or status_code is None:
            if self.logger:
                self.logger.warning(
                    f"[StorageCommitment] Không nhận được phản hồi N-ACTION hợp lệ cho "
                    f"SOPInstanceUID={sop_instance_uid} — có thể PACS không hỗ trợ/từ chối "
                    f"SOP Class Storage Commitment Push Model trong association này"
                )
        elif status_code == 0x0000:
            if self.logger:
                self.logger.info(
                    f"[StorageCommitment] PACS CHẤP NHẬN yêu cầu N-ACTION (TransactionUID={transaction_uid}) cho "
                    f"SOPInstanceUID={sop_instance_uid}, chờ xác nhận committed qua N-EVENT-REPORT"
                )
        else:
            if self.logger:
                self.logger.warning(
                    f"[StorageCommitment] PACS TỪ CHỐI yêu cầu N-ACTION (status=0x{status_code:04X}) "
                    f"cho SOPInstanceUID={sop_instance_uid}"
                )

    def close(self):
        pass
