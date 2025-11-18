# model_qwen3.py
from ollama import chat

# Chatbot xịn Qwen3-VL:4B
def call_gemma_pro_chat(messages):
    """
    messages: list of dict {"role": "user"/"system", "content": "..."}
    Trả về text chatbot
    """
    resp = chat(model="gemma3:4b-it-q4_K_M", messages=messages)
    return resp.message.content  # chỉ lấy text
