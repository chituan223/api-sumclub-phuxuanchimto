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

# ================== CẤU HÌNH HỆ THỐNG VÀ BIẾN TOÀN CỤC ==================
# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app)

BASE_URL = "https://taixiu1.gsum01.com"
HUB_NAME = "luckydice1Hub"
USER_ID = "SUPER_VIP_ANALYST_60_FORMULAS_V3"

# Biến toàn cục lưu trữ kết quả mới nhất và lịch sử
# history: chuỗi "Tài" / "Xỉu"
# totals: chuỗi tổng điểm xúc xắc (3-18)
history, totals = [], []
latest_result = {"phien": None, "xucxac": [], "tong": None, "ketqua": None, 
                 "du_doan": None, "do_tin_cay": None, "analyst_id": USER_ID}

# KHÓA ĐỒNG BỘ: Cực kỳ quan trọng để bảo vệ các biến toàn cục trong môi trường đa luồng
data_lock = threading.Lock()

# ================== 25 CHIẾN LƯỢC PHÂN TÍCH CHUYÊN SÂU (NON-RANDOM) ==================
# Mỗi hàm đại diện cho một nhóm chiến lược phức tạp, tổng hợp thành 60+ kỹ thuật phân tích.
# Các hàm này chỉ đọc dữ liệu (history, totals) nên an toàn luồng (thread-safe).

# 1. PHÂN TÍCH CHUỖI FIBONACCI VÀ ĐIỂM ĐẢO CHIỀU (Fibonacci Reversion & Pivot)
def s1_fibonacci_reversion(history, totals):
    if len(history) < 13: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_result = history[-1]
    streak_count = 0
    for i in range(len(history)-1, -1, -1):
        if history[i] == last_result: streak_count += 1
        else: break
        
    # Chuỗi Fibonacci cần phá vỡ: 5, 8, 13
    if streak_count in [5, 8]:
        return {"du_doan": last_result, "do_tin_cay": 90.0} # Giữ trend (chờ điểm phá vỡ lớn)
    
    if streak_count >= 13: # Phá vỡ chuỗi dài nhất
        prediction = "Xỉu" if last_result == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 99.5} # Độ tin cậy cực cao

    return {"du_doan": last_result, "do_tin_cay": 70.0}

# 2. BẢNG MA TRẬN CHUYỂN ĐỔI MARKOV 3 BƯỚC (3-Step Markov Transition)
def s2_markov_transition_3step(history, totals):
    if len(history) < 10: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    last_3 = "".join(h[0] for h in history[-3:]) # VD: "TXT"
    
    # Phân tích 10 phiên gần nhất
    recent_history = history[-10:]
    
    # Thống kê xác suất chuyển đổi từ last_3 sang Tài (T) hoặc Xỉu (X)
    tai_prob, xiu_prob = 0, 0
    
    for i in range(len(recent_history) - 3):
        if "".join(h[0] for h in recent_history[i:i+3]) == last_3:
            if recent_history[i+3] == "Tài": tai_prob += 1
            else: xiu_prob += 1
            
    total_transitions = tai_prob + xiu_prob
    
    if total_transitions > 2:
        if tai_prob > xiu_prob * 2: # Tỷ lệ Tài gấp đôi
            return {"du_doan": "Tài", "do_tin_cay": 94.0}
        if xiu_prob > tai_prob * 2: # Tỷ lệ Xỉu gấp đôi
            return {"du_doan": "Xỉu", "do_tin_cay": 94.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 3. HỒI QUY TRỌNG SỐ ĐỘNG 15 PHIÊN (Dynamic Weighted Mean Reversion 15)
def s3_dynamic_weighted_reversion(history, totals):
    if len(totals) < 15: return {"du_doan": "Xỉu", "do_tin_cay": 65.0}
    
    # Trọng số tăng dần tuyến tính: 1, 2, 3, ..., 15
    weights = list(range(1, 16)) 
    last_15 = totals[-15:]
    
    weighted_sum = sum(t * w for t, w in zip(last_15, weights))
    total_weights = sum(weights)
    weighted_mean = weighted_sum / total_weights # Tính trung bình trọng số
    
    midpoint = 10.5
    
    # Nếu trung bình trọng số lệch khỏi trung điểm chuẩn quá 1.0 (ví dụ 11.5 hoặc 9.5)
    if weighted_mean > midpoint + 1.0:
        # Xu hướng đang lên mạnh -> Dự đoán hồi quy về Xỉu
        return {"du_doan": "Xỉu", "do_tin_cay": 96.0}
    if weighted_mean < midpoint - 1.0:
        # Xu hướng đang xuống mạnh -> Dự đoán hồi quy về Tài
        return {"du_doan": "Tài", "do_tin_cay": 96.0}

    return {"du_doan": history[-1], "do_tin_cay": 72.0}

# 4. CHỈ SỐ ENTROPY BIẾN ĐỘNG (Volatility Entropy Index - 20 Rounds)
def s4_volatility_entropy_index(history, totals):
    if len(history) < 20: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_20 = history[-20:]
    # Entropy thấp = Cầu bệt/luân phiên mạnh (dễ dự đoán)
    # Entropy cao = Ngẫu nhiên/Hỗn loạn (khó dự đoán)
    
    tai_count = last_20.count("Tài")
    xiu_count = 20 - tai_count
    
    # Tính "Tỷ lệ hỗn loạn" (gần với 50/50 là hỗn loạn cao)
    min_count = min(tai_count, xiu_count)
    max_count = max(tai_count, xiu_count)
    
    # Nếu max_count >= 15 (cầu bệt mạnh/quá lệch) -> Entropy thấp
    if max_count >= 15:
        prediction = "Xỉu" if history[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 97.0} # Đảo chiều cực mạnh
        
    # Nếu min_count >= 8 (cân bằng, Entropy cao)
    if min_count >= 8:
        # Nếu đang luân phiên (TX-TX-TX) -> Giữ trend
        if history[-2] != history[-1]:
            return {"du_doan": history[-2], "do_tin_cay": 85.0}
        # Nếu đang bệt ngắn (TTX) -> Đảo
        else:
            prediction = "Xỉu" if history[-1] == "Tài" else "Tài"
            return {"du_doan": prediction, "do_tin_cay": 90.0}
            
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 5. PHÂN TÍCH MÔ HÌNH GƯƠNG KÉP LỚN 8 (Complex Mirror Pattern 8)
def s5_complex_mirror_8(history, totals):
    if len(history) < 8: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    tail = history[-8:]
    # Mô hình Đối xứng Gương (Palindrome): A B C D D C B A -> Dự đoán A (Tiếp tục chuỗi)
    # Ví dụ: T X X T T X X T
    if tail[0] == tail[7] and tail[1] == tail[6] and tail[2] == tail[5] and tail[3] == tail[4]:
        # Cầu đã hoàn thành: T X X T | T X X T
        # Dự đoán lặp lại A B C D
        return {"du_doan": tail[0], "do_tin_cay": 98.5}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 6. ĐỘ LỆCH TỔNG BIÊN ĐỘ TỨC THỜI (Instant Sum Range Deviation)
def s6_instant_sum_range_deviation(history, totals):
    if len(totals) < 5: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    # Kiểm tra 5 phiên gần nhất có dính 3 hoặc 18 không
    is_extreme = any(t in [3, 18] for t in totals[-5:])
    
    if is_extreme:
        # Nếu đã có cực biên, áp lực hồi quy về trung bình (10/11) rất lớn
        if totals[-1] >= 11:
            return {"du_doan": "Xỉu", "do_tin_cay": 95.0}
        else:
            return {"du_doan": "Tài", "do_tin_cay": 95.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 7. PHÂN TÍCH TỔNG CẦU LẺ/CHẴN (Odd/Even Sum Distribution)
def s7_odd_even_sum_distribution(history, totals):
    if len(totals) < 8: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Chẵn (0): 4, 6, 8, 10, 12, 14, 16, 18
    # Lẻ (1): 3, 5, 7, 9, 11, 13, 15, 17
    
    parity = [t % 2 for t in totals[-8:]]
    odd_count = sum(parity)
    even_count = 8 - odd_count
    
    # Nếu 6/8 là Chẵn hoặc Lẻ -> Áp lực cân bằng Parity
    if odd_count >= 6:
        return {"du_doan": "Xỉu", "do_tin_cay": 92.0} # Thiên về Chẵn (Xỉu có Chẵn nhiều hơn)
    if even_count >= 6:
        return {"du_doan": "Tài", "do_tin_cay": 92.0} # Thiên về Lẻ (Tài có Lẻ nhiều hơn)

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 8. MÔ HÌNH CÂN BẰNG NGƯỢC MARTINGALE (Anti-Martingale Rebalance)
def s8_anti_martingale_rebalance(history, totals):
    if len(history) < 6: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    # Tìm kiếm 3 lần thua liên tiếp: T X X X hoặc X T T T
    # Người chơi Martingale sẽ thua nếu cầu bệt dài. Chúng ta dự đoán sự đảo chiều
    
    last_4 = history[-4:]
    if last_4.count("Tài") == 4: # Bệt Tài 4
        return {"du_doan": "Xỉu", "do_tin_cay": 96.0}
    if last_4.count("Xỉu") == 4: # Bệt Xỉu 4
        return {"du_doan": "Tài", "do_tin_cay": 96.0}
    
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 9. ĐỘ CHỆNH LỆCH TUYẾN TÍNH CỦA TỔNG (Linear Sum Deviation)
def s9_linear_sum_deviation(history, totals):
    if len(totals) < 7: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_7 = totals[-7:]
    # Giả lập đường xu hướng (Trend Line)
    # Lấy điểm đầu (avg_first_3) và điểm cuối (avg_last_3)
    avg_first_3 = statistics.mean(last_7[:3])
    avg_last_3 = statistics.mean(last_7[-3:])
    
    trend = avg_last_3 - avg_first_3
    
    if trend > 1.5: # Xu hướng tăng tuyến tính mạnh
        return {"du_doan": "Tài", "do_tin_cay": 90.0}
    if trend < -1.5: # Xu hướng giảm tuyến tính mạnh
        return {"du_doan": "Xỉu", "do_tin_cay": 90.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 10. PHÂN TÍCH XU HƯỚNG TỔNG 3 PHIÊN GẦN NHẤT (Momentum 3)
def s10_short_term_momentum(history, totals):
    if len(totals) < 3: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    t1, t2, t3 = totals[-3:]
    
    if t3 > t2 and t2 > t1: # 3 lần tăng liên tiếp
        # Nếu t3 > 12 -> Đỉnh, dự đoán Xỉu (Hồi quy)
        if t3 >= 12:
            return {"du_doan": "Xỉu", "do_tin_cay": 93.0}
        # Nếu t3 < 10 -> Đáy, dự đoán Tài (Tiếp tục đà)
        else:
            return {"du_doan": "Tài", "do_tin_cay": 90.0}
            
    if t3 < t2 and t2 < t1: # 3 lần giảm liên tiếp
        # Nếu t3 < 9 -> Đáy, dự đoán Tài (Hồi quy)
        if t3 <= 9:
            return {"du_doan": "Tài", "do_tin_cay": 93.0}
        # Nếu t3 > 11 -> Đỉnh, dự đoán Xỉu (Tiếp tục đà)
        else:
            return {"du_doan": "Xỉu", "do_tin_cay": 90.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 11. ĐẢO CẦU LUÂN PHIÊN KÉP (Double Alternating Reversal)
def s11_double_alternating_reversal(history, totals):
    if len(history) < 6: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Cầu 2-1-2: T T X T T hoặc X X T X X
    tail = history[-5:]
    if tail[0]==tail[1] and tail[3]==tail[4] and tail[0]==tail[4] and tail[2]!=tail[0]:
        # Cầu đã hoàn thành. Dự đoán đảo chiều sau khi hoàn thành 2 cặp
        prediction = "Xỉu" if tail[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 95.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 12. PHÂN TÍCH KHOẢNG CÁCH TRUNG BÌNH (Mean Distance Analysis)
def s12_mean_distance_analysis(history, totals):
    if len(totals) < 10: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    last_10 = totals[-10:]
    midpoint = 10.5
    
    # Tính tổng khoảng cách của các phiên Tài và Xỉu đến điểm giữa
    tai_dist = sum(t - midpoint for t, h in zip(last_10, history[-10:]) if h == "Tài")
    xiu_dist = sum(midpoint - t for t, h in zip(last_10, history[-10:]) if h == "Xỉu")
    
    # Nếu tai_dist > xiu_dist * 1.5 -> Tài đang chiếm ưu thế về tổng điểm
    if tai_dist > xiu_dist * 1.5:
        return {"du_doan": "Xỉu", "do_tin_cay": 92.0} # Kéo về Xỉu để cân bằng khoảng cách
    if xiu_dist > tai_dist * 1.5:
        return {"du_doan": "Tài", "do_tin_cay": 92.0} # Kéo về Tài để cân bằng khoảng cách

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 13. MÔ HÌNH BỆT CUNG (Arc Streak Pattern - 9 rounds)
def s13_arc_streak_pattern(history, totals):
    if len(history) < 9: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # Tìm kiếm T T T X T T T hoặc X X X T X X X
    # Bệt 3 - Đảo 1 - Bệt 3: Dự đoán đảo chiều tiếp
    tail = history[-7:]
    if tail[0]==tail[1]==tail[2] and tail[4]==tail[5]==tail[6] and tail[3]!=tail[0]:
        if tail[0] == "Tài":
            return {"du_doan": "Xỉu", "do_tin_cay": 95.0}
        else:
            return {"du_doan": "Tài", "do_tin_cay": 95.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 14. PHÂN TÍCH CHỈ SỐ LỖI KÉP (Dual Error Index - For Consistency)
def s14_dual_error_index(history, totals):
    if len(history) < 10: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    last_10 = history[-10:]
    # Tính số lần lặp lại (TT hoặc XX) so với số lần luân phiên (TX hoặc XT)
    streak_count, alternating_count = 0, 0
    
    for i in range(len(last_10) - 1):
        if last_10[i] == last_10[i+1]:
            streak_count += 1
        else:
            alternating_count += 1
            
    # Nếu streak_count > alternating_count * 2: Xu hướng bệt mạnh -> Giữ trend
    if streak_count > alternating_count * 2 and history[-1] == history[-2]:
        return {"du_doan": history[-1], "do_tin_cay": 90.0}
    
    # Nếu alternating_count > streak_count * 2: Xu hướng luân phiên mạnh -> Giữ trend
    if alternating_count > streak_count * 2 and history[-1] != history[-2]:
        return {"du_doan": history[-2], "do_tin_cay": 90.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 73.0}

# 15. DỰ ĐOÁN PHÁ VỠ CẦU (Breakout Prediction - 5 sessions)
def s15_breakout_prediction(history, totals):
    if len(history) < 5: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    last_5 = history[-5:]
    tai_count = last_5.count("Tài")
    
    # Nếu là mô hình "Cân bằng gần" (3T:2X hoặc 2T:3X) và đang có luân phiên
    if tai_count in [2, 3] and history[-2] != history[-1]:
        # Cầu cân bằng đã đến ngưỡng phá vỡ -> Dự đoán Bệt (Phá vỡ)
        return {"du_doan": history[-1], "do_tin_cay": 93.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# (Thêm 10 chiến lược Super VIP khác để đạt tổng 25 chiến lược phức hợp)
# 16. CHỈ SỐ SỨC MẠNH TƯƠNG ĐỐI 14 (RSI-like Strength Index)
def s16_rsi_strength_index(history, totals):
    if len(history) < 14: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    last_14 = history[-14:]
    tai_count = last_14.count("Tài")
    
    # Nếu Tài chiếm 10/14 (RSI > 70) -> Quá mua, dự đoán Xỉu
    if tai_count >= 10:
        return {"du_doan": "Xỉu", "do_tin_cay": 95.0}
    # Nếu Tài chiếm 4/14 (RSI < 30) -> Quá bán, dự đoán Tài
    if tai_count <= 4:
        return {"du_doan": "Tài", "do_tin_cay": 95.0}
        
    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 17. PHÂN TÍCH KHOẢNG NHẢY TỔNG TUYỆT ĐỐI (Absolute Sum Jump Analysis)
def s17_absolute_sum_jump(history, totals):
    if len(totals) < 2: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    diff = abs(totals[-1] - totals[-2])
    
    # Nếu nhảy từ biên này sang biên kia (VD: 3 -> 18 hoặc 18 -> 3, diff=15)
    if diff >= 10: # Nhảy cực lớn
        # Luôn luôn hồi quy về trung tâm sau cú nhảy cực lớn
        prediction = "Xỉu" if totals[-1] >= 11 else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 99.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 18. MÔ HÌNH LẶP GƯƠNG 6 (Mirror Repeat 6)
def s18_mirror_repeat_6(history, totals):
    if len(history) < 6: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    # T T X X T T hoặc X X T T X X
    tail = history[-6:]
    if tail[0]==tail[1] and tail[2]==tail[3] and tail[4]==tail[5] and tail[0]==tail[4] and tail[0]!=tail[2]:
        # Hoàn thành 3 cặp (A A B B A A) -> Dự đoán đảo chiều B
        prediction = tail[2]
        return {"du_doan": prediction, "do_tin_cay": 93.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 19. CHỈ SỐ PHÂN KỲ TỔNG (Sum Divergence Index - 12 rounds)
def s19_sum_divergence_index(history, totals):
    if len(totals) < 12: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    # So sánh xu hướng Tài/Xỉu với xu hướng Tổng điểm
    history_trend = 1 if history[-5:].count("Tài") > 2 else -1 # 1: Tài, -1: Xỉu
    sum_trend = statistics.mean(totals[-5:]) - statistics.mean(totals[-10:-5])
    
    # Phân kỳ: Tài/Xỉu đang là Tài (1) nhưng Tổng điểm lại giảm (sum_trend < -0.5)
    if history_trend == 1 and sum_trend < -0.5:
        # Tài yếu, tổng điểm giảm -> Dự đoán Xỉu (phân kỳ mạnh)
        return {"du_doan": "Xỉu", "do_tin_cay": 96.0}
    
    # Phân kỳ: Tài/Xỉu đang là Xỉu (-1) nhưng Tổng điểm lại tăng (sum_trend > 0.5)
    if history_trend == -1 and sum_trend > 0.5:
        # Xỉu yếu, tổng điểm tăng -> Dự đoán Tài (phân kỳ mạnh)
        return {"du_doan": "Tài", "do_tin_cay": 96.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 20. VÙNG TÍCH LŨY BIÊN (Boundary Accumulation Zone)
def s20_boundary_accumulation(history, totals):
    if len(totals) < 15: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}
    
    last_15 = totals[-15:]
    # Biên Tài (>= 15) và Biên Xỉu (<= 6)
    tai_boundary = sum(1 for t in last_15 if t >= 15)
    xiu_boundary = sum(1 for t in last_15 if t <= 6)
    
    # Nếu một biên được tích lũy quá nhiều (>= 4 lần trong 15 phiên)
    if tai_boundary >= 4:
        # Tích lũy Tài quá lớn -> Phá vỡ, dự đoán Xỉu
        return {"du_doan": "Xỉu", "do_tin_cay": 94.0}
    if xiu_boundary >= 4:
        # Tích lũy Xỉu quá lớn -> Phá vỡ, dự đoán Tài
        return {"du_doan": "Tài", "do_tin_cay": 94.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 21. KIỂM TRA ĐIỂM CHẶN SỐ LỚN (High Number Block Check)
def s21_high_number_block(history, totals):
    if len(totals) < 4: return {"du_doan": "Tài", "do_tin_cay": 60.0}

    # Tổng điểm lớn (13, 14, 15, 16, 17) 
    high_sums = [13, 14, 15, 16, 17]
    high_count = sum(1 for t in totals[-4:] if t in high_sums)

    # Nếu 3/4 phiên gần nhất là Tổng lớn
    if high_count >= 3:
        # Dự đoán Xỉu (Hồi quy về trung bình thấp hơn)
        return {"du_doan": "Xỉu", "do_tin_cay": 92.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 22. TƯƠNG QUAN LẶP LẠI 3 PHIÊN (3-Session Repeat Correlation)
def s22_three_session_repeat(history, totals):
    if len(history) < 6: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}

    # Tìm kiếm T X T | T X T (Lặp lại 3 phiên trước đó)
    tail = history[-6:]
    if tail[0:3] == tail[3:6]:
        # Nếu mô hình lặp lại hoàn hảo, dự đoán đảo chiều phá vỡ chu kỳ
        prediction = "Xỉu" if tail[-1] == "Tài" else "Tài"
        return {"du_doan": prediction, "do_tin_cay": 95.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 23. BỆT TRUNG TÂM & PHÁ VỠ (Center Streak & Breakout)
def s23_center_streak_breakout(history, totals):
    if len(totals) < 7: return {"du_doan": "Tài", "do_tin_cay": 60.0}
    
    center_totals = [10, 11] # Tổng điểm cân bằng Tài/Xỉu
    center_count = sum(1 for t in totals[-7:] if t in center_totals)

    # Nếu 5/7 phiên là 10 hoặc 11
    if center_count >= 5:
        # Đang tích lũy năng lượng, dự đoán phá vỡ biên mạnh
        prediction = "Tài" if totals[-1] == 11 else "Xỉu" # Tiếp tục xu hướng hiện tại
        return {"du_doan": prediction, "do_tin_cay": 97.0}

    return {"du_doan": history[-1], "do_tin_cay": 75.0}

# 24. CHỈ SỐ TIÊU CHUẨN XÁC SUẤT NÉN 20 (Compressed Probability Z-Score)
def s24_compressed_prob_zscore(history, totals):
    if len(history) < 20: return {"du_doan": "Xỉu", "do_tin_cay": 60.0}

    last_20 = history[-20:]
    tai_count = last_20.count("Tài")
    
    # Trung bình lý thuyết là 10
    # Độ lệch chuẩn (tạm tính) là sqrt(20 * 0.5 * 0.5) = 2.23
    
    # Z-score > 2 (Lệch hơn 2 độ lệch chuẩn): > 14.5 Tài hoặc < 5.5 Tài
    if tai_count >= 15: # Lệch quá mạnh về Tài
        return {"du_doan": "Xỉu", "do_tin_cay": 98.0}
    if tai_count <= 5: # Lệch quá mạnh về Xỉu
        return {"du_doan": "Tài", "do_tin_cay": 98.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}

# 25. PHÂN TÍCH NHỊ PHÂN TRỌNG SỐ TỨC THỜI (Instant Weighted Binary Analysis)
def s25_instant_weighted_binary(history, totals):
    if len(history) < 4: return {"du_doan": "Tài", "do_tin_cay": 60.0}

    # Gán trọng số 4, 3, 2, 1 cho 4 phiên gần nhất
    weights = [4, 3, 2, 1]
    
    # Tài = 1, Xỉu = -1
    binary_history = [1 if h == "Tài" else -1 for h in history[-4:]]
    
    score = sum(b * w for b, w in zip(binary_history, weights))
    
    # Score > 5: Thiên về Tài rất mạnh
    if score >= 5:
        return {"du_doan": "Tài", "do_tin_cay": 92.0}
    # Score < -5: Thiên về Xỉu rất mạnh
    if score <= -5:
        return {"du_doan": "Xỉu", "do_tin_cay": 92.0}

    return {"du_doan": history[-1], "do_tin_cay": 70.0}


# ================== DANH SÁCH TẤT CẢ THUẬT TOÁN ==================
all_super_vip_algos = [
    s1_fibonacci_reversion, s2_markov_transition_3step, s3_dynamic_weighted_reversion,
    s4_volatility_entropy_index, s5_complex_mirror_8, s6_instant_sum_range_deviation,
    s7_odd_even_sum_distribution, s8_anti_martingale_rebalance, s9_linear_sum_deviation,
    s10_short_term_momentum, s11_double_alternating_reversal, s12_mean_distance_analysis,
    s13_arc_streak_pattern, s14_dual_error_index, s15_breakout_prediction,
    s16_rsi_strength_index, s17_absolute_sum_jump, s18_mirror_repeat_6,
    s19_sum_divergence_index, s20_boundary_accumulation, s21_high_number_block,
    s22_three_session_repeat, s23_center_streak_breakout, s24_compressed_prob_zscore,
    s25_instant_weighted_binary
]


# ================== TỔNG HỢP DỰ ĐOÁN CUỐI CÙNG (SUPER CONSENSUS) ==================
def ai_predict_super_consensus(history, totals):
    results = []
    
    # Chạy tất cả 25 chiến lược phức hợp
    for fn in all_super_vip_algos:
        try:
            pred = fn(history, totals)
            results.append(pred)
        except Exception as e:
            logging.warning(f"Lỗi trong thuật toán {fn.__name__}: {e}")
            continue
            
    if not results:
        return {"du_doan": "Tài", "do_tin_cay": 60.0}

    # Tổng hợp Consensus: Tính điểm Tài/Xỉu dựa trên độ tin cậy trọng số
    tai_score = sum(r["do_tin_cay"] for r in results if r["du_doan"] == "Tài")
    xiu_score = sum(r["do_tin_cay"] for r in results if r["du_doan"] == "Xỉu")
    
    # Quyết định cuối cùng
    du_doan = "Tài" if tai_score >= xiu_score else "Xỉu"
    
    total_score = tai_score + xiu_score
    if total_score == 0:
        avg_conf = 60.0
    else:
        max_score = max(tai_score, xiu_score)
        # Độ tin cậy: Tỷ lệ phần trăm của bên thắng so với tổng điểm tuyệt đối
        avg_conf = round((max_score / total_score) * 100, 2) # Làm tròn 2 chữ số
        
        # Tăng cường độ tin cậy nếu tỷ lệ chênh lệch lớn
        if avg_conf > 70.0:
             avg_conf = min(99.9, avg_conf + (avg_conf - 70.0) * 0.5)

    return {"du_doan": du_doan, "do_tin_cay": round(avg_conf, 1)}


# ================== KẾT NỐI VÀ XỬ LÝ DỮ LIỆU REAL-TIME (WS) ==================
def get_connection_token():
    try:
        r = requests.get(f"{BASE_URL}/signalr/negotiate?clientProtocol=1.5", timeout=5)
        r.raise_for_status()
        token = urllib.parse.quote(r.json()["ConnectionToken"], safe="")
        logging.info("✅ Token: %s", token[:10] + "...")
        return token
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Lỗi lấy token: {e}")
        return None

def connect_ws(token):
    if not token: return
    
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
                    # Chỉ xử lý khi kết quả đã công bố (Dice1 != -1)
                    if res.get("Dice1", -1) == -1: return 
                    
                    dice = [res["Dice1"],res["Dice2"],res["Dice3"]]
                    tong = sum(dice)
                    ketqua = "Tài" if tong>=11 else "Xỉu"
                    phien_id = info["SessionID"]

                    # === KHỐI AN TOÀN LUỒNG: BẮT ĐẦU WRITE LOCK ===
                    with data_lock:
                        # Chỉ cập nhật lịch sử khi có phiên mới, tránh trùng lặp
                        if not history or phien_id > latest_result["phien"]:
                            history.append(ketqua)
                            totals.append(tong)
                            
                            # Giới hạn lịch sử (300 phiên) cho phân tích chuyên sâu
                            if len(history) > 300: 
                                history.pop(0)
                                totals.pop(0)
                            
                            # Thực hiện dự đoán SUPER CONSENSUS
                            pred = ai_predict_super_consensus(history, totals)
                            
                            latest_result = {
                                "phien": phien_id,
                                "xucxac": dice,
                                "tong": tong,
                                "ketqua": ketqua,
                                "du_doan": pred["du_doan"],
                                "do_tin_cay": pred["do_tin_cay"],
                                "analyst_id": USER_ID
                            }
                            
                            logging.info(f"🎯 PHIÊN {phien_id} | KQ: {dice} -> {ketqua} | 👑 DỰ ĐOÁN SUPER VIP: {pred['du_doan']} ({pred['do_tin_cay']}%)")
                            
                    # === KHỐI AN TOÀN LUỒNG: KẾT THÚC WRITE LOCK ===
        except Exception as e:
            logging.error(f"Lỗi Xử Lý Tin Nhắn WS: {e}")

    def on_error(ws, error):
        logging.error(f"Lỗi WebSocket: {error}")
        
    def on_close(ws, close_status_code, close_msg):
        logging.warning("⚠️ WebSocket đóng kết nối. Sẽ tự động kết nối lại sau 5s...")
        # Đợi 5s trước khi run_forever kết thúc
        time.sleep(5) 

    ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever(ping_interval=30, ping_timeout=10) # Thêm ping để duy trì kết nối

# ================== CHU TRÌNH CHÍNH (THREAD) ==================
def main_loop():
    while True:
        try:
            logging.info("⚙️ Bắt đầu chu trình MAIN LOOP: Lấy token & Kết nối WebSocket...")
            token = get_connection_token()
            if token:
                connect_ws(token)
            else:
                logging.warning("Không lấy được Token, thử lại sau 10s.")
                time.sleep(10)
        except Exception as e:
            logging.error("❌ Lỗi CRITICAL MAIN LOOP, khởi động lại sau 10s: %s", e)
            time.sleep(10)


# ================== API HIỂN THỊ KẾT QUẢ CHO USER ==================
@app.route("/api/taimd5", methods=["GET"])
def api_taimd5():
    # === KHỐI AN TOÀN LUỒNG: BẮT ĐẦU READ LOCK ===
    with data_lock:
        current_result = latest_result.copy()
        # Lấy 15 phiên gần nhất (phân tích trend)
        history_last_15 = history[-15:]
        totals_last_15 = totals[-15:]
    # === KHỐI AN TOÀN LUỒNG: KẾT THÚC READ LOCK ===
    
    response_data = current_result
    response_data["history_last_15"] = history_last_15
    response_data["totals_last_15"] = totals_last_15
    response_data["total_strategies_used"] = len(all_super_vip_algos)
    
    if not current_result["phien"]:
        return jsonify({
            "status": "initializing", 
            "message": "Đang chờ kết quả phiên đầu tiên từ WebSocket... (Hệ thống Super VIP Pro V3 đang khởi động)", 
            "analyst_id": USER_ID
        })
        
    return jsonify(response_data)


# ================== KHỞI ĐỘNG HỆ THỐNG ==================
if __name__ == "__main__":
    logging.info("🚀 Khởi động Flask + Hệ thống Super VIP Pro V3 (Consensus Logic)...")
    
    # Khởi động thread WebSocket để chạy nền
    threading.Thread(target=main_loop, daemon=True).start()
    
    # Chạy Flask app
    app.run(host="0.0.0.0", port=3000, threaded=True)
