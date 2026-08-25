"""Web Control Panel REST API Server cho DICOM Gateway Service.

Cung cấp giao diện Web và REST API quản lý cấu hình, kiểm tra kết nối C-ECHO PACS/RIS,
xem thống kê, nhật ký log thời gian thực và theo dõi hoạt động của hệ thống.
"""
import os
import threading
from datetime import timedelta
from functools import wraps
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from dicom_builder import DicomBuildError, build_dicom_from_file
from dicom_sender import DicomSender
from utils import (
    ConfigError,
    authenticate_user,
    dedupe_destination,
    delete_station,
    delete_user,
    extract_metadata_from_filename,
    get_auth_config,
    get_station_by_id,
    get_stations_config,
    get_system_stats,
    get_user_by_username,
    get_watch_folders_list,
    list_stations,
    list_users,
    load_config,
    save_config,
    test_ris_connection,
    update_user_password,
    upsert_station,
    upsert_user,
)
from worklist_client import WorklistClient

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'TTSG_DICOM_GATEWAY_SUPER_SECRET_KEY_2026'

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

    auth_cfg = get_auth_config(config)
    app.secret_key = auth_cfg.get('secret_key', 'TTSG_DICOM_GATEWAY_SUPER_SECRET_KEY_2026')
    lifetime_days = int(auth_cfg.get('session_lifetime_days', 30))
    app.permanent_session_lifetime = timedelta(days=lifetime_days)


def get_current_user():
    """Lấy thông tin người dùng hiện tại từ session (hỗ trợ User login và Station login)."""
    if not app_config:
        return None
    auth_cfg = get_auth_config(app_config)
    if not auth_cfg.get('enabled', True):
        return {
            'username': 'trind',
            'full_name': 'Nguyễn Đình Trí (No Auth)',
            'department': 'Công nghệ thông tin',
            'role': 'ADMIN',
            'allowed_modalities': ['*'],
            'is_station': False,
        }

    # 1. Kiểm tra nếu đăng nhập theo Nơi thực hiện / Trạm máy (Station Login)
    station_id = session.get('station_id')
    if station_id:
        st = get_station_by_id(app_config, station_id)
        if st:
            tech_name = session.get('technician_name') or ''
            return {
                'is_station': True,
                'station_id': st['id'],
                'station_name': st['name'],
                'username': f"station_{st['id'].lower()}",
                'full_name': f"{st['name']}" + (f" ({tech_name})" if tech_name else ""),
                'technician_name': tech_name,
                'department': st.get('department', ''),
                'role': 'TECHNICIAN',
                'allowed_modalities': st.get('allowed_modalities', []),
                'default_modality': st.get('default_modality', ''),
                'icon': st.get('icon', '🏢'),
            }

    # 2. Kiểm tra nếu đăng nhập theo Tài khoản User / Super Admin (User Login)
    username = session.get('username')
    if not username:
        return None
    user = get_user_by_username(app_config, username)
    if not user:
        return None
    return {
        'is_station': False,
        'username': user.get('username'),
        'full_name': user.get('full_name', user.get('username')),
        'department': user.get('department', ''),
        'role': user.get('role', 'TECHNICIAN'),
        'allowed_modalities': user.get('allowed_modalities', []),
    }


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not app_config:
            return f(*args, **kwargs)
        auth_cfg = get_auth_config(app_config)
        if not auth_cfg.get('enabled', True):
            return f(*args, **kwargs)

        user = get_current_user()
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Vui lòng đăng nhập để tiếp tục', 'code': 'UNAUTHORIZED'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not app_config:
            return f(*args, **kwargs)
        auth_cfg = get_auth_config(app_config)
        if not auth_cfg.get('enabled', True):
            return f(*args, **kwargs)

        user = get_current_user()
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Vui lòng đăng nhập', 'code': 'UNAUTHORIZED'}), 401
            return redirect(url_for('login_page'))
        if user.get('role') != 'ADMIN':
            return jsonify({'success': False, 'message': 'Chức năng chỉ dành riêng cho Super Admin', 'code': 'FORBIDDEN'}), 403
        return f(*args, **kwargs)
    return decorated_function


@app.after_request
def add_no_cache_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


@app.route('/login')
def login_page():
    if get_current_user():
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/api/stations', methods=['GET'])
def api_list_stations():
    """Lấy danh sách các trạm thực hiện (công khai cho màn hình đăng nhập)."""
    if not app_config:
        return jsonify({'success': False, 'stations': []})
    return jsonify({'success': True, 'stations': list_stations(app_config)})


@app.route('/api/auth/station-login', methods=['POST'])
def api_auth_station_login():
    """Đăng nhập trực tiếp theo Nơi thực hiện / Trạm máy mà không cần mật khẩu."""
    if not app_config:
        return jsonify({'success': False, 'message': 'Hệ thống chưa sẵn sàng'}), 500
    data = request.get_json(silent=True) or {}
    station_id = (data.get('station_id') or '').strip().upper()
    technician_name = (data.get('technician_name') or '').strip()
    remember = bool(data.get('remember', True))

    station = get_station_by_id(app_config, station_id)
    if not station:
        return jsonify({'success': False, 'message': f'Nơi thực hiện [{station_id}] không tồn tại hoặc đã bị xóa'}), 404

    session.clear()
    session.permanent = remember
    session['station_id'] = station['id']
    session['technician_name'] = technician_name
    session['role'] = 'TECHNICIAN'

    if logger_ref:
        tech_str = f" do KTV [{technician_name}] trực" if technician_name else ""
        logger_ref.info(f"Đăng nhập thành công vào Nơi thực hiện [{station['name']}]{tech_str} (Modality: {station['allowed_modalities']})")

    user_info = get_current_user()
    return jsonify({
        'success': True,
        'message': f"Chào mừng bạn đến với {station['name']}!",
        'user': user_info
    })


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    if not app_config:
        return jsonify({'success': False, 'message': 'Hệ thống chưa sẵn sàng'}), 500
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    remember = bool(data.get('remember', True))

    user = authenticate_user(app_config, username, password)
    if not user:
        return jsonify({'success': False, 'message': 'Tên đăng nhập hoặc mật khẩu không chính xác'}), 401

    session.clear()
    session.permanent = remember
    session['username'] = user['username']
    session['role'] = user['role']

    if logger_ref:
        logger_ref.info(f"Người dùng [{user['username']}] ({user['full_name']}) đã đăng nhập thành công")

    return jsonify({
        'success': True,
        'message': f"Đăng nhập thành công! Xin chào {user['full_name']}",
        'user': user
    })


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    uname = session.get('username') or session.get('station_id') or 'Unknown'
    session.clear()
    if logger_ref:
        logger_ref.info(f"Phiên làm việc [{uname}] đã đăng xuất")
    return jsonify({'success': True, 'message': 'Đã đăng xuất thành công'})


@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    auth_cfg = get_auth_config(app_config) if app_config else {}
    if not auth_cfg.get('enabled', True):
        return jsonify({
            'success': True,
            'auth_enabled': False,
            'user': {
                'username': 'trind',
                'full_name': 'Nguyễn Đình Trí',
                'department': 'Công nghệ thông tin',
                'role': 'ADMIN',
                'allowed_modalities': ['*'],
                'is_station': False,
            }
        })
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Chưa đăng nhập', 'code': 'UNAUTHORIZED'}), 401
    return jsonify({'success': True, 'auth_enabled': True, 'user': user})


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_auth_change_password():
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401
    if user.get('is_station'):
        return jsonify({'success': False, 'message': 'Tài khoản Trạm thực hiện không sử dụng mật khẩu'}), 400

    data = request.get_json(silent=True) or {}
    old_pass = data.get('old_password', '')
    new_pass = data.get('new_password', '')

    if not new_pass or len(new_pass) < 4:
        return jsonify({'success': False, 'message': 'Mật khẩu mới phải có ít nhất 4 ký tự'}), 400

    check_u = authenticate_user(app_config, user['username'], old_pass)
    if not check_u:
        return jsonify({'success': False, 'message': 'Mật khẩu cũ không chính xác'}), 400

    ok = update_user_password(app_config, config_path, user['username'], new_pass)
    if ok:
        if logger_ref:
            logger_ref.info(f"Người dùng [{user['username']}] đã đổi mật khẩu thành công")
        return jsonify({'success': True, 'message': 'Đổi mật khẩu thành công!'})
    return jsonify({'success': False, 'message': 'Lỗi cập nhật mật khẩu'}), 500


@app.route('/api/admin/stations', methods=['GET'])
@admin_required
def api_admin_list_stations():
    """Lấy danh sách trạm thực hiện đầy đủ cho Super Admin."""
    return jsonify({'success': True, 'stations': list_stations(app_config)})


@app.route('/api/admin/stations', methods=['POST'])
@admin_required
def api_admin_upsert_station():
    """Thêm mới hoặc cập nhật thông tin Trạm thực hiện & Modality được phép."""
    data = request.get_json(silent=True) or {}
    try:
        st = upsert_station(app_config, config_path, data)
        if logger_ref:
            logger_ref.info(f"Super Admin đã cập nhật thông tin Nơi thực hiện [{st['name']}] (ID: {st['id']}, Modality: {st['allowed_modalities']})")
        return jsonify({
            'success': True,
            'message': f"Đã lưu thông tin nơi thực hiện [{st['name']}]",
            'station': st
        })
    except ValueError as ve:
        return jsonify({'success': False, 'message': str(ve)}), 400
    except Exception as exc:
        return jsonify({'success': False, 'message': f"Lỗi lưu nơi thực hiện: {exc}"}), 500


@app.route('/api/admin/stations/<station_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_station(station_id):
    """Xóa Nơi thực hiện khỏi hệ thống."""
    try:
        ok = delete_station(app_config, config_path, station_id)
        if ok:
            if logger_ref:
                logger_ref.info(f"Super Admin đã xóa Nơi thực hiện [{station_id}]")
            return jsonify({'success': True, 'message': f"Đã xóa nơi thực hiện [{station_id}] thành công"})
        return jsonify({'success': False, 'message': 'Không tìm thấy nơi thực hiện để xóa'}), 404
    except ValueError as ve:
        return jsonify({'success': False, 'message': str(ve)}), 400
    except Exception as exc:
        return jsonify({'success': False, 'message': f"Lỗi xóa nơi thực hiện: {exc}"}), 500


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_list_users():
    return jsonify({'success': True, 'users': list_users(app_config)})


@app.route('/api/admin/users', methods=['POST'])
@admin_required
def api_admin_upsert_user():
    data = request.get_json(silent=True) or {}
    try:
        u = upsert_user(app_config, config_path, data)
        return jsonify({
            'success': True,
            'message': f"Đã cập nhật thông tin tài khoản [{u['username']}]",
            'user': {
                'username': u.get('username'),
                'full_name': u.get('full_name'),
                'department': u.get('department', ''),
                'role': u.get('role'),
                'allowed_modalities': u.get('allowed_modalities', []),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/admin/users/<username>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(username):
    try:
        ok = delete_user(app_config, config_path, username)
        if ok:
            return jsonify({'success': True, 'message': f"Đã xóa tài khoản [{username}]"})
        return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


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
@login_required
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
@admin_required
def api_get_config():
    return jsonify(app_config)


@app.route('/api/config', methods=['POST'])
@admin_required
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
@admin_required
def api_test_pacs():
    pacs_cfg = request.json if request.is_json and request.json else app_config['pacs']
    sender = DicomSender(pacs_cfg, logger_ref)
    success, error = sender.test_connection()
    if success:
        return jsonify({'success': True, 'message': f"Kết nối PACS C-ECHO THÀNH CÔNG đến {pacs_cfg['ip']}:{pacs_cfg['port']} ({pacs_cfg['called_ae_title']})"})
    return jsonify({'success': False, 'message': f"Kết nối PACS THẤT BẠI: {error}"})


@app.route('/api/test-ris', methods=['POST'])
@admin_required
def api_test_ris():
    ris_cfg = request.json if request.is_json and request.json else app_config['ris']
    success, message = test_ris_connection(ris_cfg)
    return jsonify({'success': success, 'message': message})


@app.route('/api/worklist', methods=['GET'])
@login_required
def api_worklist():
    if not app_config or not app_config.get('ris', {}).get('enabled', False):
        return jsonify({'success': False, 'message': 'Tính năng RIS Worklist đang bị tắt trong config.yaml', 'items': [], 'counts': {'pending': 0, 'completed': 0, 'total': 0}})

    user = get_current_user()
    user_role = user.get('role', 'TECHNICIAN') if user else 'ADMIN'
    allowed_modalities = user.get('allowed_modalities', ['*']) if user else ['*']

    date_str = request.args.get('date', '').strip().replace('-', '')
    patient_id = request.args.get('patient_id', '').strip()
    patient_name = request.args.get('patient_name', '').strip()
    modality = request.args.get('modality', '').strip().upper()
    status_filter = request.args.get('status', 'PENDING').strip().upper()
    if status_filter not in ('PENDING', 'COMPLETED', 'ALL'):
        status_filter = 'PENDING'

    # Scope restriction for technician
    if user_role != 'ADMIN' and '*' not in allowed_modalities:
        if modality and modality not in allowed_modalities:
            modality = allowed_modalities[0]
        elif not modality and len(allowed_modalities) == 1:
            modality = allowed_modalities[0]

    try:
        client = WorklistClient(app_config['ris'], logger_ref)
        items = client.query_worklist(date_str=date_str, patient_id=patient_id, patient_name=patient_name, modality=modality)

        if user_role != 'ADMIN' and '*' not in allowed_modalities:
            items = [it for it in items if (it.get('modality') or '').upper() in allowed_modalities]

        # Đối soát với CSDL SQLite để kiểm tra ca nào đã đẩy PACS thành công (status = 'SUCCESS')
        completed_map = {}
        if registry_ref and items:
            acc_list = [str(it.get('accession_number') or '').strip() for it in items if it.get('accession_number')]
            completed_map = registry_ref.get_completed_accessions(accessions=acc_list, date_str=date_str)

        pending_count = 0
        completed_count = 0
        enriched_items = []

        for it in items:
            acc = str(it.get('accession_number') or '').strip()
            completed_info = completed_map.get(acc) if acc else None
            is_completed = completed_info is not None

            it['is_completed'] = is_completed
            if is_completed:
                it['completed_at'] = completed_info.get('created_at')
                it['completed_sop_uid'] = completed_info.get('sop_instance_uid')
                completed_count += 1
            else:
                pending_count += 1

            enriched_items.append(it)

        # Lọc danh sách trả về theo status_filter
        if status_filter == 'PENDING':
            filtered_items = [it for it in enriched_items if not it.get('is_completed')]
        elif status_filter == 'COMPLETED':
            filtered_items = [it for it in enriched_items if it.get('is_completed')]
        else:
            filtered_items = enriched_items

        return jsonify({
            'success': True,
            'items': filtered_items,
            'counts': {
                'pending': pending_count,
                'completed': completed_count,
                'total': len(enriched_items)
            },
            'status_filter': status_filter
        })
    except Exception as exc:
        if logger_ref:
            logger_ref.error(f"Lỗi truy vấn Worklist API: {exc}")
        return jsonify({'success': False, 'message': f"Lỗi truy vấn RIS: {exc}", 'items': [], 'counts': {'pending': 0, 'completed': 0, 'total': 0}})


@app.route('/api/studies', methods=['GET'])
@login_required
def api_studies():
    if not registry_ref:
        return jsonify({'success': False, 'message': 'Registry chưa khởi tạo', 'studies': []})

    user = get_current_user()
    user_role = user.get('role', 'TECHNICIAN') if user else 'ADMIN'
    allowed_modalities = user.get('allowed_modalities', ['*']) if user else ['*']

    status_filter = request.args.get('status', 'ALL').strip()
    search = request.args.get('search', '').strip()

    try:
        studies = registry_ref.get_studies(status_filter=status_filter, search_keyword=search)
        if user_role != 'ADMIN' and '*' not in allowed_modalities:
            studies = [s for s in studies if (s.get('modality') or '').upper() in allowed_modalities]
        return jsonify({'success': True, 'studies': studies})
    except Exception as exc:
        return jsonify({'success': False, 'message': f"Lỗi lấy lịch sử ca chụp: {exc}", 'studies': []})


@app.route('/api/upload-manual', methods=['POST'])
@login_required
def api_upload_manual():
    if not app_config:
        return jsonify({'success': False, 'message': 'Hệ thống chưa tải cấu hình'}), 500

    user = get_current_user()
    user_role = user.get('role', 'TECHNICIAN') if user else 'ADMIN'
    allowed_modalities = user.get('allowed_modalities', ['*']) if user else ['*']

    uploaded_files = request.files.getlist('files') or request.files.getlist('file')
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        return jsonify({'success': False, 'message': 'Chưa chọn file nào để tải lên'}), 400

    form_patient_id = request.form.get('patient_id', '').strip()
    form_patient_name = request.form.get('patient_name', '').strip()
    form_study_date = request.form.get('study_date', '').strip()
    form_accession_number = request.form.get('accession_number', '').strip()
    form_modality = request.form.get('modality', '').strip().upper()
    form_study_description = request.form.get('study_description', '').strip()
    form_study_instance_uid = request.form.get('study_instance_uid', '').strip()
    main_report_filename = request.form.get('main_report_filename', '').strip()

    # Scope validation for technician
    if user_role != 'ADMIN' and '*' not in allowed_modalities:
        if form_modality and form_modality not in allowed_modalities:
            return jsonify({'success': False, 'message': f'Bạn không có quyền đẩy ca thuộc Modality [{form_modality}]'}), 403
        if not form_modality and len(allowed_modalities) >= 1:
            form_modality = allowed_modalities[0]

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
@admin_required
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
@login_required
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
