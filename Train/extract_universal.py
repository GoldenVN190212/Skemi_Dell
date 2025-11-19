import os
import json
import docx
import pdfplumber
from pptx import Presentation
from PIL import Image
import pytesseract
import pandas as pd
from bs4 import BeautifulSoup
import yaml
import sqlite3
import zipfile
import re
import magic  # pip install python-magic-bin

# =========================
# Helper: Extract ASCII/Unicode from binary
# =========================
def extract_from_binary(path):
    try:
        raw = open(path, "rb").read()
        ascii_text = re.findall(rb"[ -~]{5,}", raw)
        unicode_text = re.findall(rb"(?:[\x20-\x7E][\x00]){5,}", raw)
        ascii_text = b"\n".join(ascii_text).decode("utf-8", errors="ignore")
        unicode_text = b"\n".join(unicode_text).decode("utf-16", errors="ignore")
        return ascii_text + "\n" + unicode_text
    except:
        return ""

# =========================
# Extract text by type
# =========================
def extract_pdf(path):
    try:
        text = ""
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    text += t + "\n"
        return text
    except:
        return ""

def extract_docx(path):
    try:
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except:
        return ""

def extract_pptx(path):
    try:
        prs = Presentation(path)
        texts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    texts.append(shape.text)
        return "\n".join(texts)
    except:
        return ""

def extract_excel(path):
    try:
        df = pd.read_excel(path)
        return df.to_string()
    except:
        return ""

def extract_csv(path):
    try:
        df = pd.read_csv(path)
        return df.to_string()
    except:
        return ""

def extract_json(path):
    try:
        data = json.load(open(path, "r", encoding="utf-8"))
        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return ""

def extract_yaml(path):
    try:
        data = yaml.safe_load(open(path, "r", encoding="utf-8"))
        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return ""

def extract_html(path):
    try:
        html = open(path, "r", encoding="utf-8", errors="ignore").read()
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text("\n")
    except:
        return ""

def extract_txt(path):
    try:
        return open(path, "r", encoding="utf-8", errors="ignore").read()
    except:
        return ""

def extract_sqlite(path):
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        output = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for (table,) in tables:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            output.append(f"===== TABLE {table} =====")
            for row in rows:
                output.append(str(row))
        conn.close()
        return "\n".join(output)
    except:
        return ""

def extract_zip(path):
    text = ""
    try:
        with zipfile.ZipFile(path) as z:
            for file in z.namelist():
                sub = z.open(file)
                try:
                    content = sub.read().decode("utf-8", errors="ignore")
                except:
                    continue
                text += f"\n\n=== {file} ===\n{content}"
    except:
        pass
    return text

def extract_image(path):
    try:
        img = Image.open(path)
        t = pytesseract.image_to_string(img, lang="eng+vie")
        return t.strip()
    except:
        return ""

# =========================
# MAIN FUNCTION
# =========================
def extract_text(path):
    ext = path.lower()
    mime = magic.from_file(path, mime=True)

    # Text files
    if ext.endswith((".txt", ".md", ".ini", ".cfg", ".env", ".log")):
        return extract_txt(path)
    # Office
    if ext.endswith(".pdf"): return extract_pdf(path)
    if ext.endswith(".docx"): return extract_docx(path)
    if ext.endswith(".pptx"): return extract_pptx(path)
    if ext.endswith(".csv"): return extract_csv(path)
    if ext.endswith(".xlsx"): return extract_excel(path)
    # Structured
    if ext.endswith(".json"): return extract_json(path)
    if ext.endswith((".yaml", ".yml")): return extract_yaml(path)
    if ext.endswith((".html", ".htm", ".xml")): return extract_html(path)
    # Database
    if ext.endswith((".sqlite", ".db")): return extract_sqlite(path)
    # ZIP
    if ext.endswith(".zip"): return extract_zip(path)
    # Source code
    if ext.endswith((".py", ".js", ".ts", ".cpp", ".c", ".java", ".cs", ".php", ".html", ".css")):
        return extract_txt(path)
    # Image
    if mime.startswith("image/"): 
        return extract_image(path)  # nếu rỗng, Granite vẫn phân tích ảnh
    # Fallback binary
    try:
        return open(path, "r", encoding="utf-8", errors="ignore").read()
    except:
        return extract_from_binary(path)
