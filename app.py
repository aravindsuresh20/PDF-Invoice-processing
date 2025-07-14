from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
import os
import re
import fitz  # PyMuPDF
import pdfplumber
from word2number import w2n

app = Flask(__name__)
app.secret_key = 'your_secret_key'

EXCEL_FILE = "D:/original files for uplaoding/CONTROLLER PROJECTS/PDF Invoice/extracted_data.xlsx"
MAX_PDFS = 25
EDA_FILE = "eda_results.txt"  # EDA output file

def extract_text_from_pdf(file_path, use_pdfplumber=False):
    text = ''
    if use_pdfplumber:
        return extract_text_with_pdfplumber(file_path)
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text("text")
        doc.close()
        if not text.strip():
            text = extract_text_with_pdfplumber(file_path)
        return text
    except Exception as e:
        print(f"Error with PyMuPDF: {e}")
        return extract_text_with_pdfplumber(file_path)

def extract_text_with_pdfplumber(file_path):
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ''
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + '\n'
            return text
    except Exception as e:
        print(f"Error with pdfplumber: {e}")
        return ''

def normalize_text(text):
    text = text.replace('\n', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def extract_invoice_data(text, filename):
    text = normalize_text(text)
    data = {
        "Source PDF": filename.capitalize(),
        "Invoice Date": "NA",
        "Invoice Number": "NA",
        "Due Date": "NA",
        "Order Number": "NA",
        "Payment Transaction ID": "NA",
        "Ship To": "NA",
        "Total Amount": "NA"
    }

    patterns = {
        "Invoice Number": r"Invoice\s+Number\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        "Invoice Date": r"Invoice\s+Date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        "Due Date": r"Due\s+Date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        "Order Number": r"Order\s+(?:Number|No|ID)[:\-]?\s*([A-Za-z0-9\-\/]+)",
        "Payment Transaction ID": r"Payment\s+Transaction\s+ID[:\-]?\s*([A-Za-z0-9\-]+)",
    }

    ship_to_patterns = [
        r"To:\s*(.*?)(?:Invoice|Order|Total|Bill\s+To)",
        r"(?:Ship\s+To|Shipping\s+Address)[:\s]*(.*?)(?:Total|Order|Invoice|Bill\s+To)",
        r"Billing\s+Address\s*[:\-]?\s*(.*?)(?:Shipping\s+Address|Total|Order|Invoice|Bill\s+To)",
        r"Shipping Address\s*[:\-]?\s*(.*?)(?:State/UT Code|Place of supply|Place of delivery)",
        r"(?:Ship\s+To|Shipping\sAddress)\s*[:\-]?\s*([\s\S]+?)(?=\n(?:Total|Order|Invoice|Bill))",
        r"(?:Ship\s+To|Shipping\sAddress)\s*[:\-]?\s*([\s\S]+)",
    ]

    for pattern in ship_to_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            ship_to_text = match.group(1).strip()
            email_match = re.search(r'\S+@\S+', ship_to_text)
            if email_match:
                ship_to_text = ship_to_text[:email_match.end()]
            else:
                ship_to_text = ship_to_text.split('\n')[0]
            data["Ship To"] = ship_to_text
            break

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()

    if data["Invoice Date"] == "NA":
        match = re.search(r"Invoice\s+Date[:\s]*([0-9]{2}[./-][0-9]{2}[./-][0-9]{4})", text)
        if match:
            data["Invoice Date"] = match.group(1).strip()

    if data["Due Date"] == "NA":
        match = re.search(r"Due\s+Date[:\s]*([0-9]{2}[./-][0-9]{2}[./-][0-9]{4})", text)
        if match:
            data["Due Date"] = match.group(1).strip()

    if data["Total Amount"] == "NA":
        total_patterns = [
            r"Total\s+Due\s*[:\-]?\s*([$£¥€₹]?\s?[0-9,]+\.\d{2})",
            r"Total\s*[:\-]?\s*([$£¥€₹]?\s?[0-9,]+\.\d{2})\s*$",
            r"(?:Invoice\s+Value|Grand\s+Total|Amount\s+Payable)\s*[:\-]?\s*([$£¥€₹]?\s?[0-9,]+\.\d{2})"
        ]
        for pat in total_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                data["Total Amount"] = match.group(1).strip()
                break

    if data["Total Amount"] == "NA":
        match = re.search(
            r"Amount\s+in\s+Words[:\s]*([A-Za-z\s\-]+(?:Point\s+[A-Za-z\s\-]+)?)(?:\s+only)?",
            text, re.IGNORECASE)
        if match:
            words = match.group(1).strip()
            try:
                if "point" in words.lower():
                    parts = re.split(r"\s+point\s+", words, flags=re.IGNORECASE)
                    whole = w2n.word_to_num(parts[0])
                    decimal = w2n.word_to_num(parts[1]) if len(parts) > 1 else 0
                    data["Total Amount"] = f"{whole}.{str(decimal).zfill(2)}"
                else:
                    number = w2n.word_to_num(words)
                    data["Total Amount"] = f"{number:.2f}"
            except:
                pass

    return data

def save_to_excel(data):
    column_order = [
        "Source PDF", "Invoice Date", "Invoice Number", "Due Date",
        "Order Number", "Payment Transaction ID", "Ship To", "Total Amount"
    ]
    df = pd.DataFrame([data], columns=column_order)
    try:
        os.makedirs(os.path.dirname(EXCEL_FILE), exist_ok=True)
        if os.path.exists(EXCEL_FILE):
            existing = pd.read_excel(EXCEL_FILE, engine='openpyxl')
            df = pd.concat([existing, df], ignore_index=True)
        df.to_excel(EXCEL_FILE, index=False, engine='openpyxl')
        print(f"✅ Data saved to {EXCEL_FILE}")
    except Exception as e:
        print(f"❌ Error saving to Excel: {e}")
        raise e

@app.route('/', methods=['GET'])
def startup():
    return render_template('startup.html')

@app.route('/upload', methods=['GET'])
def upload_page():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    extracted_data = []
    files = request.files.getlist('pdf_file')
    num_files = len(files)
    files_to_process = files[:MAX_PDFS]
    for file in files_to_process:
        if file:
            file_path = f'temp_{file.filename}'
            try:
                file.save(file_path)
                text = extract_text_from_pdf(file_path)
                if not text:
                    text = extract_text_with_pdfplumber(file_path)
                data = extract_invoice_data(text, file.filename)
                extracted_data.append(data)
                save_to_excel(data)
            except Exception as e:
                print(f"❌ Error processing file {file.filename}: {e}")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
    session['extracted_data'] = extracted_data
    session['num_files'] = num_files

    # ✅ Save EDA result to a notepad file
    with open(EDA_FILE, 'w') as f:
        f.write(f"Total PDF files processed: {num_files}\n")

    return redirect(url_for('results'))

@app.route('/results')
def results():
    extracted_data = session.get('extracted_data', [])
    num_files = session.get('num_files', 0)
    return render_template('results.html', data=extracted_data, num_files=num_files)

@app.route('/download')
def download_result():
    try:
        return send_file(EXCEL_FILE, as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)



