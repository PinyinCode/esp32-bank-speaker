from flask import Flask, jsonify, request, render_template_string
import requests
import os
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from pymongo import MongoClient

app = Flask(__name__)

# --- CẤU HÌNH MONGODB & BẢO MẬT ---
MONGO_URI = os.environ.get("MONGO_URI") 
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default_sepay_secret")

client = None
db = None
devices_collection = None

try:
    if MONGO_URI:
        client = MongoClient(MONGO_URI)
        db = client["esp32_bank_db"] 
        devices_collection = db["bank_devices"]
        
        # TẠO TTL INDEX CHO MẢNG NOTIFICATIONS (Tự động xóa sau 24 giờ = 86400 giây)
        try:
            devices_collection.create_index(
                [("notifications.created_at", 1)],
                expireAfterSeconds=86400
            )
            print("✓ Đã cấu hình tự động xóa thông báo sau 24 giờ (TTL Index)!")
        except Exception as idx_err:
            print(f"⚠️ Không thể tạo TTL Index: {idx_err}")

        print("✓ Kết nối MongoDB thành công!")
    else:
        print("⚠️ Chưa cấu hình biến môi trường MONGO_URI trên Render!")
except Exception as e:
    print(f"❌ Lỗi kết nối MongoDB: {e}")

# --- GIAO DIỆN PORTAL CHO KHÁCH HÀNG TỰ ĐĂNG KÝ ---
USER_PORTAL_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kích hoạt Loa Ngân Hàng - ESP32</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f2f2f7; color: #1c1c1e; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: white; width: 480px; padding: 30px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); box-sizing: border-box; text-align: center; }
        h2 { font-size: 22px; margin-bottom: 8px; color: #007aff; }
        p.subtitle { font-size: 13px; color: #8e8e93; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; text-align: left; }
        label { font-size: 13px; font-weight: 600; color: #3a3a3c; display: block; margin-bottom: 5px; }
        input { width: 100%; padding: 12px; border: 1px solid #c7c7cc; border-radius: 10px; font-size: 14px; box-sizing: border-box; outline: none; }
        input:focus { border-color: #007aff; }
        .btn { width: 100%; padding: 12px; background: #007aff; color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
        .btn:hover { background: #0056b3; }
        .result-box { margin-top: 20px; background: #fafafc; border: 1px solid #e5e5ea; border-radius: 12px; padding: 15px; text-align: left; font-size: 13px; display: none; }
        .code-block { background: #e5e5ea; padding: 8px; border-radius: 6px; word-break: break-all; font-family: monospace; font-size: 12px; margin-top: 5px; color: #d70015; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Đăng Ký Loa Ngân Hàng</h2>
        <p class="subtitle">Nhập địa chỉ MAC thiết bị của bạn để lấy thông tin cấu hình</p>
        
        <div class="form-group">
            <label>Địa chỉ MAC của ESP32:</label>
            <input type="text" id="macInput" placeholder="Ví dụ: 24:0A:C4:12:34:56">
        </div>
        <button class="btn" onclick="registerDevice()">Kích Hoạt Thiết Bị</button>

        <div id="resultCard" class="result-box">
            <b>✓ Đăng ký thành công!</b>
            <p style="margin: 8px 0 2px 0; color: #666;">1. Copy đường dẫn Webhook dán vào SePay:</p>
            <div class="code-block" id="webhookResult"></div>
            <p style="margin: 10px 0 2px 0; color: #666;">2. Token bảo mật nạp vào code ESP32:</p>
            <div class="code-block" id="tokenResult" style="color: #007aff;"></div>
        </div>
    </div>

    <script>
        async function registerDevice() {
            const mac = document.getElementById('macInput').value.trim();
            if (!mac) { alert('Vui lòng nhập địa chỉ MAC!'); return; }

            try {
                const response = await fetch('/api/user/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mac: mac })
                });
                const data = await response.json();

                if (response.ok) {
                    document.getElementById('webhookResult').innerText = data.webhook_url;
                    document.getElementById('tokenResult').innerText = data.device_token;
                    document.getElementById('resultCard').style.display = 'block';
                } else {
                    alert(data.error || "Không thể đăng ký thiết bị.");
                }
            } catch (e) { alert("Lỗi kết nối đến máy chủ."); }
        }
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return render_template_string(USER_PORTAL_HTML)

# --- 1. API KHÁCH HÀNG ĐĂNG KÝ MAC ---
@app.route("/api/user/register", methods=["POST"])
def user_register():
    if devices_collection is None:
        return jsonify({"error": "Chưa kết nối cơ sở dữ liệu MongoDB"}), 500

    data = request.get_json() or {}
    mac = data.get("mac")
    if not mac:
        return jsonify({"error": "Thiếu thông tin địa chỉ MAC"}), 400
        
    mac_clean = mac.strip().upper().replace(":", "")
    
    existing_device = devices_collection.find_one({"_id": mac_clean})
    if existing_device:
        device_token = existing_device.get("device_token")
    else:
        device_token = str(uuid.uuid4())
        devices_collection.insert_one({
            "_id": mac_clean,
            "device_token": device_token,
            "notifications": []
        })
        
    host_url = request.host_url.rstrip('/')
    webhook_url = f"{host_url}/api/bank-webhook/{mac_clean}"
    
    return jsonify({
        "success": True,
        "mac": mac_clean,
        "webhook_url": webhook_url,
        "device_token": device_token
    })

# --- 2. API WEBHOOK NHẬN TỪ SEPAY ---
@app.route("/api/bank-webhook/<path:mac>", methods=["POST"])
def bank_webhook(mac):
    if devices_collection is None:
        return jsonify({"success": False, "error": "Database error"}), 500

    mac_clean = mac.strip().upper().replace(":", "")
    
    device = devices_collection.find_one({"_id": mac_clean})
    if not device:
        return jsonify({"success": False, "error": "Device MAC not registered"}), 404
        
    # Xác thực chữ ký HMAC-SHA256 bảo mật từ SePay
    signature = request.headers.get("X-SePay-Signature", "")
    raw_body = request.get_data()
    computed_signature = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    if signature and not hmac.compare_digest(signature, computed_signature):
        return jsonify({"success": False, "error": "Invalid signature"}), 401

    data = request.get_json() or {}
    amount = data.get("transferAmount", 0)
    content = data.get("content", "")
    
    if amount and float(amount) > 0:
        amount_int = int(float(amount))
        message = f"Tài khoản đã nhận {amount_int:,} đồng. Nội dung: {content}"
        print(f"[BANK ALERT cho MAC {mac_clean}] {message}")
        
        devices_collection.update_one(
            {"_id": mac_clean},
            {
                "$push": {
                    "notifications": {
                        "amount": amount_int,
                        "message": message,
                        "created_at": datetime.now(timezone.utc)
                    }
                }
            }
        )
        
        return jsonify({"success": True, "message": f"Queued for {mac_clean}"}), 200
        
    return jsonify({"success": False, "error": "Invalid amount"}), 400

# --- 3. API CHO ESP32 GỌI ĐẾN ĐỂ LẤY THÔNG BÁO ---
@app.route("/api/check-bank-audio", methods=["GET"])
def check_bank_audio():
    if devices_collection is None:
        return jsonify({"has_notification": False, "error": "Database error"}), 500

    mac_address = request.args.get("mac")
    token = request.args.get("token")
    
    if not mac_address or not token:
        return jsonify({"has_notification": False, "error": "Missing MAC or Token"}), 400
        
    mac_clean = mac_address.strip().upper().replace(":", "")
    
    device = devices_collection.find_one({"_id": mac_clean})
    if not device or device.get("device_token") != token:
        return jsonify({"has_notification": False, "error": "Unauthorized"}), 403
        
    notifications = device.get("notifications", [])
    if len(notifications) > 0:
        notif = notifications.pop(0)
        
        devices_collection.update_one(
            {"_id": mac_clean},
            {"$set": {"notifications": notifications}}
        )
        
        msg = notif["message"]
        encoded_msg = requests.utils.quote(msg)
        audio_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_msg}&tl=vi&client=tw-ob"
        
        return jsonify({
            "has_notification": True,
            "mac": mac_clean,
            "message": msg,
            "audio_url": audio_url
        })
        
    return jsonify({"has_notification": False})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
