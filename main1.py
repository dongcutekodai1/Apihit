import json
import threading
import time
import os
import logging
from urllib.request import urlopen, Request
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HOST = '0.0.0.0'
POLL_INTERVAL = 5
RETRY_DELAY = 5
MAX_HISTORY = 50

lock_md5 = threading.Lock()

latest_md5 = {
    "Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
    "Tong": 0, "Ket_qua": "Chưa có", "id": "truongdong1920",
    "Du_doan": "—", "thoi_gian": ""
}
history_md5 = []
last_sid_md5 = None

# thống kê dự đoán
stats = {
    "total": 0,
    "correct": 0,
    "wrong": 0
}

# --------------------------
def get_tai_xiu(d1, d2, d3):
    total = d1 + d2 + d3
    return "Xỉu" if total <= 10 else "Tài"

# --------------------------
def ai_predict(history):
    if not history or len(history) < 3:
        return "Tài" if time.time() % 2 == 0 else "Xỉu"

    recent = [h["Ket_qua"] for h in history[:15]][::-1]
    totals = [h.get("Tong", 0) for h in history[:15]][::-1]

    streak = 1
    last = recent[-1]
    for r in reversed(recent[:-1]):
        if r == last:
            streak += 1
        else:
            break

    tai_score, xiu_score = 0.0, 0.0

    # Trend balance
    tai_count = recent.count("Tài")
    xiu_count = recent.count("Xỉu")
    if abs(tai_count - xiu_count) / len(recent) >= 0.25:
        if tai_count > xiu_count:
            xiu_score += 0.25
        else:
            tai_score += 0.25

    # Short pattern
    if len(recent) >= 4:
        if recent[-3:] == ["Tài", "Xỉu", "Tài"]:
            xiu_score += 0.3
        elif recent[-3:] == ["Xỉu", "Tài", "Xỉu"]:
            tai_score += 0.3

    # Mean deviation
    if totals:
        avg_score = sum(totals) / len(totals)
        if avg_score > 10:
            tai_score += 0.2
        elif avg_score < 8:
            xiu_score += 0.2

    # Streak logic
    if streak >= 6:
        if last == "Tài":
            xiu_score += 0.35
        else:
            tai_score += 0.35
    elif streak >= 4:
        if last == "Tài":
            tai_score += 0.15
        else:
            xiu_score += 0.15

    # Normalize
    total_score = tai_score + xiu_score
    if total_score > 0:
        tai_score /= total_score
        xiu_score /= total_score

    # Random nếu cân bằng
    if abs(tai_score - xiu_score) < 0.15:
        return "Tài" if time.time() % 2 == 0 else "Xỉu"

    return "Tài" if tai_score > xiu_score else "Xỉu"

# --------------------------
def update_result(store, history, lock, result):
    global stats
    with lock:
        # dự đoán cho phiên hiện tại
        prediction = ai_predict(history)
        result["Du_doan"] = prediction
        result["thoi_gian"] = time.strftime("%H:%M:%S %d/%m/%Y")

        # kiểm tra dự đoán của phiên trước
        if history:
            prev = history[0]
            if prev.get("Du_doan") in ("Tài", "Xỉu"):
                stats["total"] += 1
                if prev["Du_doan"] == result["Ket_qua"]:
                    stats["correct"] += 1
                else:
                    stats["wrong"] += 1

        # cập nhật data
        store.clear()
        store.update(result)
        history.insert(0, result.copy())
        if len(history) > MAX_HISTORY:
            history.pop()

# --------------------------
def poll_md5():
    global last_sid_md5
    url = "https://jakpotgwab.geightdors.net/glms/v1/notify/taixiu?platform_id=g8&gid=vgmn_101"
    while True:
        try:
            req = Request(url, headers={'User-Agent': 'Python-Proxy/1.0'})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 'OK' and isinstance(data.get('data'), list):
                for game in data['data']:
                    if game.get("cmd") == 2006:
                        sid = game.get("sid")
                        d1, d2, d3 = game.get("d1"), game.get("d2"), game.get("d3")
                        if sid and sid != last_sid_md5 and None not in (d1, d2, d3):
                            last_sid_md5 = sid
                            total = d1 + d2 + d3
                            ket_qua = get_tai_xiu(d1, d2, d3)
                            result = {
                                "Phien": sid,
                                "Xuc_xac_1": d1,
                                "Xuc_xac_2": d2,
                                "Xuc_xac_3": d3,
                                "Tong": total,
                                "Ket_qua": ket_qua,
                                "id": "truongdong1920"
                            }
                            update_result(latest_md5, history_md5, lock_md5, result)
                            logger.info(f"[MD5] Phiên {sid} - KQ: {ket_qua}, Dự đoán: {result['Du_doan']}")
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu MD5: {e}")
            time.sleep(RETRY_DELAY)
        time.sleep(POLL_INTERVAL)

# --------------------------
app = Flask(__name__)

@app.route("/api/md5", methods=["GET"])
def get_md5():
    with lock_md5:
        return jsonify(latest_md5)

@app.route("/api/history", methods=["GET"])
def get_history():
    with lock_md5:
        return jsonify({
            "taixiumd5": history_md5,
            "stats": stats
        })

@app.route("/api/dudoan_md5", methods=["GET"])
def get_dudoan_md5():
    with lock_md5:
        data = latest_md5.copy()
    return jsonify({
        "current": data,
        "stats": stats
    })

@app.route("/")
def index():
    return "API Server running. Endpoints: /api/md5, /api/history, /api/dudoan_md5"

if __name__ == "__main__":
    logger.info("Khởi động hệ thống API Tài Xỉu MD5...")
    thread_md5 = threading.Thread(target=poll_md5, daemon=True)
    thread_md5.start()
    logger.info("Đã bắt đầu polling dữ liệu MD5.")
    port = int(os.environ.get("PORT", 8000))
    app.run(host=HOST, port=port)
