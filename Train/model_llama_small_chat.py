import ollama
from typing import List, Dict
import re
import logging

logging.basicConfig(level=logging.INFO)

MODEL_NAME = "llama3.1:8b"

SYSTEM_PROMPT_FORMAT = (
    "Bạn là trợ lý AI Skemi. Hãy trả lời một cách tự nhiên và hữu ích như một người bạn, phù hợp với cấp độ câu hỏi đơn giản. "
    "TUYỆT ĐỐI không sử dụng bất kỳ định dạng Markdown hoặc ký tự đặc biệt nào như *, **, #, [], v.v. "
    "Chỉ trả về văn bản thuần. Yêu cầu về ngôn ngữ ĐẦU RA (Việt/Anh) phải được TUÂN THỦ NGHIÊM NGẶT từ các hướng dẫn trước đó."
)


def call_gemma__small_chat(messages: List[Dict[str, str]]):
    
    lang_system_prompt = next((m for m in messages if m['role'] == 'system'), None)
    
    full_messages = []
    
    # 1. Thêm System Prompt về Format/Tone
    full_messages.append({"role": "system", "content": SYSTEM_PROMPT_FORMAT})
    
    # 2. Thêm System Prompt về Ngôn ngữ (Ưu tiên cao)
    if lang_system_prompt:
        full_messages.append(lang_system_prompt)
        
    # 3. Thêm các tin nhắn lịch sử và tin nhắn User hiện tại
    full_messages.extend([m for m in messages if m['role'] != 'system'])

    try:
        logging.info(f"Calling Ollama Small: {MODEL_NAME} with {len(full_messages)} messages.")
        
        response = ollama.chat(
            model=MODEL_NAME,
            messages=full_messages,
            options={'temperature': 0.5}
        )

        text = getattr(response.message, "content", str(response))
        text = re.sub(r'[*_~`#]', '', text)
        return text.strip()

    except Exception as e:
        logging.error(f"Lỗi gọi model SMALL ({MODEL_NAME}): {e}")
        return "Xin lỗi, tôi không thể trả lời lúc này."
    

import time
import argparse 
import numpy as np # Cần để tính giá trị trung bình (average)

# ... (Giữ nguyên các hàm và định nghĩa ở trên) ...

def main():
    parser = argparse.ArgumentParser(description="Đo lường tốc độ suy luận của Ollama Chat Model.")
    parser.add_argument('--num_runs', type=int, default=5, help='Số lần chạy lặp lại để đo.')
    parser.add_argument('--prompt', type=str, default='Viết một câu chuyện ngắn về mèo và chuột.', help='Câu lệnh đầu vào để đo.')
    args = parser.parse_args()

    # --- Chuẩn bị Dữ liệu ---
    # Dữ liệu mẫu (sẽ được thêm vào sau System Prompt)
    test_messages = [
        {"role": "user", "content": args.prompt}
    ]

    total_times = []
    total_output_tokens = []

    print(f"\n--- BẮT ĐẦU ĐO LƯỜNG TỐC ĐỘ ---")
    print(f"Model: {MODEL_NAME}")
    print(f"Số lần lặp: {args.num_runs}\n")

    # 1. Làm nóng (Warm-up)
    # Lần chạy đầu tiên thường chậm hơn do cache và tải model
    print("Khởi động (Warm-up)...")
    call_gemma__small_chat(test_messages)
    print("Hoàn tất Warm-up.")

    # 2. Đo lường chính thức
    for i in range(args.num_runs):
        start_time = time.time()
        
        # Gọi hàm chat đã có sẵn của bạn
        response_text = call_gemma__small_chat(test_messages)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Đếm số token (giả định 1 từ xấp xỉ 1 token hoặc dùng thư viện tokenizer chính xác hơn)
        # Vì đây là mô hình ngôn ngữ, ta đo độ dài văn bản đầu ra.
        output_word_count = len(response_text.split()) 
        # Giả sử 1 token = 1 từ (để đơn giản)
        
        total_times.append(elapsed_time)
        total_output_tokens.append(output_word_count)

        logging.info(f"Lần {i+1}/{args.num_runs}: Thời gian = {elapsed_time:.3f}s. {output_word_count} tokens.")


    # --- Hiển thị Kết quả ---
    avg_latency = np.mean(total_times) * 1000 # Chuyển sang mili-giây (ms)
    avg_tokens = np.mean(total_output_tokens)
    total_time_sum = np.sum(total_times)
    
    # Tính Thông lượng (Tokens/giây)
    throughput_tokens_per_sec = np.sum(total_output_tokens) / total_time_sum

    print("\n-------------------------------------")
    print("✅ KẾT QUẢ TỐC ĐỘ SUY LUẬN (OLLAMA) ✅")
    print("-------------------------------------")
    print(f"  Thời gian trung bình (1 lần gọi): {avg_latency:.2f} ms")
    print(f"  Số token đầu ra trung bình: {avg_tokens:.0f} tokens")
    print(f"  Tốc độ xử lý: **{throughput_tokens_per_sec:.2f} tokens/giây**")
    print("-------------------------------------")
    
if __name__ == '__main__':
    main()