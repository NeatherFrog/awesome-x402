"""Portable runtime view of immutable campaign evidence.

The historical inventory reader is itself fingerprinted by published
dependence diagnostics. Preserve its bytes; correct its Windows-relative-path
receipt presentation here without altering models, outcomes or admission.
"""
from pathlib import Path

from . import research_campaign as archive


def portable_receipt(root, row):
    if row.get("promotion_blocked") is not True:
        return row
    spec = archive.STUDIES.get(row.get("id"), {})
    if not spec.get("blocked_protocol_sha256"):
        return row
    verified = False
    try:
        base = Path(root).resolve()
        value = archive.read_report(base, row["id"])
        audit = archive._receipt(base, spec["directory"], "retrospective-causality-audit.json")
        name = "data/" + spec["directory"] + "/retrospective-causality-audit.json"
        original = archive._path(base, name)
        path = (original if original.exists() or (base / name).is_symlink() else
                archive._path(base, "docs/research-receipts/" + spec["directory"] + "/retrospective-causality-audit.json"))
        verified = bool(value and audit
            and value.get("protocol_sha256") == spec["blocked_protocol_sha256"]
            and audit.get("protocol_sha256") == spec["blocked_protocol_sha256"]
            and audit.get("status") == "causal_green_revoked"
            and audit.get("promotion_blocked") is True
            and audit.get("sealed_report_sha256") == archive._file_hash(archive._path(base, "docs/" + spec["file"]))
            and archive._hash_matches(base, path.relative_to(base).as_posix(), spec["causality_audit_sha256"]))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    # Only an artifact-identity fact changes. The known causal block and all
    # paper/live/Telegram permission fields stay as returned by the archive.
    return {**row, "causality_audit_receipt_verified": verified}


def board(root):
    result = archive.board(root)
    return {**result, "studies": [portable_receipt(root, row) for row in result["studies"]]}


def inspect(root, study, value=None):
    return portable_receipt(root, archive.inspect(root, study, value))


def report(root, study):
    result = archive.report(root, study)
    if result is None:
        return None
    return {**result, "verification": portable_receipt(root, result["verification"])}
