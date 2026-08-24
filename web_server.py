"""Web Control Panel REST API Server cho DICOM Gateway Service.

Cung cấp giao diện Web và REST API quản lý cấu hình, kiểm tra kết nối C-ECHO PACS/RIS,
xem thống kê, nhật ký log thời gian thực và theo dõi hoạt động của hệ thống.
"""
import os
import threading
from flask import Flask, jsonify, render_template, request

from dicom_builder import DicomBuildError, build_dicom_from_file
from dicom_sender import DicomSender
from utils import (
    ConfigError,
    dedupe_destination,
    extract_metadata_from_filename,
    get_system_stats,
    get_watch_folders_list,
    load_config,
    save_config,
    test_ris_connection,
)
from worklist_client import WorklistClient

app = Flask(__name__, template_folder='templates', static_folder='static')

# Global references set by main.py
app_config = None
config_path = None
retry_worker_ref = None
logger_ref = None
start_time = None
registry_ref = None


def init_web_app(config, cfg_path, retry_worker=None, logger=None, app_start_time=None, registry=None):
    global app_config, config_path, retry_worker_ref, logger_ref, start_time, registry_ref
    app_config = config
    config_path = cfg_path
    retry_worker_ref = retry_worker
    logger_ref = logger
    start_time = app_start_time
    registry_ref = registry


@app.after_request
def add_no_cache_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def api_status():
    import time
    uptime = int(time.time() - start_time) if start_time else 0
    stats = get_system_stats(app_config) if app_config else {}
    folders = get_watch_folders_list(app_config) if app_config else []
    return jsonify({
        'status': 'running',
        'uptime_seconds': uptime,
        'stats': stats,
        'watch_folders': folders,
        'pacs_target': f"{app_config['pacs']['ip']}:{app_config['pacs']['port']} ({app_config['pacs']['called_ae_title']})",
        'ris_enabled': app_config['ris'].get('enabled', False)
    })


MODALITY_CATALOG = [
    {
        'code': 'US',
        'name_vi': 'Siêu âm',
        'name_en': 'Ultrasound',
        'icon': '🩺',
        'sop_class': '1.2.840.10008.5.1.4.1.1.6.1',
        'sop_name': 'Ultrasound Image Storage',
        'color': '#06b6d4',
        'default_service': 'Siêu âm ổ bụng tổng quát',
    },
    {
        'code': 'ES',
        'name_vi': 'Nội soi',
        'name_en': 'Endoscopy',
        'icon': '🔬',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#10b981',
        'default_service': 'Nội soi dạ dày / đại tràng',
    },
    {
        'code': 'ECG',
        'name_vi': 'Điện tâm đồ',
        'name_en': 'Electrocardiogram',
        'icon': '💓',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#f43f5e',
        'default_service': 'Điện tâm đồ thường 12 chuyển đạo',
    },
    {
        'code': 'EEG',
        'name_vi': 'Điện não đồ',
        'name_en': 'Electroencephalogram',
        'icon': '🧠',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#d946ef',
        'default_service': 'Điện não đồ vi tính (EEG)',
    },
    {
        'code': 'EMG',
        'name_vi': 'Điện cơ',
        'name_en': 'Electromyogram',
        'icon': '⚡',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#0ea5e9',
        'default_service': 'Điện cơ & Dẫn truyền thần kinh',
    },
    {
        'code': 'BD',
        'name_vi': 'Đo loãng xương',
        'name_en': 'Bone Density / DEXA',
        'icon': '🦴',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#f59e0b',
        'default_service': 'Đo mật độ xương DEXA',
    },
    {
        'code': 'MR',
        'name_vi': 'Cộng hưởng từ',
        'name_en': 'Magnetic Resonance (MRI)',
        'icon': '🧲',
        'sop_class': '1.2.840.10008.5.1.4.1.1.4',
        'sop_name': 'MR Image Storage',
        'color': '#6366f1',
        'default_service': 'Chụp cộng hưởng từ MRI',
    },
    {
        'code': 'CT',
        'name_vi': 'Cắt lớp vi tính',
        'name_en': 'Computed Tomography (CT)',
        'icon': '🌀',
        'sop_class': '1.2.840.10008.5.1.4.1.1.2',
        'sop_name': 'CT Image Storage',
        'color': '#ec4899',
        'default_service': 'Chụp cắt lớp vi tính CT Scanner',
    },
    {
        'code': 'DR',
        'name_vi': 'X-quang số trực tiếp',
        'name_en': 'Digital Radiography (DR)',
        'icon': '📷',
        'sop_class': '1.2.840.10008.5.1.4.1.1.1.1',
        'sop_name': 'Digital X-Ray Image Storage',
        'color': '#0284c7',
        'default_service': 'X-quang số trực tiếp DR',
    },
    {
        'code': 'CR',
        'name_vi': 'X-quang kỹ thuật số',
        'name_en': 'Computed Radiography (CR)',
        'icon': '📸',
        'sop_class': '1.2.840.10008.5.1.4.1.1.1',
        'sop_name': 'CR Image Storage',
        'color': '#3b82f6',
        'default_service': 'X-quang ngực thẳng CR',
    },
    {
        'code': 'PFT',
        'name_vi': 'Đo chức năng hô hấp',
        'name_en': 'Pulmonary Function Test',
        'icon': '💨',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#8b5cf6',
        'default_service': 'Đo dung tích phổi / Phế dung kế',
    },
    {
        'code': 'DOC',
        'name_vi': 'Báo cáo kết quả PDF',
        'name_en': 'Encapsulated PDF Document',
        'icon': '📄',
        'sop_class': '1.2.840.10008.5.1.4.1.1.104.1',
        'sop_name': 'Encapsulated PDF Storage',
        'color': '#ea580c',
        'default_service': 'Phiếu kết quả chẩn đoán PDF',
    },
    {
        'code': 'OT',
        'name_vi': 'Cận lâm sàng khác',
        'name_en': 'Other Modality',
        'icon': '⚙️',
        'sop_class': '1.2.840.10008.5.1.4.1.1.7',
        'sop_name': 'Secondary Capture Image Storage',
        'color': '#64748b',
        'default_service': 'Dịch vụ cận lâm sàng khác',
    },
]


@app.route('/api/modalities/summary', methods=['GET'])
def api_modalities_summary():
    date_param = request.args.get('date', '').strip()
    raw_stats = registry_ref.get_modality_stats(date_param) if registry_ref else {}
    watch_folders = get_watch_folders_list(app_config) if app_config else []

    folder_map = {}
    for f in watch_folders:
        mod = (f.get('modality') or 'OT').strip().upper()
        if mod not in folder_map:
            folder_map[mod] = []
        folder_map[mod].append(f.get('path'))

    modalities_list = []
    total_today = 0
    success_today = 0
    retrying_today = 0
    failed_today = 0
    active_modalities = 0

    for item in MODALITY_CATALOG:
        code = item['code']
        st = raw_stats.get(code, {
            'today': {'total': 0, 'success': 0, 'retrying': 0, 'failed': 0, 'duplicate': 0},
            'all_time': {'total': 0, 'success': 0, 'retrying': 0, 'failed': 0, 'duplicate': 0},
            'last_activity': None,
            'last_patient': None,
        })

        t_today = st['today']['total']
        s_today = st['today']['success']
        r_today = st['today']['retrying']
        f_today = st['today']['failed']

        total_today += t_today
        success_today += s_today
        retrying_today += r_today
        failed_today += f_today

        if t_today > 0 or st['all_time']['total'] > 0 or code in folder_map:
            active_modalities += 1

        status = 'IDLE'
        if r_today > 0:
            status = 'WARNING'
        elif f_today > 0:
            status = 'DANGER'
        elif t_today > 0:
            status = 'ACTIVE'

        mod_entry = dict(item)
        mod_entry['status'] = status
        mod_entry['stats_today'] = st['today']
        mod_entry['stats_all_time'] = st['all_time']
        mod_entry['last_activity'] = st['last_activity']
        mod_entry['last_patient'] = st['last_patient']
        mod_entry['watch_folders'] = folder_map.get(code, [])
        mod_entry['is_configured'] = code in folder_map
        modalities_list.append(mod_entry)

    success_rate = round((success_today / total_today * 100), 1) if total_today > 0 else 100.0

    return jsonify({
        'success': True,
        'summary': {
            'total_studies_today': total_today,
            'success_studies_today': success_today,
            'retrying_studies_today': retrying_today,
            'failed_studies_today': failed_today,
            'success_rate_percent': success_rate,
            'active_modalities_count': active_modalities,
            'total_modalities_count': len(MODALITY_CATALOG),
        },
        'modalities': modalities_list,
    })


@app.route('/api/config', methods=['GET'])
def api_get_config():
    return jsonify(app_config)


@app.route('/api/config', methods=['POST'])
def api_update_config():
    global app_config
    new_data = request.json
    if not isinstance(new_data, dict):
        return jsonify({'success': False, 'message': 'Dữ liệu không hợp lệ'}), 400

    try:
        save_config(new_data, config_path)
        app_config = new_data
        if logger_ref:
            logger_ref.info("Đã cập nhật cấu hình config.yaml từ Web Dashboard")
        return jsonify({'success': True, 'message': 'Cập nhật cấu hình thành công!'})
    except ConfigError as exc:
        return jsonify({'success': False, 'message': f"Lỗi cấu hình: {exc}"}), 400
    except Exception as exc:
        return jsonify({'success': False, 'message': f"Lỗi không xác định: {exc}"}), 500


@app.route('/api/test-pacs', methods=['POST'])
def api_test_pacs():
    pacs_cfg = request.json if request.is_json and request.json else app_config['pacs']
    sender = DicomSender(pacs_cfg, logger_ref)
    success, error = sender.test_connection()
    if success:
        return jsonify({'success': True, 'message': f"Kết nối PACS C-ECHO THÀNH CÔNG đến {pacs_cfg['ip']}:{pacs_cfg['port']} ({pacs_cfg['called_ae_title']})"})
    return jsonify({'success': False, 'message': f"Kết nối PACS THẤT BẠI: {error}"})


@app.route('/api/test-ris', methods=['POST'])
def api_test_ris():
    ris_cfg = request.json if request.is_json and request.json else app_config['ris']
    success, message = test_ris_connection(ris_cfg)
    return jsonify({'success': success, 'message': message})


@app.route('/api/worklist', methods=['GET'])
def api_worklist():
    if not app_config or not app_config.get('ris', {}).get('enabled', False):
        return jsonify({'success': False, 'message': 'Tính năng RIS Worklist đang bị tắt trong config.yaml', 'items': []})

    date_str = request.args.get('date', '').strip().replace('-', '')
    patient_id = request.args.get('patient_id', '').strip()
    patient_name = request.args.get('patient_name', '').strip()
    modality = request.args.get('modality', '').strip()

    try:
        client = WorklistClient(app_config['ris'], logger_ref)
        items = client.query_worklist(date_str=date_str, patient_id=patient_id, patient_name=patient_name, modality=modality)
        return jsonify({'success': True, 'items': items})
    except Exception as exc:
        if logger_ref:
            logger_ref.error(f"Lỗi truy vấn Worklist API: {exc}")
        return jsonify({'success': False, 'message': f"Lỗi truy vấn RIS: {exc}", 'items': []})


@app.route('/api/studies', methods=['GET'])
def api_studies():
    if not registry_ref:
        return jsonify({'success': False, 'message': 'Registry chưa khởi tạo', 'studies': []})

    status_filter = request.args.get('status', 'ALL').strip()
    search = request.args.get('search', '').strip()

    try:
        studies = registry_ref.get_studies(status_filter=status_filter, search_keyword=search)
        return jsonify({'success': True, 'studies': studies})
    except Exception as exc:
        return jsonify({'success': False, 'message': f"Lỗi lấy lịch sử ca chụp: {exc}", 'studies': []})


@app.route('/api/upload-manual', methods=['POST'])
def api_upload_manual():
    if not app_config:
        return jsonify({'success': False, 'message': 'Hệ thống chưa tải cấu hình'}), 500

    uploaded_files = request.files.getlist('files') or request.files.getlist('file')
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        return jsonify({'success': False, 'message': 'Chưa chọn file nào để tải lên'}), 400

    form_patient_id = request.form.get('patient_id', '').strip()
    form_patient_name = request.form.get('patient_name', '').strip()
    form_study_date = request.form.get('study_date', '').strip()
    form_accession_number = request.form.get('accession_number', '').strip()
    form_modality = request.form.get('modality', '').strip()
    form_study_description = request.form.get('study_description', '').strip()
    form_study_instance_uid = request.form.get('study_instance_uid', '').strip()
    main_report_filename = request.form.get('main_report_filename', '').strip()

    staging_dir = app_config.get('paths', {}).get('dicom_staging_folder', './data/dicom_staging')
    processed_dir = app_config.get('paths', {}).get('processed_folder', './data/processed')
    failed_dir = app_config.get('paths', {}).get('failed_folder', './data/failed')

    os.makedirs(staging_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(failed_dir, exist_ok=True)

    sender = DicomSender(app_config['pacs'], logger_ref)
    results = []
    success_count = 0
    attachment_counter = 2

    # Sinh StudyInstanceUID và SeriesInstanceUID chung cho toàn bộ batch file trong 1 lần đẩy
    from pydicom.uid import generate_uid
    batch_study_uid = form_study_instance_uid or generate_uid()
    batch_attachment_series_uid = generate_uid()

    # Tìm xem file nào là main report
    has_explicit_main = any(f.filename == main_report_filename for f in uploaded_files if f and f.filename)

    for idx, file_obj in enumerate(uploaded_files):
        if not file_obj or file_obj.filename == '':
            continue

        filename = file_obj.filename
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.png', '.jpg', '.jpeg', '.pdf'):
            results.append({'file': filename, 'success': False, 'message': f'Định dạng {ext} không hỗ trợ'})
            continue

        temp_input_path = os.path.join(staging_dir, f"upload_{filename}")
        file_obj.save(temp_input_path)

        try:
            metadata, warnings = extract_metadata_from_filename(
                filename, app_config['filename_pattern'], app_config['metadata']['default_value']
            )

            if form_patient_id:
                metadata['patient_id'] = form_patient_id
            if form_patient_name:
                metadata['patient_name'] = form_patient_name
            if form_study_date:
                metadata['study_date'] = form_study_date.replace('-', '')
            if form_accession_number:
                metadata['accession_number'] = form_accession_number
            if form_study_description:
                metadata['study_description'] = form_study_description
            if form_modality:
                metadata['modality'] = form_modality
            elif ext == '.pdf':
                metadata['modality'] = 'DOC'
            else:
                metadata['modality'] = 'OT'

            metadata['study_instance_uid'] = batch_study_uid

            # Xử lý phân định Phiếu Kết Quả chính vs Tài liệu đính kèm
            is_main = (filename == main_report_filename) or (not has_explicit_main and idx == 0)
            if is_main:
                metadata['instance_number'] = 1
                metadata['series_number'] = 1
                metadata['series_instance_uid'] = generate_uid()
                metadata['document_title'] = 'PHIẾU KẾT QUẢ CẬN LÂM SÀNG'
                metadata['series_description'] = 'Diagnostic Report'
            else:
                metadata['instance_number'] = attachment_counter
                attachment_counter += 1
                metadata['series_number'] = 2
                metadata['series_instance_uid'] = batch_attachment_series_uid
                metadata['document_title'] = f'Tài liệu đính kèm ({filename})'
                metadata['series_description'] = 'Attachment'

            if app_config.get('ris', {}).get('enabled', False) and metadata.get('patient_id'):
                try:
                    wl_client = WorklistClient(app_config['ris'], logger_ref)
                    ris_data = wl_client.lookup_patient(metadata['patient_id'])
                    if ris_data:
                        if not form_patient_name and ris_data.get('patient_name'):
                            metadata['patient_name'] = ris_data['patient_name']
                        if ris_data.get('patient_birth_date'):
                            metadata['patient_birth_date'] = ris_data['patient_birth_date']
                        if ris_data.get('patient_sex'):
                            metadata['patient_sex'] = ris_data['patient_sex']
                        if not form_accession_number and ris_data.get('accession_number'):
                            metadata['accession_number'] = ris_data['accession_number']
                except Exception as ris_err:
                    if logger_ref:
                        logger_ref.warning(f"Lỗi tra cứu RIS cho {filename}: {ris_err}")

            dicom_path, sop_uid = build_dicom_from_file(temp_input_path, metadata, app_config)
            dicom_filename = os.path.basename(dicom_path)
            success, send_err = sender.send(dicom_path)

            if success:
                is_unknown_meta = (metadata.get('patient_id') == 'UNKNOWN') or (metadata.get('accession_number') == 'UNKNOWN')
                if logger_ref:
                    if is_unknown_meta:
                        logger_ref.warning(f"[Web Upload] Đã đóng gói DICOM {dicom_filename} & gửi PACS thành công nhưng thiếu metadata (PatientID={metadata.get('patient_id')}, Accession={metadata.get('accession_number')}). File có thể nằm trong mục Unmatched trên PACS.")
                    else:
                        logger_ref.info(f"[Web Upload] Đã đóng gói DICOM {dicom_filename} & gửi PACS thành công cho {filename} (SOPInstanceUID={sop_uid})")
                target_orig = dedupe_destination(os.path.join(processed_dir, filename))
                os.replace(temp_input_path, target_orig)
                if registry_ref:
                    registry_ref.record_study(filename, metadata, 'SUCCESS', sop_instance_uid=sop_uid)

                success_msg = f'Đã đóng gói thành file DICOM [{dicom_filename}] & gửi PACS THÀNH CÔNG! (SOPInstanceUID: {sop_uid})'
                if is_unknown_meta:
                    success_msg += ' ⚠️ Cảnh báo: Thiếu Mã BN/Số CĐ, file có thể xếp vào Unmatched Studies trên PACS.'

                results.append({
                    'file': filename,
                    'dicom_file': dicom_filename,
                    'success': True,
                    'sop_instance_uid': sop_uid,
                    'message': success_msg
                })
                success_count += 1
            else:
                if logger_ref:
                    logger_ref.error(f"[Web Upload] Gửi PACS thất bại cho {filename}: {send_err}")
                target_failed = dedupe_destination(os.path.join(failed_dir, filename))
                os.replace(temp_input_path, target_failed)
                if registry_ref:
                    registry_ref.record_study(filename, metadata, 'FAILED', last_error=send_err)
                results.append({
                    'file': filename,
                    'success': False,
                    'message': f'Lỗi gửi PACS: {send_err}'
                })

        except DicomBuildError as build_err:
            target_failed = dedupe_destination(os.path.join(failed_dir, filename))
            if os.path.exists(temp_input_path):
                os.replace(temp_input_path, target_failed)
            if registry_ref:
                registry_ref.record_study(filename, metadata if 'metadata' in locals() else {}, 'FAILED', last_error=str(build_err))
            results.append({'file': filename, 'success': False, 'message': f'Lỗi đóng gói DICOM: {build_err}'})
        except Exception as exc:
            if os.path.exists(temp_input_path) and os.path.isfile(temp_input_path):
                try:
                    os.remove(temp_input_path)
                except Exception:
                    pass
            results.append({'file': filename, 'success': False, 'message': f'Lỗi xử lý: {exc}'})

    overall_success = (success_count == len(results)) and len(results) > 0
    return jsonify({
        'success': overall_success,
        'message': f"Đã gửi thành công {success_count}/{len(results)} file lên PACS.",
        'results': results
    })


@app.route('/api/logs', methods=['GET'])
def api_get_logs():
    log_folder = app_config.get('logging', {}).get('log_folder', './logs')
    log_path = os.path.join(log_folder, 'gateway.log')
    if not os.path.exists(log_path):
        return jsonify({'logs': ['Chưa có file log.']})

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            lines = lines[-200:]  # 200 dòng mới nhất
            return jsonify({'logs': [line.strip() for line in lines]})
    except Exception as exc:
        return jsonify({'logs': [f"Lỗi đọc file log: {exc}"]})


@app.route('/api/retry-now', methods=['POST'])
def api_retry_now():
    if retry_worker_ref and hasattr(retry_worker_ref, 'trigger_immediate_scan'):
        retry_worker_ref.trigger_immediate_scan()
        return jsonify({'success': True, 'message': 'Đã gửi yêu cầu quét thử lại hàng đợi lập tức!'})
    return jsonify({'success': False, 'message': 'Tiến trình Retry Worker chưa sẵn sàng'}), 400


def run_web_server(config, cfg_path, retry_worker=None, logger=None, app_start_time=None, registry=None):
    init_web_app(config, cfg_path, retry_worker, logger, app_start_time, registry)
    web_cfg = config.get('web_ui', {})
    host = web_cfg.get('host', '0.0.0.0')
    port = int(web_cfg.get('port', 5000))
    if logger:
        logger.info(f"Khởi chạy Web Control Panel tại: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")

    # Chạy server ẩn log Werkzeug thừa
    import logging as py_logging
    log = py_logging.getLogger('werkzeug')
    log.setLevel(py_logging.ERROR)

    app.run(host=host, port=port, debug=False, use_reloader=False)


def start_web_server_thread(config, cfg_path, retry_worker=None, logger=None, app_start_time=None, registry=None):
    if not config.get('web_ui', {}).get('enabled', True):
        if logger:
            logger.info("Web UI đang bị tắt trong config.yaml (web_ui.enabled: false)")
        return None

    t = threading.Thread(
        target=run_web_server,
        args=(config, cfg_path, retry_worker, logger, app_start_time, registry),
        daemon=True
    )
    t.start()
    return t
