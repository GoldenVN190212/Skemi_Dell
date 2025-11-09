import json, joblib, os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

def train_model():
    if not os.path.exists("Train/dataset.json"):
        print("❌ Không tìm thấy dataset.json")
        return

    with open("Train/dataset.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    texts = [item["text"] for item in data]
    labels = [item["label"] for item in data]

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(texts)

    model = LogisticRegression()
    model.fit(X, labels)

    joblib.dump(model, "Train/skemi_model.pkl")
    joblib.dump(vectorizer, "Train/skemi_vectorizer.pkl")
    print("✅ Đã huấn luyện lại mô hình AI")

if __name__ == "__main__":
    train_model()