"""Acquire original research PDFs into an authenticated, short-lived CI artifact.

No PDF or complete extracted text is committed/pushed by this producer. Public
receipts contain hashes, identity diagnostics and <=80 quoted words per paper.
Human method review happens after authorized artifact download, not from snippets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 16 * 1024 * 1024
SOURCES = (
    {
        "id": "concretum_noise_original",
        "url": "https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf",
        "title_terms": ["beat the market", "intraday momentum"],
        "author_surnames": ["zarattini", "aziz", "barbon"],
        "allowed_final_hosts": ["concretumgroup.com", "www.concretumgroup.com"],
        "method_terms": ["noise", "sigma", "upper", "lower", "vwap", "commission",
                         "slippage", "dividend", "30", "volatility", "out-of-sample"],
        "excerpt_terms": ["sigma", "vwap", "commission", "out-of-sample"],
    },
    {
        "id": "concretum_orb_original",
        "url": "https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf",
        "title_terms": ["profitable day trading strategy", "equity market"],
        "author_surnames": ["zarattini", "barbon"],
        "allowed_final_hosts": ["concretumgroup.com", "www.concretumgroup.com"],
        "method_terms": ["opening range", "volume", "commission", "slippage", "stocks",
                         "stop", "risk", "out-of-sample"],
        "excerpt_terms": ["opening range", "relative volume", "commission", "out-of-sample"],
    },
    {
        "id": "liu_tsyvinski_wu_common_crypto_original",
        "url": "https://www.nber.org/system/files/working_papers/w25882/w25882.pdf",
        "title_terms": ["common risk factors", "cryptocurrency"],
        "author_surnames": ["liu", "tsyvinski", "wu"],
        "rejected_first_page_markers": ["course assignment", "submitted by"],
        "allowed_final_hosts": ["www.nber.org", "nber.org"],
        "method_terms": ["momentum", "quintile", "weekly", "transaction", "short",
                         "delist", "market capitalization", "out-of-sample"],
        "excerpt_terms": ["quintile", "momentum", "transaction", "shorting"],
    },
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def pdf_details(raw, source, reader_factory=None):
    if len(raw) > MAX_BYTES or not raw.startswith(b"%PDF"):
        raise ValueError("Source must be a bounded actual PDF body")
    if reader_factory is None:
        from pypdf import PdfReader
        reader_factory = PdfReader
    reader = reader_factory(io.BytesIO(raw))
    page_text = [(page.extract_text() or "") for page in reader.pages]
    if not page_text or not any(page_text):
        raise ValueError("Original PDF has no extractable text; human OCR would be required")
    identity_scope = normalize(" ".join(page_text[:3])[:20000])
    title_ok = all(normalize(term) in identity_scope for term in source["title_terms"])
    authors_ok = all(normalize(term) in identity_scope for term in source["author_surnames"])
    first_page = normalize(page_text[0])
    rejected = any(normalize(term) in first_page for term in source.get("rejected_first_page_markers", []))
    if not (title_ok and authors_ok) or rejected:
        raise ValueError("Original PDF title/author identity mismatch; not accepted as the intended paper")
    text = "\n".join(f"PAGE {index + 1}\n{value}" for index, value in enumerate(page_text))
    term_pages = {term: [index + 1 for index, value in enumerate(page_text)
                         if term.lower() in value.lower()] for term in source["method_terms"]}
    excerpts, budget, used = [], 80, set()
    for term in source["excerpt_terms"]:
        if budget <= 0:
            break
        for page, value in enumerate(page_text):
            words = value.split()
            lowered = [word.lower() for word in words]
            matched = next((index for index, word in enumerate(lowered) if term.lower() in word), None)
            if matched is None:
                # Multiword terms are located in text, then mapped to an approximate
                # word position solely for a small, bounded citation window.
                hit = value.lower().find(term.lower())
                matched = len(value[:hit].split()) if hit >= 0 else None
            if matched is None:
                continue
            begin = max(0, matched - 4)
            if (page, begin) in used:
                continue
            count = min(20, budget, len(words) - begin)
            excerpts.append({"page": page + 1, "word_start": begin,
                             "word_count": count, "text": " ".join(words[begin:begin + count])})
            used.add((page, begin))
            budget -= count
            break
    metadata_title = getattr(reader.metadata, "title", None) if reader.metadata else None
    return {
        "pages": len(page_text), "extracted_words": len(text.split()),
        "title_verified_by_tokens": title_ok, "authors_verified_by_surnames": authors_ok,
        "identity_verification_scope": "First three extracted pages; token criteria, human review still required.",
        "pdf_title_metadata": metadata_title, "method_term_pages": term_pages,
        "excerpts": excerpts, "quoted_word_count": sum(row["word_count"] for row in excerpts),
        "human_full_paper_review_completed": False, "empirical_profit_reproduced": False,
    }, text


def acquire(source, output):
    receipt = {"id": source["id"], "requested_url": source["url"],
               "retrieved_at": datetime.now(timezone.utc).isoformat(),
               "source_definition_sha256": hashlib.sha256(canonical(source).encode()).hexdigest(),
               "copyright_handling": "Complete bodies only in short-lived authenticated Actions artifact; no repository push/public text publication.",
               "human_full_paper_review_completed": False, "empirical_profit_reproduced": False}
    try:
        with urlopen(Request(source["url"], headers={"User-Agent": "Mozilla/5.0 personal research"}), timeout=30) as response:
            final_url = response.geturl()
            if urlparse(final_url).scheme != "https" or urlparse(final_url).hostname not in source["allowed_final_hosts"]:
                raise ValueError("Original PDF redirected outside the declared official hosts")
            raw = response.read(MAX_BYTES + 1)
            receipt.update(status=response.status, final_url=final_url, bytes=len(raw),
                           pdf_sha256=hashlib.sha256(raw).hexdigest())
        details, text = pdf_details(raw, source)
        receipt.update(details, accepted_original_pdf=True)
        pdf_path = output / (source["id"] + ".pdf")
        text_path = output / (source["id"] + ".private.txt")
        pdf_path.write_bytes(raw)
        text_path.write_text(text, encoding="utf-8")
        receipt.update(pdf_file=pdf_path.name, private_text_file=text_path.name,
                       private_text_sha256=hashlib.sha256(text_path.read_bytes()).hexdigest())
    except Exception as error:
        receipt.update(status="unavailable", accepted_original_pdf=False,
                       error_type=type(error).__name__, error=str(error)[:300])
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="intraday-primary-artifact")
    args = parser.parse_args()
    commit = os.environ.get("GITHUB_SHA", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_REPOSITORY") != "NeatherFrog/awesome-x402" or
            not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise SystemExit("Only this repository's authorized Actions runner may acquire the artifact")
    producer_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    expected = os.environ.get("EXPECTED_PRODUCER_SHA256", "")
    if expected and (not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != producer_sha):
        raise SystemExit("Exact requested primary-source producer hash mismatch")
    output = Path(args.output)
    if output.exists():
        raise SystemExit("Fresh artifact directory required; do not overwrite previous original sources")
    output.mkdir(parents=True)
    receipts = [acquire(source, output) for source in SOURCES]
    report = {"schema": 1, "producer_commit": commit, "producer_sha256": producer_sha,
              "source_catalog_sha256": hashlib.sha256(canonical(SOURCES).encode()).hexdigest(),
              "source_definitions": SOURCES, "sources": receipts,
              "artifact_scope": "Authenticated seven-day CI artifact for authorized original-paper reading, not public branch republication.",
              "method_inference_limit": "Automated identity and small citations do not establish a full paper review or profitable reproduction."}
    (output / "receipts.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"producer_sha256": producer_sha, "producer_commit": commit,
                      "accepted_original_pdfs": sum(row["accepted_original_pdf"] for row in receipts),
                      "sources": len(receipts)}))
    if not receipts[0]["accepted_original_pdf"]:
        raise SystemExit("Required original intraday noise-area paper unavailable; inspect bounded receipts")


if __name__ == "__main__":
    main()
