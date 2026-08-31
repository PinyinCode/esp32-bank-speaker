from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

# Dictionary lưu thông báo theo từng MAC: { "MAC_ADDRESS": [danh_sách_thông_báo] }
device_notifications = {}

@app.route("/", methods=["GET"])
def home():
    return "Multi-Device Bank Speaker Server is running!"

# --- 1. API WEBHOOK: Nhận biến động số dư và phân loại theo MAC ---
# URL Webhook: https://<app>.onrender.com/api/bank-webhook/<mac_address>
@app.route("/api/bank-webhook/<path:mac>", methods=["POST"])
def bank_webhook(mac):
    mac_clean = mac.strip().upper().replace(":", "")
    data = request.get_json() or {}
    
    amount = data.get("transferAmount", 0)
    content = data.get("content", "")
    
    if amount and float(amount) > 0:
        amount_int = int(float(amount))
        message = f"Tài khoản đã nhận {amount_int:,} đồng. Nội dung: {content}"
        print(f"[BANK ALERT cho MAC {mac_clean}] {message}")
        
        # Khởi tạo danh sách thông báo cho MAC này nếu chưa có
        if mac_clean not in device_notifications:
            device_notifications[mac_clean] = []
            
        # Thêm thông báo mới vào hàng đợi của MAC đó
        device_notifications[mac_clean].append({
            "amount": amount_int,
            "message": message
        })
        
        return jsonify({"success": True, "message": f"Queued for {mac_clean}"}), 200
        
    return jsonify({"success": False, "error": "Invalid amount"}), 400

# --- 2. API CHO ESP32 GỌI ĐẾN ĐỂ LẤY THÔNG BÁO CỦA RIÊNG MÌNH ---
# Link ESP32 gọi: https://<app>.onrender.com/api/check-bank-audio?mac=240AC4123456
@app.route("/api/check-bank-audio", methods=["GET"])
def check_bank_audio():
    mac_address = request.args.get("mac")
    if not mac_address:
        return jsonify({"has_notification": False, "error": "Missing MAC"}), 400
        
    mac_clean = mac_address.strip().upper().replace(":", "")
    
    # Kiểm tra xem MAC này có thông báo nào đang chờ không
    if mac_clean in device_notifications and len(device_notifications[mac_clean]) > 0:
        # Lấy thông báo đầu tiên trong hàng đợi của MAC đó
        notif = device_notifications[mac_clean].pop(0)
        msg = notif["message"]
        
        # Tạo link giọng đọc Google TTS
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
