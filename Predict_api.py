from flask import Flask, request, jsonify
from flask_cors import CORS
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

app = Flask(__name__)
CORS(app)  # ✅ Cho phép mọi origin, xử lý cả preflight

# ======================= LOAD MISTRAL =======================
MISTRAL_PATH = "Train/models/mistral/"
mistral_tokenizer = AutoTokenizer.from_pretrained(MISTRAL_PATH)
mistral_model = AutoModelForCausalLM.from_pretrained(
    MISTRAL_PATH, device_map="auto", torch_dtype=torch.float16
)

def generate_mistral(prompt, max_length=200):
    inputs = mistral_tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = mistral_model.generate(**inputs, max_new_tokens=max_length)
    return mistral_tokenizer.decode(outputs[0], skip_special_tokens=True)

# ======================= CHAT ROUTE =======================
@app.route("/ask_mistral", methods=["POST"])
def ask_mistral():
    data = request.get_json()
    question = data.get("question", "")
    if not question:
        return jsonify({"status": "error", "message": "❌ Thiếu câu hỏi!"})
    answer = generate_mistral(question)
    return jsonify({"status": "success", "answer": answer})

# ======================= TRÍCH Ý CHÍNH CHO MINDMAP =======================
@app.route("/extract_subtopics", methods=["POST", "OPTIONS"])
def extract_subtopics():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json()
    text = data.get("text", "")
    mode = data.get("mode", "summary")

    sentences = text.split(".")
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if mode == "summary":
        return jsonify({"subtopics": sentences[:3]})

    if mode == "detail":
        # Đơn giản: chia thành 5 nhóm bằng chiều dài
        n = 5
        step = max(1, len(sentences) // n)
        clusters = [sentences[i:i+step] for i in range(0, len(sentences), step)]
        subtopics = ["; ".join(cluster[:2]) for cluster in clusters[:5]]
        return jsonify({"subtopics": subtopics})

    return jsonify({"subtopics": ["Không thể phân tích nội dung"]})

# ======================= TEST SERVER =======================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "🚀 Server Flask với Mistral đang chạy!"})

# ======================= RUN SERVER =======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
