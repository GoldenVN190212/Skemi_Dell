from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

app = Flask(__name__)

# Load Mistral đã tải offline
MODEL_PATH = "D:/Skemi/Train/Free" # đường dẫn nơi lưu model
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, trust_remote_code=True, device_map="auto")

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question", "")

    if not question:
        return jsonify({"answer": "Câu hỏi trống"})

    inputs = tokenizer(question, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=150)
    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)

    return jsonify({"answer": answer})

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"message": "Không có file"})

    # Lưu tạm file, sau này có thể xử lý phân tích
    path = f"uploads/{file.filename}"
    file.save(path)
    return jsonify({"message": f"Upload thành công: {file.filename}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
