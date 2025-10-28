from flask import Flask, jsonify
from flask_cors import CORS
import websocket
import requests
import json
import time
import threading
import logging
import urllib.parse

# ================== CẤU HÌNH ==================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app)

BASE_URL = "https://taixiu1.gsum01.com"
HUB_NAME = "luckydice1Hub"
USER_ID = "phuxuanchimto"

latest_result = {
    "phien": None,
    "xucxac": [],
    "tong": None,
    "ketqua": None,
    "thoigian": None
}

history = []  # lưu lịch sử Tài/Xỉu


# ================== CÁC THUẬT TOÁN DỰ ĐOÁN ==================
def algo_weighted_recent(history):
    if not history: return "Tài"
    t = sum((i+1)/len(history) for i,v in enumerate(history) if v=="Tài")
    x = sum((i+1)/len(history) for i,v in enumerate(history) if v=="Xỉu")
    return "Tài" if t >= x else "Xỉu"

def algo_long_chain_reverse(history, k=3):
    if not history: return "Tài"
    last = history[-1]; chain = 1
    for v in reversed(history[:-1]):
        if v == last: chain += 1
        else: break
    if chain >= k: return "Xỉu" if last=="Tài" else "Tài"
    return last

def algo_alternation(history):
    if len(history) < 4: return "Tài"
    flips = sum(1 for i in range(1, 4) if history[-i] != history[-i-1])
    if flips >= 3: return "Xỉu" if history[-1]=="Tài" else "Tài"
    return history[-1]

def algo_window_majority(history, window=6):
    win = history[-window:]
    if not win: return "Tài"
    return "Tài" if win.count("Tài") >= len(win)/2 else "Xỉu"

def algo_momentum(history):
    if len(history) < 2: return "Tài"
    score = sum(1 if history[i]==history[i-1] else -1 for i in range(1, len(history)))
    return history[-1] if score > 0 else ("Xỉu" if history[-1]=="Tài" else "Tài")

def algo_volatility(history):
    if len(history) < 5: return "Tài"
    flips = sum(1 for i in range(1, len(history)) if history[i]!=history[i-1])
    ratio = flips / len(history)
    return "Xỉu" if ratio > 0.55 and history[-1]=="Tài" else ("Tài" if ratio > 0.55 else history[-1])

def algo_pattern_repeat(history):
    L = len(history)
    if L < 6: return "Tài"
    for length in range(2, min(6, L//2)+1):
        a = "".join(history[-length:])
        b = "".join(history[-2*length:-length])
        if a == b:
            return "Tài" if history[-length]=="Tài" else "Xỉu"
    return algo_window_majority(history,5)

def algo_entropy(history):
    if not history: return "Tài"
    t = history.count("Tài"); x = len(history) - t
    diff = abs(t - x)
    if diff <= len(history)//5:
        return "Xỉu" if history[-1]=="Tài" else "Tài"
    return "Tài" if t > x else "Xỉu"

def algo_parity_index(history):
    if len(history) < 4: return "Tài"
    t = sum(1 for i,v in enumerate(history) if v=="Tài" and i%2==0)
    x = sum(1 for i,v in enumerate(history) if v=="Xỉu" and i%2==1)
    return "Tài" if t >= x else "Xỉu"

def algo_hybrid(history):
    algos = [
        algo_weighted_recent, algo_long_chain_reverse, algo_alternation,
        algo_window_majority, algo_momentum, algo_volatility,
        algo_pattern_repeat, algo_entropy, algo_parity_index
    ]
    votes = [fn(history) for fn in algos]
    scoreT = votes.count("Tài")
    scoreX = votes.count("Xỉu")
    prediction = "Tài" if scoreT >= scoreX else "Xỉu"
    confidence = int(max(scoreT, scoreX) / len(votes) * 100)
    return {"prediction": prediction, "confidence": confidence}


# ================== LẤY TOKEN ==================
def get_connection_token():
    url = f"{BASE_URL}/signalr/negotiate?clientProtocol=1.5"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()
    token = urllib.parse.quote(data["ConnectionToken"], safe="")
    logging.info(f"✅ Lấy token thành công: {token[:10]}...")
    return token


# ================== KẾT NỐI WEBSOCKET ==================
def connect_ws(token):
    params = (
        f"transport=webSockets"
        f"&clientProtocol=1.5"
        f"&connectionToken={token}"
        f"&connectionData=%5B%7B%22name%22%3A%22{HUB_NAME}%22%7D%5D"
        f"&tid=5"
    )

    ws_url = f"wss://taixiu1.gsum01.com/signalr/connect?{params}"

    def on_open(ws):
        logging.info("✅ WS kết nối thành công — bắt đầu giữ kết nối...")
        def ping_loop():
            while True:
                time.sleep(30)
                try:
                    ws.send(json.dumps({"H": HUB_NAME, "M": "PingPong", "I": 1}))
                except Exception:
                    break
        threading.Thread(target=ping_loop, daemon=True).start()

    def on_message(ws, message):
        global latest_result, history
        try:
            data = json.loads(message)
            if "M" not in data:
                return
            for m in data["M"]:
                if m["H"].lower() == HUB_NAME.lower() and m["M"] == "notifyChangePhrase":
                    info = m["A"][0]
                    result = info["Result"]
                    session = info["SessionID"]

                    if result["Dice1"] == -1: return

                    dice1, dice2, dice3 = result["Dice1"], result["Dice2"], result["Dice3"]
                    tong = dice1 + dice2 + dice3
                    ketqua = "Tài" if tong >= 11 else "Xỉu"

                    history.append(ketqua)
                    if len(history) > 100: history = history[-100:]  # giữ 100 kết quả gần nhất

                    latest_result = {
                        "phien": session,
                        "xucxac": [dice1, dice2, dice3],
                        "tong": tong,
                        "ketqua": ketqua,
                        "thoigian": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                    pred = algo_hybrid(history)
                    logging.info(f"🎯 Phiên {session}: {dice1}-{dice2}-{dice3} (Tổng={tong} → {ketqua}) | Dự đoán tiếp: {pred['prediction']} ({pred['confidence']}%)")

        except Exception as e:
            logging.error(f"❌ Parse lỗi: {e} — raw: {message[:120]}")

    def on_error(ws, error):
        logging.error(f"⚠️ WS lỗi: {error}")

    def on_close(ws, *_):
        logging.warning("🔌 WS mất kết nối — thử lại sau 5s...")
        time.sleep(5)
        main_loop()

    ws = websocket.WebSocketApp(
        ws_url, on_open=on_open, on_message=on_message,
        on_error=on_error, on_close=on_close
    )
    ws.run_forever()


# ================== CHU TRÌNH CHÍNH ==================
def main_loop():
    while True:
        try:
            token = get_connection_token()
            connect_ws(token)
        except Exception as e:
            logging.error(f"💥 Lỗi chính: {e}")
            time.sleep(5)


# ================== API ENDPOINT ==================
@app.route("/api/taimd5", methods=["GET"])
def api_taimd5():
    if latest_result["phien"] is None:
        return jsonify({"status": "waiting", "message": "Chưa có kết quả nào được ghi nhận."})

    pred = algo_hybrid(history)
    return jsonify({
        "Phien": latest_result["phien"],
        "Xuc_xac_1": latest_result["xucxac"][0],
        "Xuc_xac_2": latest_result["xucxac"][1],
        "Xuc_xac_3": latest_result["xucxac"][2],
        "Tong": latest_result["tong"],
        "Ket_qua": latest_result["ketqua"],
        "Du_doan_tiep": pred["prediction"],
        "Do_tin_cay": pred["confidence"],
        "Id": USER_ID,
        "Thoi_gian": latest_result["thoigian"]
    })


# ================== KHỞI ĐỘNG ==================
def run_ws_thread():
    t = threading.Thread(target=main_loop, daemon=True)
    t.start()

if __name__ == "__main__":
    logging.info("🚀 Khởi động Flask API + WebSocket client 24/7...")
    run_ws_thread()
    app.run(host="0.0.0.0", port=3000)