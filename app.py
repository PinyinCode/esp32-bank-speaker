from flask import Flask, jsonify, request, render_template_string
import requests
import os
import hmac
import hashlib

app = Flask(__name__)

# Lấy mã bí mật từ biến môi trường trên Render
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default_secret_key")

# Lưu trữ danh sách thiết bị đã đăng ký: { "MAC": {"bank_account": "...", "created_at": "..."} }
registered_devices = {}

# Lưu trữ thông báo chờ đọc theo từng MAC: { "MAC": [ {amount, message} ] }
device_notifications = {}

# --- GIAO DIỆN PORTAL CHO KHÁCH HÀNG TỰ ĐĂNG KÝ ---
USER_PORTAL_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kích hoạt Loa Tinh Tinh - Cổng Khách Hàng</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f2f2f7; color: #1c1c1e; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: white; width: 450px; padding: 30px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); box-sizing: border-box; text-align: center; }
        h2 { font-size: 22px; margin-bottom: 8px; color: #007aff; }
        p.subtitle { font-size: 13px; color: #8e8e93; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; text-align: left; }
        label { font-size: 13px; font-weight: 600; color: #3a3a3c; display: block; margin-bottom: 5px; }
        input { width: 100%; padding: 12px; border: 1px solid #c7c7cc; border-radius: 10px; font-size: 14px; box-sizing: border-box; outline: none; }
        input:focus { border-color: #007aff; }
        .btn { width: 100%; padding: 12px; background: #007aff; color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
        .btn:hover { background: #0056b3; }
        .result-box { margin-top: 20px; background: #fafafc; border: 1px solid #e5e5ea; border-radius: 12px; padding: 15px; text-align: left; font-size: 13px; display: none; }
        .webhook-url { background: #e5e5ea; padding: 8px; border-radius: 6px; word-break: break-all; font-family: monospace; font-size: 12px; margin-top: 5px; color: #d70015; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Đăng Ký Loa Ngân Hàng</h2>
        <p class="subtitle">Nhập địa chỉ MAC trên thiết bị của bạn để lấy link Webhook</p>
        
        <div class="form-group">
            <label>Địa chỉ MAC của ESP32:</label>
            <input type="text" id="macInput" placeholder="Ví dụ: 24:0A:C4:12:34:56">
        </div>
        <button class="btn" onclick="registerDevice()">Tạo Link Webhook</button>

        <div id="resultCard" class="result-box">
            <b>✓ Đăng ký thành công!</b>
            <p style="margin: 8px 0 4px 0; color: #666;">Hãy copy đường dẫn Webhook dưới đây dán vào cài đặt SePay của bạn:</p>
            <div class="webhook-url" id="webhookResult"></div>
        </div>
    </div>

    <script>
        async function registerDevice() {
            const mac = document.getElementById('macInput').value.trim();
            if (!mac) {
                alert('Vui lòng nhập địa chỉ MAC!');
                return;
            }

            try {
                const response = await fetch('/api/user/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mac: mac })
                });
                const data = await response.json();

                if (response.ok) {
                    document.getElementById('webhookResult').innerText = data.webhook_url;
                    document.getElementById('resultCard').style.display = 'block';
                } else {
                    alert(data.error || "Không thể đăng ký thiết bị.");
                }
            } catch (e) {
                alert("Lỗi kết nối đến máy chủ.");
            }
        }
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return redirect_portal()

@app.route("/device-portal", methods=["GET"])
def redirect_portal():
    return render_template_string(USER_PORTAL_HTML)

# --- API KHÁCH HÀNG GỬI MAC ĐỂ ĐĂNG KÝ ---
@app.route("/api/user/register", methods=["POST"])
def user_register():
    data = request.get_json() or {}
    mac = data.get("mac")
    if not mac:
        return jsonify({"error": "Thiếu thông tin địa chỉ MAC"}), 400
        
    mac_clean = mac.strip().upper().replace(":", "")
    
    # Lưu vào danh sách thiết bị
    if mac_clean not in registered_devices:
        registered_devices[mac_clean] = {"created_at": True}
        
    # Tạo URL Webhook riêng cho MAC này dựa trên host hiện tại của Render
    host_url = request.host_url.rstrip('/')
    webhook_url = f"{host_url}/api/bank-webhook/{mac_clean}"
    
    return jsonify({
        "success": True,
        "mac": mac_clean,
        "webhook_url": webhook_url
    })

# --- API WEBHOOK NHẬN TỪ SEPAY (CÓ BẢO MẬT HMAC) ---
@app.route("/api/bank-webhook/<path:mac>", methods=["POST"])
def bank_webhook(mac):
    mac_clean = mac.strip().upper().replace(":", "")
    
    # Kiểm tra MAC có tồn tại trong hệ thống đã đăng ký không
    if mac_clean not in registered_devices:
        return jsonify({"success": False, "error": "Device MAC not registered"}), 404
        
    # Xác thực chữ ký HMAC-SHA256 từ SePay
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
        
        if mac_clean not in device_notifications:
            device_notifications[mac_clean] = []
            
        device_notifications[mac_clean].append({
            "amount": amount_int,
            "message": message
        })
        
        return jsonify({"success": True, "message": f"Queued for {mac_clean}"}), 200
        
    return jsonify({"success": False, "error": "Invalid amount"}), 400

# --- API CHO ESP32 GỌI ĐẾN ĐỂ LẤY THÔNG BÁO ---
@app.route("/api/check-bank-audio", methods=["GET"])
def check_bank_audio():
    mac_address = request.args.get("mac")
    if not mac_address:
        return jsonify({"has_notification": False, "error": "Missing MAC"}), 400
        
    mac_clean = mac_address.strip().upper().replace(":", "")
    
    if mac_clean in device_notifications and len(device_notifications[mac_clean]) > 0:
        notif = device_notifications[mac_clean].pop(0)
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
