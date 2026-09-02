from datetime import datetime, timedelta
import os
import certifi
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from pymongo import MongoClient
import requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CẤU HÌNH MONGODB VỚI CERTIFI ---
MONGO_URI = os.environ.get("MONGO_URI", "")
client = None
db = None
devices_collection = None

try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        tls=True,
        tlsCAFile=certifi.where(),
    )
    client.admin.command("ping")
    db = client["esp32_manager"]
    devices_collection = db["devices"]
    print(">>> KẾT NỐI MONGODB THÀNH CÔNG VỚI CERTIFI! <<<")
except Exception as e:
    print(f">>> LỖI KẾT NỐI MONGODB: {e} <<<")

# --- CẤU HÌNH GITHUB OAUTH ---
GITHUB_CLIENT_ID = "Ov23liD2PKCxgNkZfUj5"
GITHUB_CLIENT_SECRET = "158a74d6beed0ed201ad9a7c4a041738d3185eb6"
YOUR_GITHUB_USERNAME = "PinyinCode"

DEFAULT_FIRMWARE_URL = "https://esp32-linkdownload.onrender.com/xiaozhi.bin"
DEFAULT_LATEST_VERSION = "v1.1.0"


def get_device(chip_id):
    try:
        if devices_collection is not None and chip_id:
            doc = devices_collection.find_one({"_id": chip_id})
            if doc:
                expires_at_str = doc.get("expires_at", "")
                status = doc.get("status", "active")
                if expires_at_str:
                    try:
                        expiry_time = datetime.fromisoformat(expires_at_str)
                        if datetime.utcnow() > expiry_time:
                            status = "expired"
                    except Exception:
                        pass

                return {
                    "chip_id": doc.get("_id", ""),
                    "username": doc.get("username", ""),
                    "status": status,
                    "expires_at": expires_at_str,
                    "trial": doc.get("trial", False),
                    "ota_pending": doc.get("ota_pending", False),
                    "created_at": doc.get("created_at", ""),
                    "sepay_secret": doc.get("sepay_secret", ""),
                    "notifications": doc.get("notifications", []),
                }
    except Exception as e:
        print(f"Lỗi khi tìm thiết bị {chip_id}: {e}")
    return None


def save_device(chip_id, data):
    try:
        if devices_collection is not None and chip_id:
            devices_collection.update_one({"_id": chip_id}, {"$set": data}, upsert=True)
    except Exception as e:
        print(f"Lỗi khi lưu thiết bị {chip_id}: {e}")


def load_db():
    devices_dict = {}
    try:
        if devices_collection is not None:
            for doc in devices_collection.find():
                chip_id = doc.get("_id")
                if chip_id:
                    dev = get_device(chip_id)
                    if dev:
                        devices_dict[chip_id] = dev
    except Exception as e:
        print(f"Lỗi khi tải danh sách thiết bị: {e}")
    return devices_dict


# --- GIAO DIỆN TRANG ĐĂNG NHẬP (CHUẨN APPLE/VERCEL) ---
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Xác thực Hệ thống - ESP32 Manager</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            margin: 0; 
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh; 
            color: #1d1d1f; 
        }
        .login-card { 
            background: rgba(255, 255, 255, 0.9); 
            backdrop-filter: blur(20px);
            width: 90%; 
            max-width: 420px; 
            padding: 48px 36px; 
            border-radius: 28px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.08); 
            text-align: center; 
            border: 1px solid rgba(255, 255, 255, 0.4);
        }
        .icon-box {
            width: 64px; height: 64px; background: linear-gradient(135deg, #007aff, #00c6ff);
            border-radius: 20px; display: flex; align-items: center; justify-content: center;
            margin: 0 auto 24px auto; color: white; font-size: 28px; box-shadow: 0 10px 20px rgba(0,122,255,0.3);
        }
        h2 { color: #1d1d1f; font-size: 24px; margin-bottom: 8px; font-weight: 700; letter-spacing: -0.5px; }
        p { color: #86868b; font-size: 14px; margin-bottom: 32px; line-height: 1.5; }
        .github-btn { 
            background: #000000; 
            color: white; 
            padding: 16px 20px; 
            text-decoration: none; 
            border-radius: 14px; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            gap: 12px;
            font-weight: 600; 
            font-size: 15px; 
            transition: all 0.3s ease; 
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }
        .github-btn:hover { background: #2c2c2e; transform: translateY(-2px); box-shadow: 0 12px 25px rgba(0,0,0,0.2); }
        .portal-link { 
            display: inline-block; 
            margin-top: 24px; 
            font-size: 14px; 
            color: #007aff; 
            text-decoration: none; 
            font-weight: 500; 
            transition: color 0.2s;
        }
        .portal-link:hover { color: #0056b3; text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="icon-box">⚡</div>
        <h2>Quản Trị ESP32</h2>
        <p>Hệ thống quản lý bản quyền phần cứng và phân phối OTA thông minh.</p>
        <a href="/login/authorize" class="github-btn">
            <svg height="20" viewBox="0 0 16 16" width="20" fill="#fff"><path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z"></path></svg>
            Đăng nhập bằng GitHub
        </a>
        <br>
        <a href="/device-portal" class="portal-link">🔍 Vào cổng tra cứu & cấu hình SePay</a>
    </div>
</body>
</html>
"""

# --- GIAO DIỆN TRANG QUẢN TRỊ (DASHBOARD CHUYÊN NGHIỆP) ---
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bảng Điều Khiển Quản Trị - ESP32 OTA</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            margin: 0; 
            background: #f5f5f7; 
            color: #1d1d1f; 
        }
        .container { max-width: 1350px; margin: 40px auto; background: white; padding: 36px; border-radius: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.04); }
        .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; }
        .brand { display: flex; align-items: center; gap: 14px; }
        .brand-icon { width: 44px; height: 44px; background: #007aff; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: white; font-size: 20px; font-weight: bold; }
        h2 { color: #1d1d1f; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
        .nav-links { display: flex; gap: 12px; align-items: center; }
        .btn-base { padding: 10px 18px; text-decoration: none; border-radius: 12px; font-size: 14px; font-weight: 600; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px; }
        .portal-btn { background: #f0f0f5; color: #1d1d1f; }
        .portal-btn:hover { background: #e5e5ea; }
        .logout-btn { background: #fff1f0; color: #ff3b30; }
        .logout-btn:hover { background: #ffe1e0; }
        
        .form-group { background: #fafafc; border: 1px solid #eaeaf0; padding: 28px; border-radius: 20px; margin: 30px 0; }
        .form-group h3 { margin-top: 0; font-size: 16px; color: #1d1d1f; font-weight: 600; margin-bottom: 20px; }
        .form-row { display: flex; gap: 20px; flex-wrap: wrap; }
        .form-col { flex: 1; min-width: 240px; }
        label { font-size: 13px; font-weight: 600; color: #3a3a3c; display: block; margin-bottom: 8px; }
        input, select { width: 100%; padding: 12px 14px; border: 1px solid #d2d2d7; border-radius: 12px; font-size: 14px; outline: none; background: #fff; transition: border-color 0.2s, box-shadow 0.2s; }
        input:focus { border-color: #007aff; box-shadow: 0 0 0 4px rgba(0,122,255,0.1); }
        
        .submit-btn { background: #007aff; color: white; border: none; cursor: pointer; font-weight: 600; padding: 12px 24px; border-radius: 12px; font-size: 14px; transition: background 0.2s; box-shadow: 0 4px 12px rgba(0,122,255,0.2); }
        .submit-btn:hover { background: #005ec4; }

        .table-container { width: 100%; overflow-x: auto; margin-top: 15px; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th, td { padding: 16px 14px; border-bottom: 1px solid #f0f0f5; font-size: 14px; vertical-align: middle; }
        th { background: #fbfbfd; color: #86868b; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        tr:hover td { background: #fafafc; }
        
        .badge { padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }
        .badge-active { background: #e3fcef; color: #00875a; }
        .badge-expired { background: #ffebe6; color: #de350b; }
        
        .action-btn { padding: 6px 12px; font-size: 12px; border-radius: 8px; text-decoration: none; font-weight: 600; display: inline-block; transition: all 0.2s; }
        .ota-pending { background: #fff8e1; color: #b78103; border: 1px solid #ffe082; }
        .ota-trigger { background: #e1f5fe; color: #0288d1; }
        .ota-trigger:hover { background: #b3e5fc; }
        .delete-btn { background: #fff5f5; color: #e53935; }
        .delete-btn:hover { background: #ffebee; }
        
        .inline-edit { display: flex; gap: 6px; align-items: center; }
        .inline-edit input { padding: 7px 10px; font-size: 13px; }
        .inline-edit button { padding: 7px 12px; font-size: 12px; background: #34c759; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; transition: background 0.2s; }
        .inline-edit button:hover { background: #28a745; }
        .view-name-btn { background: #e5e5ea; color: #1d1d1f; border: none; padding: 7px 10px; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 600; transition: background 0.2s; }
        .view-name-btn:hover { background: #d1d1d6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="brand">
                <div class="brand-icon">⚡</div>
                <h2>Hệ Thống Quản Lý Bản Quyền & OTA ESP32</h2>
            </div>
            <div class="nav-links">
                <a href="/device-portal" class="btn-base portal-btn" target="_blank">🌐 Cổng Tra Cứu (User)</a>
                <a href="/logout" class="btn-base logout-btn">🚪 Đăng xuất ({{ user }})</a>
            </div>
        </div>
        
        <div class="form-group">
            <h3>➕ Thêm hoặc Cập nhật thiết bị mới</h3>
            <form action="/admin/add" method="POST">
                <div class="form-row">
                    <div class="form-col">
                        <label>Chip ID phần cứng:</label>
                        <input type="text" name="chip_id" placeholder="Ví dụ: ESP32_A1B2C3" required>
                    </div>
                    <div class="form-col">
                        <label>Tên khách hàng / Thiết bị:</label>
                        <input type="text" name="username" placeholder="Nhập tên quản lý...">
                    </div>
                    <div class="form-col">
                        <label>Ngày hết hạn bản quyền:</label>
                        <input type="date" name="expiry_date" required>
                    </div>
                </div>
                <div style="margin-top: 20px;">
                    <button type="submit" class="submit-btn">Lưu / Cập nhật thiết bị</button>
                </div>
            </form>
        </div>

        <h3 style="font-size: 18px; color: #1d1d1f; margin-top: 40px; font-weight: 600;">📋 Danh sách thiết bị đã đăng ký</h3>
        <div class="table-container">
            <table>
                <tr>
                    <th>Chip ID</th>
                    <th>Tên Quản Lý</th>
                    <th>Trạng Thái</th>
                    <th>Ngày Hết Hạn</th>
                    <th>Trạng Thái OTA</th>
                    <th>Thao Tác</th>
                </tr>
                {% for chip_id, info in devices.items() %}
                <tr>
                    <td><code style="background: #f0f0f5; padding: 4px 8px; border-radius: 6px; font-weight: 600;">{{ chip_id }}</code></td>
                    <td>
                        <div class="inline-edit">
                            <form action="/admin/update-username/{{ chip_id }}" method="POST" class="inline-edit" style="display:flex; gap:6px;">
                                <input type="text" name="username" value="{{ info.username }}" placeholder="Tên..." style="max-width: 150px;">
                                <button type="submit">Lưu</button>
                            </form>
                            <button type="button" class="view-name-btn" onclick="alert('Tên quản lý đầy đủ cho chip {{ chip_id }}:\n\n{{ info.username if info.username else 'Chưa đặt tên' }}')">🔍 Xem</button>
                        </div>
                    </td>
                    <td>
                        {% if info.status == 'active' %}
                            <span class="badge badge-active">Hoạt động</span>
                        {% else %}
                            <span class="badge badge-expired">Hết hạn</span>
                        {% endif %}
                    </td>
                    <td>
                        <form action="/admin/update-expiry/{{ chip_id }}" method="POST" class="inline-edit">
                            <input type="date" name="expiry_date" value="{{ info.expires_at[:10] if info.expires_at else '' }}" required style="width: 140px;">
                            <button type="submit">Sửa</button>
                        </form>
                    </td>
                    <td>
                        {% if info.get('ota_pending', False) %}
                            <span class="action-btn ota-pending">⏳ Đang chờ OTA</span>
                            <a href="/admin/cancel-ota/{{ chip_id }}" style="font-size: 12px; color: #ff3b30; text-decoration: none; margin-left: 6px; font-weight: 600;">Hủy</a>
                        {% else %}
                            <a href="/admin/trigger-ota/{{ chip_id }}" class="action-btn ota-trigger">🚀 Kích hoạt OTA</a>
                        {% endif %}
                    </td>
                    <td>
                        <a href="/admin/delete/{{ chip_id }}" class="action-btn delete-btn" onclick="return confirm('Bạn có chắc chắn muốn xóa thiết bị này không?');">🗑️ Xóa</a>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
"""

# --- GIAO DIỆN TRA CỨU & CẤU HÌNH SEPAY (CHO USER) ---
USER_PORTAL_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cổng Cấu Hình SePay & Firmware ESP32</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); 
            color: #1d1d1f; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 20px;
        }
        .card { 
            background: rgba(255, 255, 255, 0.95); 
            backdrop-filter: blur(20px);
            width: 100%; 
            max-width: 480px; 
            padding: 40px 32px; 
            border-radius: 28px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.08); 
            border: 1px solid rgba(255, 255, 255, 0.5);
        }
        .icon-box {
            width: 56px; height: 56px; background: linear-gradient(135deg, #34c759, #28a745);
            border-radius: 16px; display: flex; align-items: center; justify-content: center;
            margin: 0 auto 20px auto; color: white; font-size: 24px; box-shadow: 0 8px 16px rgba(52,199,89,0.3);
        }
        h2 { font-size: 22px; margin-bottom: 6px; color: #1d1d1f; font-weight: 700; text-align: center; letter-spacing: -0.5px; }
        p.subtitle { font-size: 14px; color: #86868b; margin-bottom: 28px; text-align: center; }
        
        .form-group { margin-bottom: 20px; text-align: left; }
        label { font-size: 13px; font-weight: 600; color: #3a3a3c; display: block; margin-bottom: 8px; }
        input { width: 100%; padding: 14px; border: 1px solid #d2d2d7; border-radius: 14px; font-size: 14px; outline: none; background: #fff; transition: all 0.2s; }
        input:focus { border-color: #007aff; box-shadow: 0 0 0 4px rgba(0,122,255,0.1); }
        
        .btn { width: 100%; padding: 14px; background: #007aff; color: white; border: none; border-radius: 14px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; box-shadow: 0 6px 16px rgba(0,122,255,0.25); }
        .btn:hover { background: #005ec4; transform: translateY(-1px); }
        .btn:disabled { background: #b0c4de; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn-green { background: #34c759; box-shadow: 0 6px 16px rgba(52,199,89,0.25); margin-top: 15px; }
        .btn-green:hover { background: #28a745; }
        
        .result-box { margin-top: 24px; background: #fafafc; border: 1px solid #eaeaf0; border-radius: 20px; padding: 24px; text-align: left; font-size: 14px; display: none; }
        .result-row { margin: 12px 0; display: flex; justify-content: space-between; align-items: center; }
        .result-row span { color: #86868b; }
        .result-row b { color: #1d1d1f; }
        
        .status-active { color: #00875a; background: #e3fcef; padding: 4px 10px; border-radius: 20px; font-weight: 600; font-size: 12px; }
        .status-expired { color: #de350b; background: #ffebe6; padding: 4px 10px; border-radius: 20px; font-weight: 600; font-size: 12px; }
        
        .copy-row { display: flex; gap: 8px; margin-top: 6px; width: 100%; }
        .copy-btn { padding: 0 16px; background: #e5e5ea; border: none; border-radius: 10px; cursor: pointer; font-size: 13px; font-weight: 600; color: #1d1d1f; transition: background 0.2s; }
        .copy-btn:hover { background: #d1d1d6; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-box">🔍</div>
        <h2>Tra Cứu Thiết Bị</h2>
        <p class="subtitle">Nhập Chip ID để kiểm tra bản quyền và cấu hình SePay Webhook</p>
        
        <div id="searchSection">
            <div class="form-group">
                <label>Mã Chip ID phần cứng:</label>
                <input type="text" id="chipIdInput" placeholder="Ví dụ: ESP32_A1B2C3...">
            </div>
            <button class="btn" id="searchBtn" type="button">Tra cứu thông tin</button>
        </div>

        <div id="resultCard" class="result-box">
            <div class="result-row"><span>Tên thiết bị:</span> <b id="resName">-</b></div>
            <div class="result-row"><span>Chip ID:</span> <b id="resChipId">-</b></div>
            <div class="result-row"><span>Trạng thái:</span> <span id="resStatus">-</span></div>
            <div class="result-row"><span>Hết hạn lúc:</span> <b id="resExpiry">-</b></div>
            
            <hr style="border: 0; border-top: 1px solid #eaeaf0; margin: 18px 0;">

            <div style="margin-top: 10px;">
                <label>SePay Webhook URL:</label>
                <div class="copy-row">
                    <input type="text" id="resWebhook" readonly>
                    <button class="copy-btn" type="button" onclick="copyText('resWebhook')">Sao chép</button>
                </div>
            </div>

            <div style="margin-top: 14px;">
                <label>SePay Secret Key:</label>
                <div class="copy-row">
                    <input type="text" id="resSecret" readonly>
                    <button class="copy-btn" type="button" onclick="copyText('resSecret')">Sao chép</button>
                </div>
            </div>
            
            <button id="updateBtn" class="btn btn-green" style="display:none;" type="button">🚀 Yêu cầu Cập nhật Firmware OTA</button>
        </div>
    </div>

    <script>
        document.addEventListener("DOMContentLoaded", function() {
            document.getElementById('searchBtn').addEventListener('click', async function() {
                let chipId = document.getElementById('chipIdInput').value.trim();
                
                if (!chipId) {
                    alert('Vui lòng nhập Chip ID!');
                    return;
                }

                const btn = this;
                btn.disabled = true;
                btn.innerText = "Đang tra cứu...";

                try {
                    const response = await fetch('/api/user/lookup', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ chip_id: chipId })
                    });
                    const data = await response.json();

                    if (response.ok) {
                        document.getElementById('resName').innerText = data.username || "Chưa đặt tên";
                        document.getElementById('resChipId').innerText = data.chip_id || chipId;
                        
                        const statusEl = document.getElementById('resStatus');
                        if (data.status === 'active') {
                            statusEl.innerText = "Hoạt động";
                            statusEl.className = "status-active";
                            document.getElementById('updateBtn').style.display = "block";
                        } else {
                            statusEl.innerText = "Đã hết hạn";
                            statusEl.className = "status-expired";
                            document.getElementById('updateBtn').style.display = "none";
                        }

                        document.getElementById('resExpiry').innerText = new Date(data.expires_at).toLocaleString('vi-VN');
                        document.getElementById('resWebhook').value = data.webhook_url || "";
                        document.getElementById('resSecret').value = data.sepay_secret || "";
                        document.getElementById('resultCard').style.display = "block";
                    } else {
                        alert("Lỗi: " + (data.error || "Không tìm thấy thiết bị hoặc sai thông tin."));
                    }
                } catch (e) {
                    alert("Lỗi kết nối: " + e.message);
                } finally {
                    btn.disabled = false;
                    btn.innerText = "Tra cứu thông tin";
                }
            });

            document.getElementById('updateBtn').addEventListener('click', async function() {
                let chipId = document.getElementById('chipIdInput').value.trim();
                if (!chipId) return;

                try {
                    const response = await fetch('/api/user/request-ota', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ chip_id: chipId })
                    });
                    const data = await response.json();
                    if (response.ok) {
                        alert("✓ Đã kích hoạt chế độ cập nhật OTA thành công!");
                    } else {
                        alert("Lỗi: " + (data.error || "Không thể kích hoạt cập nhật."));
                    }
                } catch (e) {
                    alert("Lỗi kết nối khi gửi yêu cầu OTA.");
                }
            });
        });

        function copyText(elementId) {
            const copyText = document.getElementById(elementId);
            copyText.select();
            copyText.setSelectionRange(0, 9999);
            navigator.clipboard.writeText(copyText.value);
            alert("Đã sao chép vào bộ nhớ tạm!");
        }
    </script>
</body>
</html>
"""


# --- ROUTE XÁC THỰC & ĐĂNG NHẬP ADMIN ---
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login")
def login():
    if "user" in session:
        return redirect(url_for("admin_panel"))
    return render_template_string(LOGIN_HTML)


@app.route("/login/authorize")
def login_authorize():
    return redirect(f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}")


@app.route("/login/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Đăng nhập thất bại từ GitHub!", 400

    token_json = requests.post(
        "https://github.com/login/oauth/access_token",
        json={"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code},
        headers={"Accept": "application/json"},
    ).json()

    access_token = token_json.get("access_token")
    if not access_token:
        return "Không thể lấy Token xác thực từ GitHub!", 400

    user_data = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    ).json()

    if user_data.get("login", "").lower() == YOUR_GITHUB_USERNAME.lower():
        session["user"] = user_data.get("login")
        return redirect(url_for("admin_panel"))
    return "Truy cập bị từ chối!", 403


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin", methods=["GET"])
def admin_panel():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template_string(ADMIN_HTML, devices=load_db(), user=session["user"])


@app.route("/admin/add", methods=["POST"])
def admin_add():
    if "user" not in session:
        return redirect(url_for("login"))

    chip_id = request.form.get("chip_id", "").strip()
    username = request.form.get("username", "").strip()
    expiry_date_str = request.form.get("expiry_date")

    import uuid

    if chip_id and expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            device = get_device(chip_id)
            sepay_secret = device.get("sepay_secret") if device and device.get("sepay_secret") else f"whsec_{uuid.uuid4().hex}"

            if device:
                device["expires_at"] = expiry_date.isoformat()
                if username: 
                    device["username"] = username
                device["status"] = "active"
                device["sepay_secret"] = sepay_secret
            else:
                device = {
                    "username": username,
                    "status": "active",
                    "expires_at": expiry_date.isoformat(),
                    "trial": False,
                    "ota_pending": False,
                    "created_at": datetime.utcnow().isoformat(),
                    "sepay_secret": sepay_secret,
                    "notifications": [],
                }
            save_device(chip_id, device)
        except ValueError:
            pass

    return redirect(url_for("admin_panel"))


@app.route("/admin/update-username/<path:chip_id>", methods=["POST"])
def update_username(chip_id):
    if "user" not in session:
        return redirect(url_for("login"))
    chip_id = chip_id.strip()
    username = request.form.get("username", "").strip()
    device = get_device(chip_id)
    if device:
        device["username"] = username
        save_device(chip_id, device)
    return redirect(url_for("admin_panel"))


@app.route("/admin/update-expiry/<path:chip_id>", methods=["POST"])
def update_expiry(chip_id):
    if "user" not in session:
        return redirect(url_for("login"))
    chip_id = chip_id.strip()
    expiry_date_str = request.form.get("expiry_date")
    device = get_device(chip_id)
    
    if device and expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            device["expires_at"] = expiry_date.isoformat()
            save_device(chip_id, device)
        except ValueError:
            pass
    return redirect(url_for("admin_panel"))


@app.route("/admin/trigger-ota/<path:chip_id>", methods=["GET"])
def trigger_ota(chip_id):
    if "user" not in session:
        return redirect(url_for("login"))
    chip_id = chip_id.strip()
    device = get_device(chip_id)
    if device:
        device["ota_pending"] = True
        save_device(chip_id, device)
    return redirect(url_for("admin_panel"))


@app.route("/admin/cancel-ota/<path:chip_id>", methods=["GET"])
def cancel_ota(chip_id):
    if "user" not in session:
        return redirect(url_for("login"))
    chip_id = chip_id.strip()
    device = get_device(chip_id)
    if device:
        device["ota_pending"] = False
        save_device(chip_id, device)
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete/<path:chip_id>", methods=["GET"])
def admin_delete(chip_id):
    if "user" not in session:
        return redirect(url_for("login"))
    chip_id = chip_id.strip()
    try:
        if devices_collection is not None:
            devices_collection.delete_one({"_id": chip_id})
    except Exception as e:
        print(f"Lỗi khi xóa thiết bị {chip_id}: {e}")
    return redirect(url_for("admin_panel"))


# --- CỔNG TRA CỨU CÔNG KHAI ---
@app.route("/device-portal", methods=["GET"])
def device_portal():
    return render_template_string(USER_PORTAL_HTML)


@app.route("/api/user/lookup", methods=["POST"])
def user_lookup():
    data = request.get_json() or {}
    chip_id = data.get("chip_id", "").strip()

    if not chip_id:
        return jsonify({"error": "Vui lòng nhập Chip ID"}), 400

    device_info = get_device(chip_id)

    if not device_info:
        return jsonify({"error": "Chip ID chưa tồn tại trên hệ thống. Vui lòng liên hệ quản trị viên."}), 404

    import uuid
    if not device_info.get("sepay_secret"):
        device_info["sepay_secret"] = f"whsec_{uuid.uuid4().hex}"
        save_device(chip_id, device_info)

    now = datetime.utcnow()
    try:
        expiry_time = datetime.fromisoformat(device_info["expires_at"])
    except Exception:
        expiry_time = now

    status = "active" if now <= expiry_time else "expired"
    host_url = request.host_url.rstrip("/")
    webhook_url = f"{host_url}/api/bank-webhook/{chip_id}"

    return jsonify(
        {
            "success": True,
            "chip_id": chip_id,
            "username": device_info.get("username", ""),
            "status": status,
            "expires_at": device_info["expires_at"],
            "webhook_url": webhook_url,
            "sepay_secret": device_info["sepay_secret"],
        }
    )


@app.route("/api/user/request-ota", methods=["POST"])
def user_request_ota():
    data = request.get_json() or {}
    chip_id = data.get("chip_id", "").strip()

    if not chip_id:
        return jsonify({"error": "Thiếu thông tin Chip ID"}), 400

    device_info = get_device(chip_id)

    if not device_info:
        return jsonify({"error": "Thiết bị không tồn tại"}), 404

    now = datetime.utcnow()
    try:
        expiry_time = datetime.fromisoformat(device_info["expires_at"])
    except Exception:
        expiry_time = now

    if now > expiry_time:
        return jsonify({"error": "Bản quyền thiết bị đã hết hạn!"}), 403

    device_info["ota_pending"] = True
    save_device(chip_id, device_info)

    return jsonify({"success": True, "message": "Đã kích hoạt chế độ cập nhật OTA."})


# --- API DÀNH CHO ESP32 (DÙNG CHIP_ID) ---
@app.route("/api/check-license", methods=["GET"])
def check_license():
    chip_id = request.args.get("chip_id", "").strip()

    if not chip_id:
        return jsonify({"error": "Missing chip_id parameter", "status": "error"}), 400

    now = datetime.utcnow()
    device_info = get_device(chip_id)

    import uuid
    if not device_info:
        expiry_date = now + timedelta(days=30)
        device_info = {
            "username": "",
            "status": "active",
            "expires_at": expiry_date.isoformat(),
            "trial": True,
            "ota_pending": False,
            "created_at": now.isoformat(),
            "sepay_secret": f"whsec_{uuid.uuid4().hex}",
            "notifications": [],
        }
        save_device(chip_id, device_info)

    expiry_time = datetime.fromisoformat(device_info["expires_at"])

    if now > expiry_time:
        device_info["status"] = "expired"
        save_device(chip_id, device_info)
        return jsonify(
            {
                "chip_id": chip_id,
                "status": "expired",
                "message": "License expired.",
                "expires_at": device_info["expires_at"],
            }
        )

    return jsonify(
        {
            "chip_id": chip_id,
            "status": "active",
            "message": "License is valid.",
            "trial": device_info["trial"],
            "expires_at": device_info["expires_at"],
        }
    )


@app.route("/api/check-update", methods=["GET"])
def check_update():
    chip_id = request.args.get("chip_id", "").strip()

    if not chip_id:
        return jsonify({"update_available": False, "error": "Missing chip_id"}), 400

    device_info = get_device(chip_id)

    if not device_info:
        return jsonify({"update_available": False, "message": "Device not registered."})

    now = datetime.utcnow()
    try:
        expiry_time = datetime.fromisoformat(device_info["expires_at"])
    except Exception:
        expiry_time = now

    if now > expiry_time:
        device_info["status"] = "expired"
        device_info["ota_pending"] = False
        save_device(chip_id, device_info)
        return jsonify({"update_available": False, "message": "License expired. Update denied."})

    if device_info.get("ota_pending", False):
        device_info["ota_pending"] = False
        save_device(chip_id, device_info)

        return jsonify(
            {
                "update_available": True,
                "latest_version": DEFAULT_LATEST_VERSION,
                "firmware_url": DEFAULT_FIRMWARE_URL,
                "changelog": "Cập nhật thành công theo yêu cầu hợp lệ.",
            }
        )

    return jsonify({"update_available": False})


@app.route("/api/bank-webhook/<path:chip_id>", methods=["POST"])
def bank_webhook(chip_id):
    if devices_collection is None:
        return jsonify({"success": False, "error": "Database error"}), 500

    chip_id_clean = chip_id.strip()
    device = get_device(chip_id_clean)

    if not device:
        return jsonify({"success": False, "error": "Chip ID not registered in system"}), 404

    data = request.get_json() or {}
    amount = data.get("transferAmount", 0)

    if amount and float(amount) > 0:
        amount_int = int(float(amount))
        audio_message = f"Tài khoản của bạn vừa nhận được {amount_int:,} đồng."

        if "notifications" not in device or not isinstance(device["notifications"], list):
            device["notifications"] = []

        device["notifications"].append(
            {
                "amount": amount_int,
                "message": audio_message,
                "created_at": datetime.utcnow().isoformat(),
            }
        )

        save_device(chip_id_clean, device)
        return jsonify({"success": True}), 200

    return jsonify({"success": False, "error": "Invalid amount"}), 400


@app.route("/api/check-bank-audio", methods=["GET"])
def check_bank_audio():
    chip_id = request.args.get("chip_id", "").strip()
    if not chip_id:
        return jsonify({"has_notification": False}), 400

    device = get_device(chip_id)

    if not device:
        return jsonify({"has_notification": False}), 404

    notifications = device.get("notifications", [])
    if len(notifications) > 0:
        notif = notifications.pop(0)
        save_device(chip_id, device)

        msg = notif["message"]
        encoded_msg = requests.utils.quote(msg)
        audio_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_msg}&tl=vi&client=tw-ob"

        return jsonify(
            {
                "has_notification": True,
                "chip_id": chip_id,
                "message": msg,
                "audio_url": audio_url,
            }
        )

    return jsonify({"has_notification": False})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
