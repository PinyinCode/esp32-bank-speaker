from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

# Biến tạm lưu thông báo chuyển khoản gần nhất
latest_bank_notification = None

@app.route("/", methods=["GET"])
def home():
    return "ESP32 Bank Speaker Server is running!"

# --- 1. API WEBHOOK: Nhận biến động số dư từ dịch vụ ngân hàng (SePay / Casso) ---
@app.route("/api/bank-webhook", methods=["POST"])
def bank_webhook():
    global latest_bank_notification
    data = request.get_json() or {}
    
    # Lấy thông tin số tiền và nội dung từ Webhook ngân hàng gửi về
    amount = data.get("transferAmount", 0)
    content = data.get("content", "")
    
    if amount and float(amount) > 0:
        amount_int = int(float(amount))
        message = f"Tài khoản đã nhận {amount_int:,} đồng. Nội dung: {content}"
        print(f"[BANK ALERT] {message}")
        
        # Lưu lại trạng thái chưa đọc để ESP32 lấy
        latest_bank_notification = {
            "amount": amount_int,
            "message": message,
            "unread": True
        }
        return jsonify({"success": True, "message": "Webhook processed"}), 200
        
    return jsonify({"success": False, "error": "Invalid amount"}), 400

# --- 2. API CHO ESP32 GỌI ĐẾN ĐỊNH KỲ (POLLING) ---
@app.route("/api/check-bank-audio", methods=["GET"])
def check_bank_audio():
    global latest_bank_notification
    
    # Kiểm tra xem có thông báo mới nào chưa đọc không
    if latest_bank_notification and latest_bank_notification.get("unread"):
        # Đánh dấu đã đọc để không phát lại ở lần gọi sau
        latest_bank_notification["unread"] = False
        
        msg = latest_bank_notification["message"]
        
        # Chuyển văn bản thành link âm thanh giọng đọc tiếng Việt (Google TTS)
        encoded_msg = requests.utils.quote(msg)
        audio_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_msg}&tl=vi&client=tw-ob"
        
        return jsonify({
            "has_notification": True,
            "message": msg,
            "audio_url": audio_url
        })
        
    return jsonify({"has_notification": False})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
