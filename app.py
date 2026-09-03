from datetime import datetime, timedelta
import json
import os
import certifi
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
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

# --- CẤU HÌNH GITHUB OAUTH (LẤY TỪ BIẾN MÔI TRƯỜNG) ---
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "Ov23liD2PKCxgNkZfUj5")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "158a74d6beed0ed201ad9a7c4a041738d3185eb6")
YOUR_GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "PinyinCode")


# --- HÀM ĐỌC CẤU HÌNH FIRMWARE TỪ FILE RIÊNG (firmware.json) ---
def get_firmware_config():
    try:
        if os.path.exists("firmware.json"):
            with open("firmware.json", "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Lỗi đọc file firmware.json: {e}")
    
    return {
        "latest_version": "v1.1.0",
        "firmware_url": "https://esp32-linkdownload.onrender.com/xiaozhi.bin",
        "changelog": "Cập nhật thành công."
    }


# --- HÀM CHUYỂN SỐ TIỀN THÀNH CHỮ TIẾNG VIỆT TỰ NHIÊN ---
def number_to_vietnamese_words(n):
    if n == 0:
        return "không đồng"
    
    units = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    
    def read_block(num):
        tram = num // 100
        chuc = (num % 100) // 10
        donvi = num % 10
        res = ""
        
        if tram > 0:
            res += units[tram] + " trăm "
            if chuc == 0 and donvi > 0:
                res += "lẻ "
        
        if chuc > 1:
            res += units[chuc] + " mươi "
            if donvi == 1:
                res += "mốt"
            elif donvi == 5:
                res += "lăm"
            elif donvi > 0:
                res += units[donvi]
        elif chuc == 1:
            res += "mười "
            if donvi == 5:
                res += "lăm"
            elif donvi > 0:
                res += units[donvi]
        elif chuc == 0 and tram > 0 and donvi > 0:
            res += units[donvi]
        elif chuc == 0 and tram == 0 and donvi > 0:
            res += units[donvi]
            
        return res.strip()

    trieu = n // 1_000_000
    nghin = (n % 1_000_000) // 1_000
    tram_donvi = n % 1_000
    
    result = []
    
    if trieu > 0:
        result.append(read_block(trieu) + " triệu")
        
    if nghin > 0:
        if trieu > 0 and nghin < 100:
            result.append("không trăm " + read_block(nghin) + " nghìn" if nghin < 10 else read_block(nghin) + " nghìn")
        else:
            result.append(read_block(nghin) + " nghìn")
            
    if tram_donvi > 0:
        if (trieu > 0 or nghin > 0) and tram_donvi < 100:
            result.append("lẻ " + read_block(tram_donvi))
        else:
            result.append(read_block(tram_donvi))
            
    return " ".join(result).strip() + " đồng"


def get_device(chip_id):
    try:
        if devices_collection is not None and chip_id:
            doc = devices_collection.find_one({"_id": chip_id})
            if doc:
                ota_pending = doc.get("ota_pending", False)
                ota_requested_by = doc.get("ota_requested_by", "")
                ota_requested_at = doc.get("ota_requested_at", "")

                # Nếu là do NGƯỜI DÙNG bấm và quá 30 phút -> Tự động reset về false
                if ota_pending and ota_requested_by == "user" and ota_requested_at:
                    try:
                        requested_at = datetime.fromisoformat(ota_requested_at)
                        if datetime.utcnow() - requested_at > timedelta(minutes=30):
                            ota_pending = False
                            ota_requested_by = ""
                            ota_requested_at = ""
                            devices_collection.update_one(
                                {"_id": chip_id},
                                {
                                    "$set": {
                                        "ota_pending": False,
                                        "ota_requested_by": "",
                                        "ota_requested_at": "",
                                    }
                                },
                            )
                    except Exception:
                        pass

                return {
                    "chip_id": doc.get("_id", ""),
                    "username": doc.get("username", ""),
                    "status": doc.get("status", "active"),
                    "expires_at": doc.get("expires_at", ""),
                    "trial": doc.get("trial", False),
                    "ota_pending": ota_pending,
                    "ota_requested_by": ota_requested_by,
                    "ota_requested_at": ota_requested_at,
                    "created_at": doc.get("created_at", ""),
                    "sepay_secret": doc.get("sepay_secret", ""),
                    "notifications": doc.get("notifications", []),
                    "history_24h": doc.get("history_24h", []),
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


# --- ROUTE XÁC THỰC & ĐĂNG NHẬP ADMIN ---
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login")
def login():
    if "user" in session:
        return redirect(url_for("admin_panel"))
    return render_template("login.html")


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
    return render_template("admin.html", devices=load_db(), user=session["user"])


@app.route("/admin/add", methods=["POST"])
def admin_add():
    if "user" not in session:
        return redirect(url_for("login"))

    chip_id = request.form.get("chip_id", "").strip()
    username = request.form.get("username", "").strip()[:20]
    expiry_date_str = request.form.get("expiry_date")

    import uuid

    if chip_id and expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            
            now = datetime.utcnow()
            status = "active" if now <= expiry_date else "expired"

            device = get_device(chip_id)
            sepay_secret = device.get("sepay_secret") if device and device.get("sepay_secret") else f"whsec_{uuid.uuid4().hex}"

            if device:
                device["expires_at"] = expiry_date.isoformat()
                if username: 
                    device["username"] = username
                device["status"] = status
                device["sepay_secret"] = sepay_secret
            else:
                device = {
                    "username": username,
                    "status": status,
                    "expires_at": expiry_date.isoformat(),
                    "trial": False,
                    "ota_pending": False,
                    "ota_requested_by": "",
                    "ota_requested_at": "",
                    "created_at": datetime.utcnow().isoformat(),
                    "sepay_secret": sepay_secret,
                    "notifications": [],
                    "history_24h": [],
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
    username = request.form.get("username", "").strip()[:20]
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
            
            now = datetime.utcnow()
            status = "active" if now <= expiry_date else "expired"

            device["expires_at"] = expiry_date.isoformat()
            device["status"] = status
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
        device["ota_requested_by"] = "admin"
        device["ota_requested_at"] = ""
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
        device["ota_requested_by"] = ""
        device["ota_requested_at"] = ""
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
    return render_template("user_portal.html")


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

    status = device_info.get("status", "active")
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

    if device_info.get("status") == "expired":
        return jsonify({"error": "Bản quyền thiết bị đã hết hạn!"}), 403

    device_info["ota_pending"] = True
    device_info["ota_requested_by"] = "user"
    device_info["ota_requested_at"] = datetime.utcnow().isoformat()
    save_device(chip_id, device_info)

    return jsonify({"success": True, "message": "Đã kích hoạt chế độ cập nhật OTA. Vui lòng khởi động lại thiết bị trong vòng 30 phút."})


# --- API DÀNH CHO ESP32 ---
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
            "ota_requested_by": "",
            "ota_requested_at": "",
            "created_at": now.isoformat(),
            "sepay_secret": f"whsec_{uuid.uuid4().hex}",
            "notifications": [],
            "history_24h": [],
        }
        save_device(chip_id, device_info)

    status = device_info.get("status", "active")

    if status == "expired":
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

    if device_info.get("status") == "expired":
        if device_info.get("ota_pending", False):
            device_info["ota_pending"] = False
            device_info["ota_requested_by"] = ""
            device_info["ota_requested_at"] = ""
            save_device(chip_id, device_info)
        return jsonify({"update_available": False, "message": "License expired. Update denied."})

    if device_info.get("ota_pending", False):
        device_info["ota_pending"] = False
        device_info["ota_requested_by"] = ""
        device_info["ota_requested_at"] = ""
        save_device(chip_id, device_info)

        fw_config = get_firmware_config()

        return jsonify(
            {
                "update_available": True,
                "latest_version": fw_config.get("latest_version"),
                "firmware_url": fw_config.get("firmware_url"),
                "changelog": fw_config.get("changelog"),
            }
        )

    return jsonify({"update_available": False})


# --- WEBHOOK NHẬN THÔNG BÁO TỪ SEPAY & LƯU LỊCH SỬ 24H ---
@app.route("/api/bank-webhook/<path:chip_id>", methods=["POST"])
def bank_webhook(chip_id):
    if devices_collection is None:
        return jsonify({"success": False, "error": "Database error"}), 500

    chip_id_clean = chip_id.strip()
    device = get_device(chip_id_clean)

    if not device:
        return jsonify({"success": False, "error": "Chip ID not registered in system"}), 404

    # Kiểm tra SePay Secret nếu có cấu hình bảo mật header
    auth_header = request.headers.get("Authorization", "")
    expected_secret = device.get("sepay_secret", "")
    if expected_secret and auth_header:
        token = auth_header.replace("Apikey ", "").replace("Bearer ", "").strip()
        if token and token != expected_secret:
            return jsonify({"success": False, "error": "Unauthorized webhook secret"}), 401

    data = request.get_json() or {}
    amount = data.get("transferAmount") or data.get("amount", 0)
    content = data.get("content", data.get("description", ""))

    if amount and float(amount) > 0:
        amount_int = int(float(amount))
        now_utc = datetime.utcnow()
        
        # Đọc số tiền thành chữ tự nhiên bằng tiếng Việt
        money_words = number_to_vietnamese_words(amount_int)
        audio_message = f"Tài khoản của bạn vừa nhận được {money_words}."

        if "notifications" not in device or not isinstance(device["notifications"], list):
            device["notifications"] = []
        if "history_24h" not in device or not isinstance(device["history_24h"], list):
            device["history_24h"] = []

        # 1. Thêm vào hàng đợi đọc loa
        device["notifications"].append(
            {
                "amount": amount_int,
                "message": audio_message,
                "content": content,
                "created_at": now_utc.isoformat(),
            }
        )

        # 2. Thêm vào lịch sử tổng hợp 24h
        device["history_24h"].append(
            {
                "amount": amount_int,
                "content": content,
                "created_at": now_utc.isoformat(),
            }
        )

        # 3. Tự động dọn dẹp các giao dịch cũ hơn 24 giờ
        cutoff_time = now_utc - timedelta(hours=24)
        device["history_24h"] = [
            item for item in device["history_24h"] 
            if datetime.fromisoformat(item["created_at"]) > cutoff_time
        ]

        save_device(chip_id_clean, device)
        return jsonify({"success": True, "message": "Saved notification and 24h history successfully"}), 200

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


# --- API TRA CỨU TỔNG NHẬN TRONG NGÀY (DÀNH CHO MCP) ---
@app.route("/api/stats/daily-total/<path:chip_id>", methods=["GET"])
def daily_total(chip_id):
    chip_id_clean = chip_id.strip()
    device = get_device(chip_id_clean)

    if not device:
        return jsonify({"success": False, "error": "Device not found"}), 404

    now_utc = datetime.utcnow()
    cutoff_time = now_utc - timedelta(hours=24)

    history_24h = device.get("history_24h", [])
    valid_transactions = []
    total_amount = 0

    for item in history_24h:
        try:
            tx_time = datetime.fromisoformat(item["created_at"])
            if tx_time > cutoff_time:
                valid_transactions.append(item)
                total_amount += item.get("amount", 0)
        except Exception:
            pass

    # Cập nhật lại mảng trong DB nếu có phần tử cũ tự động biến mất
    if len(valid_transactions) != len(history_24h):
        device["history_24h"] = valid_transactions
        save_device(chip_id_clean, device)

    return jsonify(
        {
            "success": True,
            "chip_id": chip_id_clean,
            "username": device.get("username", ""),
            "total_transactions_in_24h": len(valid_transactions),
            "total_amount_in_24h": total_amount,
            "formatted_total_amount": f"{total_amount:,} đồng",
            "transactions": valid_transactions,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
