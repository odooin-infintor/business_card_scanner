# 📇 Business Card Scanner — Odoo 19 Module

Scan business cards and automatically save contact information directly into Odoo Contacts.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📸 Camera Capture | Use device camera to photograph business cards |
| 📁 File Upload | Upload JPG, PNG, WEBP images of business cards |
| 🖱️ Drag & Drop | Drop card images directly onto the upload zone |
| 🔍 OCR Extraction | Auto-extract name, email, phone, company, address, website |
| ✏️ Review & Edit | Review and correct extracted data before saving |
| 💾 Save to Contacts | One-click save to `res.partner` (Odoo Contacts) |
| 🏢 Company Matching | Auto-creates or links company contacts |
| 📊 Kanban View | Visual card-scan history with status tracking |
| 🔗 Contact Link | Smart button on partner form showing linked scan |

---

## 🚀 Installation

### 1. Copy module to Odoo addons path

```bash
cp -r business_card_scanner /path/to/odoo/addons/
```

### 2. Install OCR dependency (recommended)

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-eng

# Python package
pip install pytesseract Pillow
```

> **Note:** Without `pytesseract`, the module uses a demo/placeholder OCR response so you can still test the UI and workflow. In production, install the above packages for real OCR.

### 3. Activate in Odoo

1. Go to **Settings → Apps**
2. Search for **Business Card Scanner**
3. Click **Install**

---

## 🎯 How to Use

### Step 1 — Open Scanner
Go to **Contacts → Business Card Scanner → New Scan**

### Step 2 — Upload or Capture
- Click **Upload Image** to select a file, or
- Click **📸 Use Camera** to photograph the card live

### Step 3 — Extract Info
Click **🔍 Extract Info** — the module will OCR the card and auto-fill all fields.

### Step 4 — Review & Edit
Check the extracted fields. Edit anything that needs correction.

### Step 5 — Save to Contacts
Click **💾 Save to Contacts** to create the contact in Odoo.

---

## 📁 Module Structure

```
business_card_scanner/
├── __manifest__.py          # Module definition
├── __init__.py
├── models/
│   ├── __init__.py
│   └── business_card_scan.py  # Core model + OCR logic
├── controllers/
│   ├── __init__.py
│   └── main.py               # REST API endpoints
├── views/
│   ├── business_card_scan_views.xml  # Form, List, Kanban views
│   ├── res_partner_views.xml         # Partner smart button
│   └── menu_views.xml               # Menu items
├── security/
│   └── ir.model.access.csv   # Access control
├── data/
│   └/sequences.xml           # SCAN/YYYY/XXXX numbering
└── static/src/
    ├── css/scanner.css        # Modern UI styles
    └── js/card_scanner.js    # Camera + drag-drop JS
```

---

## 🔧 Configuration

No additional configuration required. The module works out-of-the-box.

### With Real OCR
Install `tesseract-ocr` and `pytesseract` for live extraction from real business cards.

### Without OCR
The module still works — it uses a demo contact to illustrate the workflow. You can manually type extracted info into the fields.

---

## 🛡️ Access Rights

| Group | Access |
|-------|--------|
| Internal Users | Create, Read, Write scans |
| Administrators | Full access including delete |

---

## 📦 Dependencies

- Odoo 19 (Community or Enterprise)
- Python: `odoo` core packages
- Optional: `pytesseract`, `Pillow` for OCR
- Optional: `tesseract-ocr` system binary

---

## 🧑‍💻 Developer Notes

### OCR Method
The `_perform_ocr()` method in `business_card_scan.py` tries `pytesseract` first. If not installed, it returns a realistic demo response so the full UI flow can be tested.

### Extending OCR
Replace `_perform_ocr()` or `_parse_card_text()` to integrate any OCR API (Google Vision, AWS Textract, Azure AI, etc.).

### REST API
- `POST /business_card/upload` — Upload image, get scan_id
- `POST /business_card/ocr/<scan_id>` — Run OCR and return fields

---

## 📄 License

LGPL-3
