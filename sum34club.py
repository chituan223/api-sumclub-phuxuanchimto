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
USER_ID = "VIP_PRO_ANALYST_2025" # Cập nhật ID

# Biến toàn cục lưu trữ kết quả mới nhất và lịch sử
latest_result = {"phien": None, "xucxac": [], "tong": None, "ketqua": None, "du_doan": None, "do_tin_cay": None}
# history: chuỗi "Tài" / "Xỉu"
# totals: chuỗi tổng điểm xúc xắc (3-18)
history, totals = [], [] 

# ================== 20 CHIẾN LƯỢC DỰ ĐOÁN VIP PRO (NON-RANDOM) ==================

# 1. PHÂN TÍCH CẦU BỆT DÀI (Long Streak Breaker - Cực kỳ quan trọng)
def ai1_long_streak_breaker(history, totals):
    if len(history) < 6: return {"du_doan": "Tài", "do_tin_cay": 65.0}
    last_result = history[-1]
    streak_count = 0
    for i in range(len(history)-1, -1, -1):
        if history[i] == last_result: streak_count += 1
        else: break
    
    # Nếu bệt 5 lần trở lên, dự đoán đảo chiều với độ tin cậy cao
    if streak_count >= 5:
        prediction = "Xỉu" if last_result == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 95.5}
    
    # Nếu bệt 3-4 lần, tiếp tục bệt (theo trend)
    if streak_count >= 3:
        return {"du_doan": last_result, "do_tin_cay": 88.0}
        
    return {"du_doan": last_result, "do_tin_cay": 70.0}

# 2. SÓNG NHỊP ĐIỆU 3-2-1 (Rhythm Wave 3-2-1)
def ai2_rhythm_wave_3_2_1(history, totals):
    if len(history) < 6: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    tail = history[-6:]
    # Ví dụ: TTTXXT, dự đoán X
    if tail[0]==tail[1]==tail[2] and tail[3]==tail[4] and tail[5]!=tail[4]:
        prediction = "Xỉu" if tail[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 92.0}
    
    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 3. ĐẢO CHIỀU TẦN SUẤT 15 PHIÊN (15-Round Frequency Reversal)
def ai3_frequency_reversal_15(history, totals):
    if len(history) < 15: return {"du_doan": "Xỉu", "do_tin_cay": 62.0}
    
    last_15 = history[-15:]
    tai_count = last_15.count("Tài")
    xiu_count = 15 - tai_count
    
    # Nếu một bên chiếm quá 2/3 (10/15), dự đoán đảo chiều
    if tai_count >= 11:
        return {"du_doan": "Xỉu", "do_tin_cay": 93.5}
    if xiu_count >= 11:
        return {"du_doan": "Tài", "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 73.0}

# 4. PHÂN TÍCH TỔNG LẺ/CHẴN (Odd/Even Sum Parity)
def ai4_parity_pattern(history, totals):
    if len(totals) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    parity = [(t % 2) for t in totals[-5:]] # 0=Chẵn, 1=Lẻ
    
    # Nếu có mô hình 2 chẵn, 2 lẻ, 1 chẵn/lẻ (00110 hoặc 11001), dự đoán tiếp tục luân phiên
    if parity[-4:] == [0, 0, 1, 1]:
        return {"du_doan": "Tài" if totals[-1] < 11 else "Xỉu", "do_tin_cay": 80.0}
    if parity[-4:] == [1, 1, 0, 0]:
        return {"du_doan": "Tài" if totals[-1] < 11 else "Xỉu", "do_tin_cay": 85.0}

    # Nếu đang luân phiên (1010 hoặc 0101), dự đoán tiếp theo
    if parity[-4:] == [1, 0, 1, 0] or parity[-4:] == [0, 1, 0, 1]:
        next_parity = 1 if parity[-1] == 0 else 0
        return {"du_doan": "Tài" if next_parity == 1 else "Xỉu", "do_tin_cay": 88.5}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 5. ĐỘ LỆCH TỔNG TRUNG BÌNH 8 PHIÊN (8-Round Mean Deviation)
def ai5_mean_deviation_8(history, totals):
    if len(totals) < 8: return {"du_doan": "Xỉu", "do_tin_cay": 61.0}
    
    avg_sum_8 = statistics.mean(totals[-8:])
    # Mức cân bằng lý thuyết là 10.5
    
    if avg_sum_8 > 11.5: # Tổng đang quá cao
        return {"du_doan": "Xỉu", "do_tin_cay": 90.0}
    if avg_sum_8 < 9.5: # Tổng đang quá thấp
        return {"du_doan": "Tài", "do_tin_cay": 92.5}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 6. BƯỚC NHẢY TỔNG LỚN (Giant Sum Jump Detector)
def ai6_giant_sum_jump(history, totals):
    if len(totals) < 2: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    diff = totals[-1] - totals[-2]
    
    # Nếu tổng thay đổi quá lớn (>= 6 điểm)
    if abs(diff) >= 6:
        # Dự đoán ngược lại để "hồi quy" về trung bình (T or X)
        if totals[-1] >= 11:
             return {"du_doan": "Xỉu", "do_tin_cay": 90.5}
        else:
             return {"du_doan": "Tài", "do_tin_cay": 90.5}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 7. PHÂN TÍCH LUÂN PHIÊN KÉP 6 PHIÊN (Double Alternating 6)
def ai7_double_alternating_6(history, totals):
    if len(history) < 6: return {"du_doan": "Tài", "do_tin_cay": 62.0}
    
    # Tìm kiếm mô hình luân phiên: TXXTXX hoặc XTTXTT
    tail = "".join(h[0] for h in history[-6:])
    
    if tail in ["TXXTXX", "XTTXTT"]:
        prediction = "Tài" if tail[-1] == "X" else "Xỉu"
        return {"du_doan": prediction, "do_tin_cay": 91.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 8. ĐUÔI CÂN BẰNG 10 (Balance Tail 10)
def ai8_balance_tail_10(history, totals):
    if len(history) < 10: return {"du_doan": "Xỉu", "do_tin_cay": 63.0}
    
    last_10 = history[-10:]
    tai_count = last_10.count("Tài")
    
    # Nếu 10 phiên vừa qua cân bằng (5T/5X) và kết quả cuối là T/X, dự đoán tiếp tục luân phiên
    if tai_count == 5:
        prediction = "Xỉu" if history[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 94.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 9. DỰ ĐOÁN TỪ KẾT QUẢ ĐẶC BIỆT (Special Result Trigger - Bạc Nhớ)
def ai9_special_result_trigger(history, totals):
    if not totals: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_total = totals[-1]
    
    # Bạc nhớ: Tổng 4 hoặc Tổng 17 (Cực hiếm) -> Dự đoán ngược chiều
    if last_total in [4, 17]:
        prediction = "Xỉu" if last_total == 17 else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 96.0}

    # Tổng 10 (Pivot Point) -> Dự đoán Tài (theo xu hướng thị trường)
    if last_total == 10:
        return {"du_doan": "Tài", "do_tin_cay": 85.0}
        
    # Tổng 11 (Pivot Point) -> Dự đoán Xỉu (theo xu hướng thị trường)
    if last_total == 11:
        return {"du_doan": "Xỉu", "do_tin_cay": 85.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 10. PHÂN TÍCH ĐỘ LỆCH VÀO TRUNG TÂM (Deviation to Center - 10.5)
def ai10_deviation_to_center(history, totals):
    if len(totals) < 5: return {"du_doan": "Tài", "do_tin_cay": 61.0}
    
    # Tính độ lệch tích lũy so với 10.5
    deviation_sum = sum(t - 10.5 for t in totals[-5:])
    
    if deviation_sum > 4.0: # Lệch dương mạnh (Tổng cao) -> Kéo về Xỉu
        return {"du_doan": "Xỉu", "do_tin_cay": 91.5}
    if deviation_sum < -4.0: # Lệch âm mạnh (Tổng thấp) -> Kéo về Tài
        return {"du_doan": "Tài", "do_tin_cay": 91.5}
        
    return {"du_doan": history[-1], "do_tin_cay": 74.0}

# 11. MÔ HÌNH HỒI QUY NGẮN 3 PHIÊN (3-Round Short Regression)
def ai11_short_regression_3(history, totals):
    if len(history) < 3: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Ví dụ: TXT -> Dự đoán X (để lấp đầy chuỗi luân phiên)
    if history[-3:] == ["Tài", "Xỉu", "Tài"]:
        return {"du_doan": "Xỉu", "do_tin_cay": 90.0}
    # Ví dụ: XTX -> Dự đoán T
    if history[-3:] == ["Xỉu", "Tài", "Xỉu"]:
        return {"du_doan": "Tài", "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 12. PHÂN TÍCH VÙNG BIÊN (Boundary Zone Analysis)
def ai12_boundary_zone_analysis(history, totals):
    if not totals: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_total = totals[-1]
    
    # Vùng Tài Cao (15+) -> Cực kỳ hiếm, dự đoán đảo chiều Xỉu
    if last_total >= 15:
        return {"du_doan": "Xỉu", "do_tin_cay": 98.0}
    
    # Vùng Xỉu Thấp (6-) -> Cực kỳ hiếm, dự đoán đảo chiều Tài
    if last_total <= 6:
        return {"du_doan": "Tài", "do_tin_cay": 98.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 72.0}

# 13. MÔ HÌNH GƯƠNG LẬP KÉP 5 PHIÊN (Dual Mirror 5 Pattern)
def ai13_dual_mirror_5(history, totals):
    if len(history) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm mô hình đối xứng: TXXXT, XTTTX
    tail = history[-5:]
    if tail[0] == tail[-1] and tail[1] == tail[-2] and tail[1] != tail[0]:
        # Ví dụ TXXXT: Dự đoán X
        prediction = "Xỉu" if tail[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 93.0}

    return {"du_doan": history[-1], "do_tin_cay": 71.0}

# 14. PHÂN TÍCH SÓNG TỔNG 4 PHIÊN (4-Round Sum Wave Analysis)
def ai14_sum_wave_analysis(history, totals):
    if len(totals) < 4: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm chuỗi Tăng - Giảm - Tăng (hoặc ngược lại)
    # 1: Tăng, -1: Giảm, 0: Bằng
    trend = [math.copysign(1, totals[i] - totals[i-1]) for i in range(len(totals)-3, len(totals))]
    
    if trend == [1, -1, 1]: # Tăng, Giảm, Tăng -> Dự đoán Giảm (Hồi quy)
        return {"du_doan": "Xỉu" if totals[-1] >= 11 else "Tài", "do_tin_cay": 88.0}
    if trend == [-1, 1, -1]: # Giảm, Tăng, Giảm -> Dự đoán Tăng (Hồi quy)
        return {"du_doan": "Tài" if totals[-1] <= 10 else "Xỉu", "do_tin_cay": 88.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 15. DỰ ĐOÁN XÁC SUẤT NGẮN HẠN 6 PHIÊN (Short-Term Probability 6)
def ai15_short_term_prob_6(history, totals):
    if len(history) < 6: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_6 = history[-6:]
    tai_count = last_6.count("Tài")
    xiu_count = 6 - tai_count
    
    # Dự đoán bên ít xuất hiện hơn trong 6 phiên gần nhất
    if tai_count > xiu_count:
        return {"du_doan": "Xỉu", "do_tin_cay": 87.0}
    if xiu_count > tai_count:
        return {"du_doan": "Tài", "do_tin_cay": 87.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 75.0} # Nếu cân bằng, giữ nguyên trend

# 16. MÔ HÌNH 4-1-4 ĐỐI XỨNG (4-1-4 Symmetry Model)
def ai16_symmetry_4_1_4(history, totals):
    if len(history) < 9: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm 4 bên này, 1 bên kia, 4 bên này: TTTT X TTTT
    tail = history[-9:]
    
    if tail[0:4] == [tail[0]]*4 and tail[4] != tail[0] and tail[5:] == [tail[0]]*4:
        # Nếu mô hình được lấp đầy, dự đoán đảo chiều mạnh
        prediction = "Xỉu" if tail[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 97.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 17. ĐỘ RỘNG BIÊN ĐỘ TỔNG 10 PHIÊN (10-Round Amplitude Range)
def ai17_amplitude_range_10(history, totals):
    if len(totals) < 10: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_10 = totals[-10:]
    amplitude = max(last_10) - min(last_10)
    
    # Nếu biên độ rộng (>= 8 điểm), thị trường biến động mạnh -> dự đoán hồi quy về 10.5
    if amplitude >= 8:
        prediction = "Xỉu" if totals[-1] >= 11 else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 89.0}
        
    # Nếu biên độ hẹp (<= 3 điểm), thị trường ổn định -> dự đoán tiếp tục trend
    if amplitude <= 3:
        return {"du_doan": history[-1], "do_tin_cay": 87.5}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 18. ĐẢO LẶP KHÓA 5 PHIÊN (Locked Alternating Reversal 5)
def ai18_locked_alternating_5(history, totals):
    if len(history) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm luân phiên hoàn hảo: TXTXT hoặc XTXTX
    tail = "".join(h[0] for h in history[-5:])
    
    if tail == "TXTXT" or tail == "XTXTX":
        # Nếu luân phiên hoàn hảo 5 lần, dự đoán đảo chiều (phá cầu)
        prediction = "Xỉu" if tail[-1] == "T" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 96.5}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 19. XU HƯỚNG TỔNG DỊCH CHUYỂN (Sum Shift Trend)
def ai19_sum_shift_trend(history, totals):
    if len(totals) < 4: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tấn công (Attack) hay Phòng thủ (Defend)
    # Tấn công (Tài): 11 -> 12 -> 13 -> ?
    if totals[-3:] == [totals[-2] - 1, totals[-2], totals[-2] + 1] and totals[-1] >= 11:
        return {"du_doan": "Tài", "do_tin_cay": 90.0}
    # Phòng thủ (Xỉu): 10 -> 9 -> 8 -> ?
    if totals[-3:] == [totals[-2] + 1, totals[-2], totals[-2] - 1] and totals[-1] <= 10:
        return {"du_doan": "Xỉu", "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 73.0}

# 20. PHÂN TÍCH ĐIỂM CHẠM 10 VÀ 11 (Pivot Contact Analysis)
def ai20_pivot_contact_analysis(history, totals):
    if len(totals) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_5 = totals[-5:]
    
    # Đang chạm 10 (Biên Xỉu) liên tục -> Dự đoán Tài để thoát biên
    if last_5.count(10) >= 3:
        return {"du_doan": "Tài", "do_tin_cay": 94.0}
        
    # Đang chạm 11 (Biên Tài) liên tục -> Dự đoán Xỉu để thoát biên
    if last_5.count(11) >= 3:
        return {"du_doan": "Xỉu", "do_tin_cay": 94.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}


# ================== DANH SÁCH THUẬT TOÁN ĐÃ CẬP NHẬT ==================
# Tất cả 20 thuật toán mới đều nhận 2 đối số (history, totals)
algos = [
    ai1_long_streak_breaker, ai2_rhythm_wave_3_2_1, ai3_frequency_reversal_15,
    ai4_parity_pattern, ai5_mean_deviation_8, ai6_giant_sum_jump,
    ai7_double_alternating_6, ai8_balance_tail_10, ai9_special_result_trigger,
    ai10_deviation_to_center, ai11_short_regression_3, ai12_boundary_zone_analysis,
    ai13_dual_mirror_5, ai14_sum_wave_analysis, ai15_short_term_prob_6,
    ai16_symmetry_4_1_4, ai17_amplitude_range_10, ai18_locked_alternating_5,
    ai19_sum_shift_trend, ai20_pivot_contact_analysis
]


# ================== TỔNG HỢP DỰ ĐOÁN CUỐI CÙNG ==================
def ai_predict(history, totals):
    results = []
    
    # Chạy tất cả 20 thuật toán VIP
    for fn in algos:
        try:
            # Tất cả thuật toán mới đều chuẩn hóa nhận 2 đối số: history và totals
            pred = fn(history, totals)
            results.append(pred)
        except Exception as e:
            # Ghi log nếu có lỗi trong thuật toán nhưng không dừng chương trình
            logging.warning(f"Lỗi trong thuật toán {fn.__name__}: {e}")
            continue
            
    if not results:
        return {"du_doan": "Tài", "do_tin_cay": 60.0} # Dự đoán mặc định thấp

    # Tổng hợp dự đoán: Tính điểm Tài/Xỉu dựa trên độ tin cậy
    tai_score = sum(r["do_tin_cay"] for r in results if r["du_doan"] == "Tài")
    xiu_score = sum(r["do_tin_cay"] for r in results if r["du_doan"] == "Xỉu")
    
    # Quyết định cuối cùng
    du_doan = "Tài" if tai_score > xiu_score else "Xỉu"
    
    # Tính độ tin cậy trung bình
    total_score = tai_score + xiu_score
    if total_score == 0:
        avg_conf = 60.0
    else:
        max_score = max(tai_score, xiu_score)
        avg_conf = round((max_score / total_score) * 100, 1) # Độ tin cậy dựa trên tỷ lệ phiếu bầu trọng số

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
                    if res["Dice1"] == -1: return
                    
                    dice = [res["Dice1"],res["Dice2"],res["Dice3"]]
                    tong = sum(dice)
                    ketqua = "Tài" if tong>=11 else "Xỉu"
                    phien_id = info["SessionID"]

                    # Chỉ cập nhật lịch sử khi có phiên mới (phòng trường hợp nhận tin nhắn cũ)
                    if not history or phien_id > latest_result["phien"]:
                        history.append(ketqua)
                        totals.append(tong)
                        if len(history)>200: 
                            history.pop(0)
                            totals.pop(0)
                        
                        pred = ai_predict(history, totals)
                        latest_result = {"phien": phien_id,"xucxac":dice,"tong":tong,"ketqua":ketqua,"du_doan":pred["du_doan"],"do_tin_cay":pred["do_tin_cay"]}
                        logging.info(f"🎯 Phiên {phien_id} | {dice} -> {ketqua} | Dự đoán tiếp: {pred['du_doan']} ({pred['do_tin_cay']}%)")
                        
        except Exception as e:
            logging.error(f"Lỗi Xử Lý Tin Nhắn WS: {e}")

    # Cần thêm on_error và on_close để tự động kết nối lại
    def on_error(ws, error):
        logging.error(f"Lỗi WebSocket: {error}")
        
    def on_close(ws, close_status_code, close_msg):
        logging.warning("WebSocket đóng kết nối. Tự động kết nối lại sau 5s...")
        time.sleep(5)
        # Bằng cách để main_loop gọi run_forever, nó sẽ tự động chạy lại.

    ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()


# ================== CHU TRÌNH CHÍNH ==================
def main_loop():
    while True:
        try:
            # Vòng lặp này đảm bảo WebSocket luôn cố gắng kết nối lại
            connect_ws(get_connection_token())
        except Exception as e:
            logging.error("Lỗi MAIN LOOP: %s", e)
            time.sleep(5)


# ================== API HIỂN THỊ KẾT QUẢ ==================
@app.route("/api/taimd5", methods=["GET"])
def api_taimd5():
    # Thêm thông tin lịch sử ngắn gọn để người dùng theo dõi
    response_data = latest_result.copy()
    response_data["history_last_5"] = history[-5:]
    response_data["totals_last_5"] = totals[-5:]
    
    if not latest_result["phien"]:
        return jsonify({"status": "waiting for first result", "message": "Đang chờ kết quả phiên đầu tiên từ WebSocket..."})
        
    return jsonify(response_data)


# ================== KHỞI ĐỘNG HỆ THỐNG ==================
if __name__ == "__main__":
    logging.info("🚀 Khởi động Flask + Hệ thống Phân tích 20 VIP PRO...")
    
    # Khởi động thread WebSocket để chạy nền
    threading.Thread(target=main_loop, daemon=True).start()
    
    # Chạy Flask app để phục vụ API
    app.run(host="0.0.0.0", port=3000)
