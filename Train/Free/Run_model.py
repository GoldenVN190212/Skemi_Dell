# File: Run_model.py
import ollama

print("=== Test Gemma3:1b ===")

while True:
    user_input = input("Bạn: ")
    if user_input.lower() in ["exit", "quit"]:
        print("Kết thúc.")
        break

    try:
        response = ollama.chat(
            model="gemma3:1b",
            messages=[
                {"role": "system", "content": "Bạn là một chatbot thân thiện, trả lời ngắn gọn."},
                {"role": "user", "content": user_input}
            ]
        )
        # Lấy kết quả
        # response['message']['content'] theo docs
        reply = None
        try:
            reply = response['message']['content']
        except Exception:
            # fallback nếu khác kiểu
            if hasattr(response, "message") and hasattr(response.message, "content"):
                reply = response.message.content
        if not reply:
            reply = "Gemma không trả lời được."
        print("Gemma:", reply)

    except Exception as e:
        print("Gemma: Lỗi khi gọi model:", e)
