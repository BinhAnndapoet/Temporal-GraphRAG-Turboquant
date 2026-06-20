import pandas as pd
import json

# Định nghĩa tên file đầu vào và đầu ra
input_file = "/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/predict_outputs/local_base_predictions_14B_Q5.jsonl"
output_excel = "/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/predict_outputs/local_base_predictions_14B_Q5_table.xlsx"
output_csv = "/home/guest/Projects/Research/Temporal-GraphRAG-Turboquant/results/predict_outputs/local_base_predictions_14B_Q5_table.csv"

# Khởi tạo danh sách để chứa dữ liệu lọc
filtered_data = []

# Đọc từng dòng của file JSONL
with open(input_file, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip(): # Bỏ qua dòng trống nếu có
            try:
                data = json.loads(line)
                
                # Trích xuất và chỉ giữ lại các trường bạn yêu cầu
                # Dùng .get() để tránh lỗi nếu một dòng nào đó bị thiếu trường
                item = {
                    "index": data.get("index"),
                    "question": data.get("question"),
                    "answer": data.get("answer"),
                    "prediction": data.get("prediction")
                }
                filtered_data.append(item)
            except json.JSONDecodeError as e:
                print(f"Lỗi đọc dòng: {e}")

# Chuyển đổi danh sách thành DataFrame (Dạng bảng của Pandas)
df = pd.DataFrame(filtered_data)

# Xuất dữ liệu ra các định dạng bảng
# 1. Xuất ra file Excel
df.to_excel(output_excel, index=False, engine='openpyxl')
print(f"Đã xuất file Excel thành công: {output_excel}")

# 2. Xuất ra file CSV (Dấu phân cách là dấu phẩy, hỗ trợ UTF-8 hiển thị tiếng Việt/ký tự đặc biệt)
df.to_csv(output_csv, index=False, encoding='utf-8-sig')
print(f"Đã xuất file CSV thành công: {output_csv}")

# Hiển thị bản xem trước của bảng ngay trên màn hình terminal
print("\n--- Bản xem trước dữ liệu dạng bảng ---")
print(df.head())