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
                return {
                    "chip_id": doc.get("_id", ""),
                    "username": doc.get("username", ""),
                    "status": doc.get("status", "active"),
                    "expires_at": doc.get("expires_at", ""),
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
                    devices_dict[chip_id] = {
                        "chip_id": chip_id,
                        "username": doc.get("username", ""),
                        "status": doc.get("status", "active"),
                        "expires_at": doc.get("expires_at", ""),
                        "trial": doc.get("trial", False),
                        "ota_pending": doc.get("ota_pending", False),
                        "created_at": doc.get("created_at", ""),
                        "sepay_secret": doc.get("sepay_secret", ""),
                        "notifications": doc.get("notifications", []),
                    }
    except Exception as e:
        print(f"Lỗi khi tải danh sách thiết bị: {e}")
    return devices_dict


# --- GIAO DIỆN TRANG ĐĂNG NHẬP ---
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng nhập - Quản lý OTA ESP32</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; background: #f2f2f7; display: flex; justify-content: center; align-items: center; min-height: 100vh; color: #1c1c1e; }
        .login-card { background: white; width: 90%; max-width: 420px; padding: 40px 30px; border-radius: 24px; box-shadow: 0 12px 40px rgba(0,0,0,0.06); text-align: center; box-sizing: border-box; }
        h2 { color: #007aff; font-size: 24px; margin-bottom: 8px; font-weight: 700; }
        p { color: #8e8e93; font-size: 14px; margin-bottom: 30px; }
        .github-btn { background: #24292e; color: white; padding: 14px 20px; text-decoration: none; border-radius: 12px; display: block; font-weight: 600; font-size: 15px; transition: background 0.2s; }
        .github-btn:hover { background: #1b1f23; }
        .portal-link { display: inline-block; margin-top: 20px; font-size: 14px; color: #007aff; text-decoration: none; font-weight: 500; }
        .portal-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>Quản Trị ESP32</h2>
        <p>Vui lòng xác thực tài khoản quản trị hệ thống</p>
        <a href="/login/authorize" class="github-btn">Đăng nhập bằng GitHub</a>
        <a href="/device-portal" class="portal-link">🔍 Vào cổng tra cứu & cấu hình SePay</a>
    </div>
</body>
</html>
"""

# --- GIAO DIỆN TRANG QUẢN TRỊ ---
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quản lý Bản quyền & OTA ESP32</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f2f2f7; color: #1c1c1e; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
        .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        h2 { color: #007aff; margin: 0; font-size: 20px; }
        .nav-links { display: flex; gap: 10px; align-items: center; }
        .portal-btn { background: #5856d6; color: white; padding: 8px 14px; text-decoration: none; border-radius: 10px; font-size: 13px; font-weight: 600; }
        .logout-btn { background: #ff3b30; color: white; padding: 8px 14px; text-decoration: none; border-radius: 10px; font-size: 13px; font-weight: 600; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; overflow-x: auto; display: block; }
        th, td { padding: 12px 10px; border-bottom: 1px solid #e5e5ea; text-align: left; font-size: 13px; }
        th { background: #fafafc; color: #3a3a3c; font-weight: 600; }
        input, select, button { padding: 8px 10px; margin: 3px 0; border: 1px solid #c7c7cc; border-radius: 8px; font-size: 13px; outline: none; box-sizing: border-box; }
        input:focus { border-color: #007aff; }
        button { background: #34c759; color: white; border: none; cursor: pointer; font-weight: 600; }
        button:hover { background: #28a745; }
        .ota-btn { background: #007aff; padding: 6px 10px; font-size: 12px; border-radius: 8px; color: white; text-decoration: none; display: inline-block; font-weight: 600; }
        .ota-active { background: #ffcc00; color: #1c1c1e; font-weight: bold; }
        .delete-btn { background: #ff3b30; padding: 6px 10px; font-size: 12px; border-radius: 8px; color: white; text-decoration: none; display: inline-block; margin-left: 3px; font-weight: 600; }
        .form-group { background: #fafafc; border: 1px solid #e5e5ea; padding: 20px; border-radius: 14px; margin-bottom: 25px; }
        .form-row { display: flex; gap: 15px; flex-wrap: wrap; }
        .form-col { flex: 1; min-width: 220px; }
        label { font-size: 12px; font-weight: 600; color: #3a3a3c; display: block; margin-bottom: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Quản lý Bản quyền & OTA ESP32 (Chip ID)</h2>
            <div class="nav-links">
                <a href="/device-portal" class="portal-btn" target="_blank">Cổng Tra Cứu (User)</a>
                <a href="/logout" class="logout-btn">Đăng xuất ({{ user }})</a>
            </div>
        </div>
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #e5e5ea;">
        
        <div class="form-group">
            <h3 style="margin-top: 0; font-size: 15px; color: #1c1c1e;">Thêm hoặc Cập nhật thiết bị mới</h3>
            <form action="/admin/add" method="POST">
                <div class="form-row">
                    <div class="form-col">
                        <label>Chip ID:</label>
                        <input type="text" name="chip_id" placeholder="Nhập Chip ID..." required style="width: 100%;">
                    </div>
                    <div class="form-col">
                        <label>Tên thiết bị:</label>
                        <input type="text" name="username" placeholder="Tên quản lý..." style="width: 100%;">
                    </div>
                    <div class="form-col">
                        <label>Ngày hết hạn:</label>
                        <input type="date" name="expiry_date" required style="width: 100%;">
                    </div>
                </div>
                <br>
                <button type="submit" style="padding: 10px 20px; border-radius: 10px;">Lưu / Cập nhật thiết bị</button>
            </form>
        </div>

        <h3 style="font-size: 15px; color: #1c1c1e;">Danh sách thiết bị đã lưu</h3>
        <table>
            <tr>
                <th>Chip ID</th>
                <th>Tên quản lý</th>
                <th>Trạng thái</th>
                <th>Hết hạn</th>
                <th>OTA</th>
                <th>Thao tác</th>
            </tr>
            {% for chip_id, info in devices.items() %}
            <tr>
                <td><b>{{ chip_id }}</b></td>
                <td>
                    <form action="/admin/update-username/{{ chip_id }}" method="POST" style="display: flex; gap: 4px; margin: 0;">
                        <input type="text" name="username" value="{{ info.username }}" placeholder="Tên..." style="flex: 1; font-size: 12px;">
                        <button type="submit" style="padding: 4px 8px; font-size: 11px;">Lưu</button>
                    </form>
                </td>
                <td style="color: {{ '#34c759' if info.status == 'active' else '#ff3b30' }}; font-weight: 600;">{{ info.status }}</td>
                <td>{{ info.expires_at[:10] if info.expires_at else '' }}</td>
                <td>
                    {% if info.get('ota_pending', False) %}
                        <span class="ota-btn ota-active" style="padding: 4px 8px; font-size: 11px;">Đang chờ</span>
                        <a href="/admin/cancel-ota/{{ chip_id }}" style="font-size:11px; color:#ff3b30; text-decoration: none; margin-left: 3px; font-weight: bold;">Hủy</a>
                    {% else %}
                        <a href="/admin/trigger-ota/{{ chip_id }}" class="ota-btn" style="padding: 4px 8px; font-size: 11px;">Kích hoạt</a>
                    {% endif %}
                </td>
                <td>
                    <a href="/admin/delete/{{ chip_id }}" class="delete-btn" onclick="return confirm('Xóa thiết bị này?');" style="padding: 4px 8px; font-size: 11px;">Xóa</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

# --- GIAO DIỆN TRA CỨU CHO USER ---
USER_PORTAL_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cổng Cấu Hình SePay & Firmware ESP32</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f2f2f7; color: #1c1c1e; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: white; width: 90%; max-width: 440px; padding: 30px; border-radius: 24px; box-shadow: 0 12px 40px rgba(0,0,0,0.06); box-sizing: border-box; text-align: center; }
        h2 { font-size: 22px; margin-bottom: 8px; color: #007aff; font-weight: 700; }
        p.subtitle { font-size: 13px; color: #8e8e93; margin-bottom: 25px; }
        .form-group { margin-bottom: 15px; text-align: left; }
        label { font-size: 13px; font-weight: 600; color: #3a3a3c; display: block; margin-bottom: 5px; }
        input { width: 100%; padding: 12px; border: 1px solid #c7c7cc; border-radius: 12px; font-size: 14px; box-sizing: border-box; outline: none; background: #fff; }
        input:focus { border-color: #007aff; }
        .btn { width: 100%; padding: 14px; background: #007aff; color: white; border: none; border-radius: 12px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
        .btn:hover { background: #0056b3; }
        .btn:disabled { background: #b0c4de; cursor: not-allowed; }
        .btn-green { background: #34c759; margin-top: 15px; }
        .btn-green:hover { background: #28a745; }
        .result-box { margin-top: 20px; background: #fafafc; border: 1px solid #e5e5ea; border-radius: 16px; padding: 20px; text-align: left; font-size: 13px; display: none; }
        .result-row { margin: 10px 0; }
        .status-active { color: #34c759; font-weight: bold; }
        .status-expired { color: #ff3b30; font-weight: bold; }
        .copy-row { display: flex; gap: 8px; margin-top: 6px; }
        .copy-btn { padding: 0 14px; background: #e5e5ea; border: none; border-radius: 10px; cursor: pointer; font-size: 13px; font-weight: 600; color: #1c1c1e; }
        .copy-btn:hover { background: #d1d1d6; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Cổng Thông Tin Thiết Bị</h2>
        <p class="subtitle">Nhập Chip ID để Tra cứu & Cập nhật Firmware</p>
        
        <div id="searchSection">
            <div class="form-group">
                <label>Chip ID:</label>
                <input type="text" id="chipIdInput" placeholder="Ví dụ: A1B2C3D4E5F6">
            </div>
            <button class="btn" id="searchBtn" type="button">Tra cứu thông tin</button>
        </div>

        <div id="resultCard" class="result-box">
            <div class="result-row"><span>Tên thiết bị:</span> <b id="resName">-</b></div>
            <div class="result-row"><span>Chip ID:</span> <b id="resChipId">-</b></div>
            <div class="result-row"><span>Trạng thái:</span> <span id="resStatus">-</span></div>
            <div class="result-row"><span>Hết hạn lúc:</span> <b id="resExpiry">-</b></div>
            
            <hr style="border: 0; border-top: 1px solid #e5e5ea; margin: 15px 0;">

            <div class="result-row">
                <label>SePay Webhook URL:</label>
                <div class="copy-row">
                    <input type="text" id="resWebhook" readonly>
                    <button class="copy-btn" type="button" onclick="copyText('resWebhook')">Copy</button>
                </div>
            </div>

            <div class="result-row" style="margin-top: 12px;">
                <label>SePay Secret / Key:</label>
                <div class="copy-row">
                    <input type="text" id="resSecret" readonly>
                    <button class="copy-btn" type="button" onclick="copyText('resSecret')">Copy</button>
                </div>
            </div>
            
            <button id="updateBtn" class="btn btn-green" style="display:none;" type="button">Yêu cầu Cập nhật Firmware</button>
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
                            statusEl.innerText = "Hoạt động (Active)";
                            statusEl.className = "status-active";
                            document.getElementById('updateBtn').style.display = "block";
                        } else {
                            statusEl.innerText = "Đã hết hạn (Expired)";
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
            alert("Đã sao chép thành công!");
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
