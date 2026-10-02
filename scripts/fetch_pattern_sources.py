"""Read public primary sources in CI; publish receipts and tiny excerpts only."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SOURCES = {
    "gatev_pairs": "https://www.nber.org/system/files/working_papers/w7032/w7032.pdf",
    "gao_intraday": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866",
    "concretum_noise": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172",
    "concretum_orb": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
    "snb_fx": "https://www.snb.ch/n/mmr/reference/working_paper_2010_10/source/working_paper_2010_10.n.pdf",
    "author_pairs": "https://www.utstat.utoronto.ca/~ali/papers/PairsTrading.pdf",
    "author_orb_page": "https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/",
    "author_noise_page": "https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/",
    "cme_mes": "https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.contractSpecs.html",
    "cme_mnq": "https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html",
}


def read_sources():
    rows = []
    for name, url in SOURCES.items():
        row = {"id": name, "requested_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
               "copyright": "Full body stays ephemeral; excerpts at most80words TOTAL per source.",
               "title_verified": False, "strategy_profit_verified": False}
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 personal research"}), timeout=30) as response:
                raw = response.read(16*1024*1024+1)
                if len(raw) > 16*1024*1024:
                    raise ValueError("Source exceeds16MiB")
                row.update(status=response.status, final_url=response.url, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if raw.startswith(b"%PDF"):
                from pypdf import PdfReader
                pdf = PdfReader(io.BytesIO(raw))
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                row["pages"] = len(pdf.pages)
                row["pdf_title_metadata"] = str(pdf.metadata.title) if pdf.metadata and pdf.metadata.title else None
            else:
                text = raw.decode("utf-8", errors="replace")
                row["title_tag"] = re.findall(r"<title[^>]*>(.*?)</title>", text, re.I|re.S)[:1]
                row["pdf_links"] = list(dict.fromkeys(re.findall(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]*)?", text)))[:12]
                text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.I|re.S)
                text = re.sub(r"<[^>]+>", " ", text)
            words = text.split()
            row["extracted_word_count"] = len(words)
            row["body_not_available_to_local_reviewer"] = True
            # Three short windows share one80-word budget, rather than quoting
            # every retrieved page or pretending the excerpt is a full review.
            needles = ("commission", "transaction", "formation", "opening range", "volatility", "cost", "intraday")
            candidates = [0]
            lowered = [w.lower() for w in words]
            for needle in needles:
                indices = [i for i,w in enumerate(lowered) if needle in w]
                if indices:
                    candidates.append(max(0, indices[0]-5))
                if len(candidates) >= 3:
                    break
            budget = 80
            excerpts = []
            for begin in candidates:
                count = min(26, budget, len(words)-begin)
                if count > 0:
                    excerpts.append({"word_start": begin, "word_count": count,
                                     "text": " ".join(words[begin:begin+count])})
                    budget -= count
            row["excerpts"] = excerpts
        except Exception as error:
            row.update(status="unavailable", error=type(error).__name__+": "+str(error)[:300])
        rows.append(row)
    return {"schema": 1, "sources": rows, "limitations": "Receipts and tiny excerpts are not full paper review or empirical profit proof."}


def main():
    sha = os.environ.get("GITHUB_SHA", "")
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REPOSITORY") != "NeatherFrog/awesome-x402" or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit("Only this repository's own authorized CI runner")
    report = read_sources()
    report["producer_commit"] = sha
    branch = "pattern-sources-" + sha[:12]
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    Path("pattern-source-receipts.json").write_text(raw, encoding="utf-8")
    print(json.dumps({"sources": len(report["sources"]), "available": sum(r["status"]==200 for r in report["sources"]), "branch": branch}))
    # Plumbing creates one independent public tree on the disposable runner,
    # using its existing Git authentication without reading credentials or
    # changing its checkout/index. No PDF/full extracted text is distributed.
    origin = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
    if origin != "https://github.com/NeatherFrog/awesome-x402":
        if origin != "https://github.com/NeatherFrog/awesome-x402.git":
            raise SystemExit("Unexpected origin")
    blob = subprocess.check_output(["git", "hash-object", "-w", "--stdin"], input=raw.encode()).decode().strip()
    tree = subprocess.check_output(["git", "mktree"], input=("100644 blob "+blob+"\treceipts.json\n").encode()).decode().strip()
    commit = subprocess.check_output(["git", "-c", "user.email=research@users.noreply.github.com", "-c", "user.name=Research receipts", "commit-tree", tree],
                                     input=b"Public primary-source retrieval receipts\n").decode().strip()
    subprocess.run(["git", "push", "origin", commit+":refs/heads/"+branch], check=True, capture_output=True)


if __name__ == "__main__":
    main()
