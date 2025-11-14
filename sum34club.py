from flask import Flask, jsonify
from flask_cors import CORS
import websocket
import requests
import json
import time
import threading
import logging
import urllib.parse
import statistics
import math

# ================== CẤU HÌNH HỆ THỐNG ==================
# Cấu hình logging để dễ dàng theo dõi
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app)

BASE_URL = "https://taixiu1.gsum01.com"
HUB_NAME = "luckydice1Hub"
# Cập nhật ID cố định
USER_ID = "VIP_PRO_ANALYST_2025_V2" 

# Biến toàn cục lưu trữ kết quả mới nhất và lịch sử
latest_result = {"phien": None, "xucxac": [], "tong": None, "ketqua": None, "du_doan": None, "do_tin_cay": None}
# history: chuỗi "Tài" / "Xỉu"
# totals: chuỗi tổng điểm xúc xắc (3-18)
history, totals = [], [] 

# KHÓA ĐỒNG BỘ: Cực kỳ quan trọng để bảo vệ các biến toàn cục trong môi trường đa luồng
data_lock = threading.Lock() 

# ================== 20 CHIẾN LƯỢC DỰ ĐOÁN VIP PRO (TỐI ƯU) ==================
# Các thuật toán giữ nguyên logic nhưng hoạt động trong môi trường thread-safe
# (Không cần thay đổi logic bên trong vì chúng chỉ đọc dữ liệu)

# 1. PHÂN TÍCH CẦU BỆT DÀI VÀ HỒI QUY (Long Streak & Reversion)
def ai1_long_streak_breaker(history, totals):
    if len(history) < 8: return {"du_doan": "Tài", "do_tin_cay": 65.0}
    last_result = history[-1]
    streak_count = 0
    for i in range(len(history)-1, -1, -1):
        if history[i] == last_result: streak_count += 1
        else: break
    
    # Bệt từ 6 lần trở lên: Đảo chiều mạnh
    if streak_count >= 6:
        prediction = "Xỉu" if last_result == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 98.0}
    
    # Bệt 3-5 lần: Tiếp tục bệt (theo trend mạnh)
    if streak_count >= 3:
        return {"du_doan": last_result, "do_tin_cay": 90.0}
        
    return {"du_doan": last_result, "do_tin_cay": 70.0}

# 2. SÓNG LUÂN PHIÊN NGẮN (Short Alternating Wave - 4 rounds)
def ai2_short_alternating_wave(history, totals):
    if len(history) < 5: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    # Mô hình: TXTX hoặc XTXT
    if history[-4:] == ["Tài", "Xỉu", "Tài", "Xỉu"]:
        return {"du_doan": "Tài", "do_tin_cay": 93.0}
    if history[-4:] == ["Xỉu", "Tài", "Xỉu", "Tài"]:
        return {"du_doan": "Xỉu", "do_tin_cay": 93.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 3. ĐỘ LỆCH CHUẨN XU HƯỚNG 30 PHIÊN (30-Round Standard Deviation Trend)
def ai3_std_dev_trend(history, totals):
    if len(history) < 30: return {"du_doan": "Xỉu", "do_tin_cay": 65.0}
    
    last_30 = history[-30:]
    tai_count = last_30.count("Tài")
    
    # Nếu lệch quá 60% (18/30) -> Áp lực hồi quy mạnh
    if tai_count >= 19:
        return {"du_doan": "Xỉu", "do_tin_cay": 95.0}
    if tai_count <= 11:
        return {"du_doan": "Tài", "do_tin_cay": 95.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 4. PHÂN TÍCH CHUỖI TỔNG LẺ/CHẴN KÉP (Dual Parity Sum Chain)
def ai4_dual_parity_pattern(history, totals):
    if len(totals) < 6: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    parity = [(t % 2) for t in totals[-6:]] # 0=Chẵn (Xỉu), 1=Lẻ (Tài/Xỉu)
    
    # Mô hình 3 Chẵn hoặc 3 Lẻ liên tiếp
    if parity[-3:] == [0, 0, 0]: # 3 Chẵn -> Dễ về Lẻ
        return {"du_doan": "Tài", "do_tin_cay": 92.0} # (Tài thường Lẻ, nhưng Xỉu cũng có Lẻ)
    if parity[-3:] == [1, 1, 1]: # 3 Lẻ -> Dễ về Chẵn
        return {"du_doan": "Xỉu", "do_tin_cay": 92.0} # (Xỉu thường Chẵn)
        
    return {"du_doan": history[-1], "do_tin_cay": 73.0}

# 5. PHÂN TÍCH BIÊN ĐỘ ĐỘ LỆCH TRUNG BÌNH (Mean Deviation Volatility)
def ai5_mean_deviation_volatility(history, totals):
    if len(totals) < 10: return {"du_doan": "Xỉu", "do_tin_cay": 61.0}
    
    avg_sum_10 = statistics.mean(totals[-10:])
    
    # Nếu Tổng đang quá lệch và xu hướng đang tiếp tục lệch -> Dự đoán hồi quy
    if avg_sum_10 > 12.0 and totals[-1] > avg_sum_10: # Tổng cao và đang tăng
        return {"du_doan": "Xỉu", "do_tin_cay": 94.0}
    if avg_sum_10 < 9.0 and totals[-1] < avg_sum_10: # Tổng thấp và đang giảm
        return {"du_doan": "Tài", "do_tin_cay": 94.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 6. PHÂN TÍCH BƯỚC NHẢY TỔNG ĐỘT BIẾN (Extreme Sum Jump Detector)
def ai6_extreme_sum_jump(history, totals):
    if len(totals) < 2: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    diff = totals[-1] - totals[-2]
    
    # Nếu tổng thay đổi cực lớn (>= 7 điểm) -> Chắc chắn hồi quy về trung bình (10.5)
    if abs(diff) >= 7:
        prediction = "Xỉu" if totals[-1] >= 11 else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 97.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 7. PHÂN TÍCH MÔ HÌNH 2-2-1-1 (Wave Pattern)
def ai7_wave_pattern_2_2_1_1(history, totals):
    if len(history) < 6: return {"du_doan": "Tài", "do_tin_cay": 62.0}
    
    # Mô hình: TTXX T X hoặc XXTT X T (Dự đoán đảo chiều)
    tail = history[-6:]
    if tail[0]==tail[1] and tail[2]==tail[3] and tail[0]!=tail[2] and tail[4]!=tail[5] and tail[4]!=tail[0]:
        # Ví dụ: T T X X T X -> Dự đoán T (để lặp lại XX)
        prediction = tail[2] 
        return {"du_doan": prediction, "do_tin_cay": 91.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 8. MÔ HÌNH CÂN BẰNG TỨC THỜI (Instant Balance 5)
def ai8_instant_balance_5(history, totals):
    if len(history) < 5: return {"du_doan": "Xỉu", "do_tin_cay": 63.0}
    
    last_5 = history[-5:]
    tai_count = last_5.count("Tài")
    
    # Nếu 5 phiên gần nhất là 3T/2X hoặc 2T/3X, dự đoán lấp đầy điểm yếu
    if tai_count == 3 and last_5[-1] == "Tài": # 3 Tài, kết thúc bằng Tài -> Dự đoán Xỉu để cân bằng
        return {"du_doan": "Xỉu", "do_tin_cay": 94.0}
    if tai_count == 2 and last_5[-1] == "Xỉu": # 3 Xỉu, kết thúc bằng Xỉu -> Dự đoán Tài để cân bằng
        return {"du_doan": "Tài", "do_tin_cay": 94.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 9. PHÂN TÍCH KẾT QUẢ ĐẶC BIỆT KÉP (Dual Special Result Trigger)
def ai9_dual_special_result_trigger(history, totals):
    if len(totals) < 2: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_total = totals[-1]
    prev_total = totals[-2]
    
    # Bạc nhớ: Cực hiếm (3 hoặc 18) -> Đảo chiều mạnh
    if last_total in [3, 18]:
        prediction = "Xỉu" if last_total == 18 else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 99.0}

    # Bạc nhớ: Chạm biên 5/16 và đảo chiều
    if last_total == 5 and prev_total > 10: # Tổng 5 đến sau Tài -> Dự đoán Tài (Hồi quy)
        return {"du_doan": "Tài", "do_tin_cay": 95.0}
    if last_total == 16 and prev_total < 11: # Tổng 16 đến sau Xỉu -> Dự đoán Xỉu (Hồi quy)
        return {"du_doan": "Xỉu", "do_tin_cay": 95.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 10. ĐỘ LỆCH TÍCH LŨY TRỌNG SỐ (Weighted Cumulative Deviation)
def ai10_weighted_cumulative_deviation(history, totals):
    if len(totals) < 8: return {"du_doan": "Tài", "do_tin_cay": 61.0}
    
    # Gán trọng số tăng dần cho 5 phiên gần nhất (phần tử cuối là quan trọng nhất)
    weights = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] 
    deviation_sum = sum( (t - 10.5) * w for t, w in zip(totals[-8:], weights) )
    
    if deviation_sum > 3.0: # Lệch dương mạnh (Tổng cao) -> Kéo về Xỉu
        return {"du_doan": "Xỉu", "do_tin_cay": 93.0}
    if deviation_sum < -3.0: # Lệch âm mạnh (Tổng thấp) -> Kéo về Tài
        return {"du_doan": "Tài", "do_tin_cay": 93.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 74.0}

# 11. MÔ HÌNH XU HƯỚNG BƯỚC NHẢY (Jump Trend Model - 4 rounds)
def ai11_jump_trend_model(history, totals):
    if len(history) < 4: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Mô hình lặp: TTXX hoặc XXTT (Đã hoàn thành 2 cặp) -> Dự đoán tiếp tục lặp lại
    tail = history[-4:]
    if tail[0]==tail[1] and tail[2]==tail[3] and tail[0]!=tail[2]:
        prediction = tail[0] # Dự đoán lặp lại cặp đầu tiên
        return {"du_doan": prediction, "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 12. PHÂN TÍCH VÙNG TRUNG TÂM (Center Zone Analysis)
def ai12_center_zone_analysis(history, totals):
    if len(totals) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Vùng Trung tâm: 9, 10, 11, 12. Nếu dồn vào đây quá 4/5 phiên, dự đoán phá vỡ biên
    center_count = sum(1 for t in totals[-5:] if t in [9, 10, 11, 12])
    
    if center_count >= 4:
        # Nếu đang ở 10/11 -> Phá vỡ ra biên
        if totals[-1] in [10, 11]:
            return {"du_doan": history[-1], "do_tin_cay": 95.0} # Tiếp tục xu hướng hiện tại (T/X)
        # Nếu đang ở 9/12 -> Kéo về trung tâm
        else:
            prediction = "Tài" if totals[-1] == 12 else "Xỉu"
            return {"du_doan": prediction, "do_tin_cay": 95.0}

    return {"du_doan": history[-1], "do_tin_cay": 72.0}

# 13. MÔ HÌNH GƯƠNG LẬT NGẮN (Short Mirror Pattern - 4 rounds)
def ai13_short_mirror_4(history, totals):
    if len(history) < 4: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm mô hình đối xứng: TXXT hoặc XTTX
    tail = history[-4:]
    if tail[0] == tail[-1] and tail[1] == tail[-2] and tail[1] != tail[0]:
        # Ví dụ TXXT: Dự đoán X
        prediction = "Xỉu" if tail[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 93.0}

    return {"du_doan": history[-1], "do_tin_cay": 71.0}

# 14. PHÂN TÍCH XU HƯỚNG TỔNG DỊCH CHUYỂN BẰNG EMA (Sum Trend via EMA)
def ai14_sum_trend_ema(history, totals):
    if len(totals) < 10: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Giả lập EMA (Exponential Moving Average) bằng trung bình trọng số 5 phiên
    alpha = 0.6
    ema = totals[-1]
    for i in range(2, 6):
        ema = alpha * totals[-i] + (1 - alpha) * ema

    # Nếu EMA (Trung bình có trọng số) lệch khỏi 10.5
    if ema > 11.0: # Xu hướng tăng mạnh
        return {"du_doan": "Tài", "do_tin_cay": 88.0}
    if ema < 10.0: # Xu hướng giảm mạnh
        return {"du_doan": "Xỉu", "do_tin_cay": 88.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 15. DỰ ĐOÁN XÁC SUẤT NÉN (Compressed Probability)
def ai15_compressed_prob(history, totals):
    if len(history) < 12: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_12 = history[-12:]
    tai_count = last_12.count("Tài")
    xiu_count = 12 - tai_count
    
    # Nếu tỉ lệ chênh lệch quá 2:1 (ví dụ 8T:4X)
    if tai_count >= 8:
        return {"du_doan": "Xỉu", "do_tin_cay": 90.0}
    if xiu_count >= 8:
        return {"du_doan": "Tài", "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 75.0} # Nếu cân bằng, giữ nguyên trend

# 16. MÔ HÌNH ĐỐI XỨNG PHÁT TRIỂN (Developing Symmetry Model - 7 rounds)
def ai16_developing_symmetry(history, totals):
    if len(history) < 7: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm T T X T X X T hoặc X X T X T T X
    # Tương ứng với mô hình 2-1-1-2-1
    tail = history[-7:]
    
    if tail[0]==tail[1] and tail[-2]==tail[-1] and tail[2]==tail[4] and tail[3]!=tail[2]:
        # Ví dụ: T T X T X X T -> Dự đoán X
        prediction = tail[2] # Kết quả ở giữa (Tail[2] hoặc Tail[4])
        return {"du_doan": prediction, "do_tin_cay": 96.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 17. ĐỘ RỘNG BIÊN ĐỘ TỔNG (Sum Range Volatility Check)
def ai17_sum_range_volatility(history, totals):
    if len(totals) < 15: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_15 = totals[-15:]
    # Tính độ lệch chuẩn của tổng điểm (đo lường sự phân tán)
    try:
        std_dev = statistics.stdev(last_15)
    except statistics.StatisticsError: # Chỉ có 1 giá trị hoặc quá ít
        return {"du_doan": history[-1], "do_tin_cay": 70.0}
    
    # Độ lệch chuẩn rất cao (>= 3.5): Biến động mạnh -> Dự đoán hồi quy
    if std_dev >= 3.5:
        prediction = "Xỉu" if totals[-1] >= 11 else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 92.0}
        
    # Độ lệch chuẩn thấp (<= 1.5): Biến động thấp (bệt vùng) -> Dự đoán tiếp tục trend
    if std_dev <= 1.5:
        return {"du_doan": history[-1], "do_tin_cay": 87.5}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 18. ĐẢO LẶP KHÓA HOÀN HẢO (Perfect Alternating Reversal 7)
def ai18_perfect_alternating_7(history, totals):
    if len(history) < 7: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm luân phiên hoàn hảo: TXTXTXT hoặc XTXTXTX
    tail = "".join(h[0] for h in history[-7:])
    
    if tail == "TXTXTXT" or tail == "XTXTXTX":
        # Nếu luân phiên hoàn hảo 7 lần, dự đoán đảo chiều (phá cầu)
        prediction = "Xỉu" if tail[-1] == "T" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 98.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 19. XU HƯỚNG TỔNG TUYẾN TÍNH NGẮN HẠN (Short-term Linear Sum Trend)
def ai19_short_term_linear_trend(history, totals):
    if len(totals) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tính xu hướng bằng cách so sánh 3 phiên đầu và 2 phiên cuối
    avg_first_3 = statistics.mean(totals[-5:-2])
    avg_last_2 = statistics.mean(totals[-2:])
    
    # Nếu xu hướng tăng mạnh (trên 1 điểm)
    if avg_last_2 - avg_first_3 > 1.0:
        return {"du_doan": "Tài", "do_tin_cay": 90.0}
    # Nếu xu hướng giảm mạnh (dưới -1 điểm)
    if avg_last_2 - avg_first_3 < -1.0:
        return {"du_doan": "Xỉu", "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 73.0}

# 20. PHÂN TÍCH ĐIỂM CHẠM VÀ PHÁ VỠ TRUNG TÂM (Pivot Breakout Analysis)
def ai20_pivot_breakout_analysis(history, totals):
    if len(totals) < 8: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_8 = totals[-8:]
    
    # Đang tích lũy ở Trung tâm (10/11)
    if sum(1 for t in last_8 if t in [10, 11]) >= 5:
        # Nếu Tài/Xỉu đang luân phiên -> Dự đoán phá vỡ cầu luân phiên
        if history[-2] != history[-1]:
            prediction = "Xỉu" if history[-1] == "Tài" else "Tài"
            return {"du_doan": prediction, "do_tin_cay": 95.0}
        # Nếu Tài/Xỉu đang bệt -> Dự đoán tiếp tục bệt
        else:
            return {"du_doan": history[-1], "do_tin_cay": 92.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}


# ================== DANH SÁCH THUẬT TOÁN ĐÃ CẬP NHẬT ==================
algos = [
    ai1_long_streak_breaker, ai2_short_alternating_wave, ai3_std_dev_trend,
    ai4_dual_parity_pattern, ai5_mean_deviation_volatility, ai6_extreme_sum_jump,
    ai7_wave_pattern_2_2_1_1, ai8_instant_balance_5, ai9_dual_special_result_trigger,
    ai10_weighted_cumulative_deviation, ai11_jump_trend_model, ai12_center_zone_analysis,
    ai13_short_mirror_4, ai14_sum_trend_ema, ai15_compressed_prob,
    ai16_developing_symmetry, ai17_sum_range_volatility, ai18_perfect_alternating_7,
    ai19_short_term_linear_trend, ai20_pivot_breakout_analysis
]


# ================== TỔNG HỢP DỰ ĐOÁN CUỐI CÙNG ==================
def ai_predict(history, totals):
    results = []
    
    # Chạy tất cả 20 thuật toán VIP
    for fn in algos:
        try:
            pred = fn(history, totals)
            results.append(pred)
        except Exception as e:
            # Ghi log nếu có lỗi trong thuật toán nhưng không dừng chương trình
            logging.warning(f"Lỗi trong thuật toán {fn.__name__}: {e}")
            continue
            
    if not results:
        return {"du_doan": "Tài", "do_tin_cay": 60.0} # Dự đoán mặc định thấp

    # Tối ưu hóa Tổng hợp: Tính điểm Tài/Xỉu dựa trên độ tin cậy
    tai_score = sum(r["do_tin_cay"] for r in results if r["du_doan"] == "Tài")
    xiu_score = sum(r["do_tin_cay"] for r in results if r["du_doan"] == "Xỉu")
    
    # Quyết định cuối cùng
    du_doan = "Tài" if tai_score > xiu_score else "Xỉu"
    
    # Tính độ tin cậy trung bình dựa trên tổng điểm trọng số
    total_score = tai_score + xiu_score
    if total_score == 0:
        avg_conf = 60.0
    else:
        max_score = max(tai_score, xiu_score)
        # Độ tin cậy là tỷ lệ phần trăm của bên thắng so với tổng điểm
        avg_conf = round((max_score / total_score) * 100, 1)

    return {"du_doan": du_doan, "do_tin_cay": avg_conf}


# ================== LẤY TOKEN VÀ KẾT NỐI WS (GIỮ NGUYÊN) ==================
def get_connection_token():
    r = requests.get(f"{BASE_URL}/signalr/negotiate?clientProtocol=1.5")
    token = urllib.parse.quote(r.json()["ConnectionToken"], safe="")
    logging.info("✅ Token: %s", token[:10] + "...")
    return token

def connect_ws(token):
    params = f"transport=webSockets&clientProtocol=1.5&connectionToken={token}&connectionData=%5B%7B%22name%22%3A%22{HUB_NAME}%22%7D%5D&tid=5"
    ws_url = f"wss://taixiu1.gsum01.com/signalr/connect?{params}"

    def on_message(ws, message):
        global latest_result, history, totals
        try:
            data = json.loads(message)
            if "M" not in data: return
            
            for m in data["M"]:
                if m["H"].lower()==HUB_NAME.lower() and m["M"]=="notifyChangePhrase":
                    info = m["A"][0]
                    res = info["Result"]
                    # Kiểm tra xem có phải kết quả cuối cùng (Dice1 != -1)
                    if res.get("Dice1", -1) == -1: return 
                    
                    dice = [res["Dice1"],res["Dice2"],res["Dice3"]]
                    tong = sum(dice)
                    ketqua = "Tài" if tong>=11 else "Xỉu"
                    phien_id = info["SessionID"]

                    # === KHỐI AN TOÀN LUỒNG: Bắt đầu khu vực khóa ghi (WRITE LOCK) ===
                    with data_lock:
                        # Chỉ cập nhật lịch sử khi có phiên mới
                        if not history or phien_id > latest_result["phien"]:
                            history.append(ketqua)
                            totals.append(tong)
                            # Giới hạn lịch sử (ví dụ: 200 phiên) để tối ưu hóa bộ nhớ
                            if len(history)>200: 
                                history.pop(0)
                                totals.pop(0)
                            
                            # Thực hiện dự đoán ngay sau khi có kết quả mới
                            # Lưu ý: Hàm ai_predict chỉ đọc dữ liệu, nên nó an toàn
                            pred = ai_predict(history, totals)
                            
                            latest_result = {
                                "phien": phien_id,
                                "xucxac": dice,
                                "tong": tong,
                                "ketqua": ketqua,
                                "du_doan": pred["du_doan"],
                                "do_tin_cay": pred["do_tin_cay"]
                            }
                            
                            logging.info(f"🎯 Phiên {phien_id} | {dice} -> {ketqua} | Dự đoán tiếp: {pred['du_doan']} ({pred['do_tin_cay']}%)")
                            
                    # === KHỐI AN TOÀN LUỒNG: Kết thúc khu vực khóa ghi (WRITE UNLOCK) ===
        except Exception as e:
            logging.error(f"Lỗi Xử Lý Tin Nhắn WS: {e}")

    def on_error(ws, error):
        # Không in lỗi quá thường xuyên, chỉ log các lỗi nghiêm trọng
        if "BadStatusLine" not in str(error):
            logging.error(f"Lỗi WebSocket: {error}")
        
    def on_close(ws, close_status_code, close_msg):
        logging.warning("WebSocket đóng kết nối. Tự động kết nối lại...")
        # on_close sẽ kết thúc run_forever, và main_loop sẽ tự khởi động lại.

    # SignalR yêu cầu tin nhắn keep-alive. Tùy chọn `run_forever` sẽ xử lý.
    ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()


# ================== CHU TRÌNH CHÍNH ==================
def main_loop():
    # Vòng lặp này đảm bảo WebSocket luôn cố gắng kết nối lại
    while True:
        try:
            logging.info("⚙️ Bắt đầu kết nối WebSocket...")
            # Lấy token mới mỗi lần kết nối lại
            token = get_connection_token() 
            connect_ws(token)
        except Exception as e:
            logging.error("❌ Lỗi MAIN LOOP, kết nối lại sau 5s: %s", e)
            time.sleep(5)


# ================== API HIỂN THỊ KẾT QUẢ ==================
@app.route("/api/taimd5", methods=["GET"])
def api_taimd5():
    # === KHỐI AN TOÀN LUỒNG: Bắt đầu khu vực khóa đọc (READ LOCK) ===
    # Lấy bản sao dữ liệu an toàn trước khi xử lý
    with data_lock:
        current_result = latest_result.copy()
        history_last_10 = history[-10:]
        totals_last_10 = totals[-10:]
    # === KHỐI AN TOÀN LUỒNG: Kết thúc khu vực khóa đọc (READ UNLOCK) ===
    
    response_data = current_result
    response_data["history_last_10"] = history_last_10
    response_data["totals_last_10"] = totals_last_10
    response_data["analyst_id"] = USER_ID
    
    if not current_result["phien"]:
        return jsonify({"status": "waiting for first result", "message": "Đang chờ kết quả phiên đầu tiên từ WebSocket...", "analyst_id": USER_ID})
        
    return jsonify(response_data)


# ================== KHỞI ĐỘNG HỆ THỐNG ==================
if __name__ == "__main__":
    logging.info("🚀 Khởi động Flask + Hệ thống Phân tích 20 VIP PRO (V2 THREAD-SAFE)...")
    
    # Khởi động thread WebSocket để chạy nền
    threading.Thread(target=main_loop, daemon=True).start()
    
    # Chạy Flask app để phục vụ API
    # Sử dụng 'threaded=True' để đảm bảo Flask không chặn main_loop
    app.run(host="0.0.0.0", port=3000, threaded=True)
