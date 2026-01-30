# contract_ai_app.py

import os
import re
import uuid
import shutil
from datetime import datetime

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse

import pdfplumber
import docx
import spacy
from langdetect import detect

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


# ===============================
# INITIAL SETUP
# ===============================

UPLOAD_DIR = "uploads"
REPORT_DIR = "reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

nlp = spacy.load("en_core_web_sm")

app = FastAPI(
    title="Contract Analysis AI",
    description="AI Powered Contract Risk Analyzer",
    version="1.0"
)


# ===============================
# FILE HANDLING
# ===============================

def save_file(file: UploadFile):
    ext = file.filename.split(".")[-1]
    file_id = str(uuid.uuid4())
    path = f"{UPLOAD_DIR}/{file_id}.{ext}"

    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return path


# ===============================
# TEXT EXTRACTION
# ===============================

def extract_text(path):

    if path.endswith(".pdf"):
        text = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        return text

    elif path.endswith(".docx"):
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

    elif path.endswith(".txt"):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    else:
        return ""


# ===============================
# LANGUAGE DETECTION
# ===============================

def detect_language(text):
    try:
        return detect(text)
    except:
        return "unknown"


# ===============================
# CLAUSE EXTRACTION
# ===============================

def split_clauses(text):

    pattern = r"\n\s*\d+[\.\)]\s+"
    parts = re.split(pattern, text)

    clauses = []

    for i, part in enumerate(parts):
        if len(part.strip()) > 50:
            clauses.append({
                "id": i+1,
                "text": part.strip()
            })

    return clauses


# ===============================
# NAMED ENTITY RECOGNITION
# ===============================

def extract_entities(text):

    doc = nlp(text)

    entities = []

    for ent in doc.ents:
        entities.append({
            "text": ent.text,
            "label": ent.label_
        })

    return entities


# ===============================
# OBLIGATION / RIGHT / PROHIBITION
# ===============================

def detect_intent(sentence):

    s = sentence.lower()

    if "shall" in s or "must" in s:
        return "Obligation"

    if "may" in s or "can" in s:
        return "Right"

    if "shall not" in s or "must not" in s:
        return "Prohibition"

    return "Neutral"


# ===============================
# RISK ENGINE
# ===============================

HIGH_RISK = [
    "unlimited liability",
    "non compete",
    "penalty",
    "terminate anytime",
    "without notice",
    "indemnify",
    "exclusive"
]

MEDIUM_RISK = [
    "lock in",
    "arbitration",
    "auto renew",
    "jurisdiction",
    "confidentiality"
]


def calculate_risk(text):

    score = 0
    found = []

    t = text.lower()

    for word in HIGH_RISK:
        if word in t:
            score += 30
            found.append(word)

    for word in MEDIUM_RISK:
        if word in t:
            score += 15
            found.append(word)

    score = min(score, 100)

    if score > 60:
        level = "HIGH"
    elif score > 30:
        level = "MEDIUM"
    else:
        level = "LOW"

    return score, level, found


# ===============================
# COMPLIANCE CHECK (INDIA)
# ===============================

def check_compliance(text):

    flags = []

    t = text.lower()

    if "non compete" in t:
        flags.append("Non-compete validity under Indian Contract Act")

    if "unlimited liability" in t:
        flags.append("Unlimited liability may be unenforceable")

    if "no termination" in t:
        flags.append("Termination restriction may violate labor laws")

    return flags


# ===============================
# SIMPLE SUMMARY
# ===============================

def generate_summary(text):

    lines = text.split(".")[:5]

    summary = " ".join(lines)

    if len(summary) > 500:
        summary = summary[:500] + "..."

    return summary


# ===============================
# PDF REPORT GENERATOR
# ===============================

def generate_report(data):

    report_id = str(uuid.uuid4())
    path = f"{REPORT_DIR}/{report_id}.pdf"

    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    def add(text, space=10):
        elements.append(Paragraph(text, styles["Normal"]))
        elements.append(Spacer(1, space))


    add("<b>Contract Analysis Report</b>", 20)

    add(f"Generated: {datetime.now()}")

    add(f"Language: {data['language']}")

    add(f"Risk Score: {data['risk_score']} ({data['risk_level']})", 20)


    add("<b>Summary</b>", 15)
    add(data["summary"], 20)


    add("<b>Compliance Flags</b>", 15)
    if data["compliance"]:
        for c in data["compliance"]:
            add("- " + c)
    else:
        add("No major issues found")


    add("<b>Detected Entities</b>", 15)
    for e in data["entities"][:20]:
        add(f"{e['text']} ({e['label']})")


    add("<b>Clause Analysis</b>", 20)

    for c in data["clauses"]:

        add(f"<b>Clause {c['id']}</b>", 10)
        add(c["text"][:500] + "...")

        add(f"Intent: {c['intent']}")
        add(f"Risk: {c['risk_level']} ({c['risk_score']})", 15)


    doc.build(elements)

    return path


# ===============================
# MAIN PIPELINE
# ===============================

async def analyze_contract(file: UploadFile):

    path = save_file(file)

    text = extract_text(path)

    if not text:
        return {"error": "Could not extract text"}

    language = detect_language(text)

    clauses_raw = split_clauses(text)

    clauses = []

    total_risk = 0


    for c in clauses_raw:

        intent = detect_intent(c["text"])

        score, level, found = calculate_risk(c["text"])

        total_risk += score

        clauses.append({
            "id": c["id"],
            "text": c["text"],
            "intent": intent,
            "risk_score": score,
            "risk_level": level,
            "keywords": found
        })


    avg_risk = int(total_risk / max(len(clauses),1))

    if avg_risk > 60:
        contract_level = "HIGH"
    elif avg_risk > 30:
        contract_level = "MEDIUM"
    else:
        contract_level = "LOW"


    entities = extract_entities(text)

    compliance = check_compliance(text)

    summary = generate_summary(text)


    result = {
        "language": language,
        "risk_score": avg_risk,
        "risk_level": contract_level,
        "entities": entities,
        "compliance": compliance,
        "summary": summary,
        "clauses": clauses
    }


    report_path = generate_report(result)

    result["report_url"] = f"/download/{os.path.basename(report_path)}"

    return result


# ===============================
# API ENDPOINTS
# ===============================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    result = await analyze_contract(file)

    return result


@app.get("/download/{filename}")
def download(filename: str):

    path = f"{REPORT_DIR}/{filename}"

    return FileResponse(path, media_type="application/pdf")


# ===============================
# RUN SERVER
# ===============================

# Run using:
# uvicorn contract_ai_app:app --reload