from datetime import datetime, timedelta
import random
import hashlib
import re


VENDORS = ["Orange", "SNCF", "Amazon Business", "EDF", "Ikea", "OVH", "Carrefour"]
DEFAULT_RULES = [
    ("orange", ("626000", "Frais telecom")),
    ("ovh", ("613200", "Hebergement")),
    ("sncf", ("625100", "Transport")),
    ("edf", ("606100", "Energie")),
    ("ikea", ("606300", "Petit equipement")),
    ("carrefour", ("606400", "Fournitures")),
    ("amazon", ("607000", "Achats")),
]


def random_doc_data(filename: str):
    amount = round(random.uniform(100, 1000), 2)
    vat = round(amount * 0.2, 2)
    vendor = random.choice(VENDORS)
    doc_date = (datetime.utcnow() - timedelta(days=random.randint(0, 30))).date().isoformat()
    status = "OK" if random.random() > 0.15 else "A verifier"
    created_at = datetime.utcnow().isoformat()
    return {
        "filename": filename,
        "vendor": vendor,
        "doc_date": doc_date,
        "amount_ttc": amount,
        "vat": vat,
        "status": status,
        "created_at": created_at,
    }


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def parse_fields_from_text(text: str):
    cleaned = " ".join(text.split())
    if not cleaned:
        return {}

    date_match = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", cleaned)
    amount_match = re.search(r"(TTC|TOTAL|MONTANT)\s*[:\-]?\s*([0-9]+[.,][0-9]{2})", cleaned, re.IGNORECASE)
    vat_match = re.search(r"(TVA)\s*[:\-]?\s*([0-9]+[.,][0-9]{2})", cleaned, re.IGNORECASE)
    vendor_match = re.search(r"(SIRET|SIREN|Fournisseur)\s*[:\-]?\s*([A-Za-z0-9 &.-]{3,})", cleaned, re.IGNORECASE)

    def _to_float(val: str | None):
        if not val:
            return None
        return float(val.replace(",", "."))

    amount = _to_float(amount_match.group(2)) if amount_match else None
    vat = _to_float(vat_match.group(2)) if vat_match else None
    doc_date = None
    if date_match:
        d = date_match.group(1).replace("/", "-")
        doc_date = d[6:10] + "-" + d[3:5] + "-" + d[0:2]

    vendor = vendor_match.group(2).strip() if vendor_match else "Fournisseur"

    if amount is None:
        return {}

    if vat is None:
        vat = round(amount * 0.2, 2)

    return {
        "vendor": vendor,
        "doc_date": doc_date or "2026-01-01",
        "amount_ttc": amount,
        "vat": vat,
        "status": "OK",
        "created_at": datetime.utcnow().isoformat(),
    }


def infer_account(vendor: str, tenant_rules: list[tuple[str, str, str]] | None = None):
    v = vendor.lower()
    if tenant_rules:
        for key, code, label in tenant_rules:
            if key.lower() in v:
                return code, label
    for key, (code, label) in DEFAULT_RULES:
        if key in v:
            return code, label
    return "606000", "Achats divers"


def to_accounting_entries(doc: dict, tenant_rules: list[tuple[str, str, str]] | None = None):
    """
    Generate basic accounting entries (journal achats).
    """
    amount_ttc = float(doc["amount_ttc"])
    vat = float(doc["vat"])
    amount_ht = round(amount_ttc - vat, 2)
    expense_code, expense_label = infer_account(doc["vendor"], tenant_rules)
    vendor_code = "401000"
    vat_code = "445660"

    return [
        {
            "date": doc["doc_date"],
            "journal": "ACH",
            "account": expense_code,
            "label": expense_label,
            "debit": amount_ht,
            "credit": 0.0,
            "doc": doc["filename"],
            "vendor": doc["vendor"],
        },
        {
            "date": doc["doc_date"],
            "journal": "ACH",
            "account": vat_code,
            "label": "TVA deductible",
            "debit": vat,
            "credit": 0.0,
            "doc": doc["filename"],
            "vendor": doc["vendor"],
        },
        {
            "date": doc["doc_date"],
            "journal": "ACH",
            "account": vendor_code,
            "label": f"Fournisseur {doc['vendor']}",
            "debit": 0.0,
            "credit": amount_ttc,
            "doc": doc["filename"],
            "vendor": doc["vendor"],
        },
    ]


def best_matches(documents: list[dict], txns: list[dict]):
    """
    Simple matching by amount and date proximity.
    Returns list of {document_id, bank_txn_id, match_score}.
    """
    matches = []
    for d in documents:
        best = None
        for t in txns:
            if abs(float(d["amount_ttc"]) - float(t["amount"])) > 0.01:
                continue
            score = 0.6
            if d["doc_date"] == t["txn_date"]:
                score += 0.3
            if d["vendor"].lower() in t["description"].lower():
                score += 0.1
            if best is None or score > best["match_score"]:
                best = {"document_id": d["id"], "bank_txn_id": t["id"], "match_score": round(score, 2)}
        if best and best["match_score"] >= 0.7:
            matches.append(best)
    return matches
