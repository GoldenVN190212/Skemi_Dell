import json, re, os

train_path = "Train/dataset.json"
backup_path = "Train/dataset_backup.json"

# === B1. Sao lưu ===
if os.path.exists(train_path):
    os.rename(train_path, backup_path)
    print(f"📦 Đã sao lưu dataset cũ -> {backup_path}")

# === B2. Đọc dữ liệu cũ ===
with open(backup_path, "r", encoding="utf-8") as f:
    data = json.load(f)

cleaned = []
for i, item in enumerate(data):
    text = item.get("text", "").strip()
    label = item.get("label", "").strip()

    # Bỏ các mẫu quá ngắn, rác, hoặc lặp vô nghĩa
    if len(text) < 25 or len(label) == 0:
        continue

    # Loại bỏ dòng rác có cụm "là quá trình" bị nhân bản
    if re.search(r"là quá trình", text, re.IGNORECASE):
        # Giữ lại đúng 1-2 mẫu thật đầu tiên nếu có nghĩa
        if len(cleaned) < 10 and len(text) < 120:
            cleaned.append(item)
        continue

    # Bỏ dòng toàn ký tự vô nghĩa (chữ loạn, nhiều ngôn ngữ trộn)
    if not re.search(r"[a-zA-ZÀ-ỹ]", text):
        continue
    if len(set(re.findall(r"[a-zA-ZÀ-ỹ]", text))) < 4:
        continue

    # Nếu qua được hết thì giữ lại
    cleaned.append({"text": text, "label": label})

print(f"🧹 Dọn xong, còn lại {len(cleaned)} mẫu sạch (từ {len(data)} mẫu gốc)")

# === B3. Ghi đè ===
with open(train_path, "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

print("✅ Đã ghi đè Train/dataset.json (bản sạch hoàn toàn)")
