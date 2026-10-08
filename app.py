from flask import Flask, render_template, request, redirect, url_for, flash
from pathlib import Path
from datetime import datetime
import json
import os
import re

import yaml

from congress_api import CongressGovClient

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "bill-explorer-dev-secret")

OUTPUT_DIR = Path(__file__).resolve().parent / "exports"
OUTPUT_DIR.mkdir(exist_ok=True)

client = CongressGovClient(api_key=os.environ.get("CONGRESS_API_KEY"))


def slugify(value: str) -> str:
    value = (value or "bill").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "bill"


def format_markdown(bill: dict) -> str:
    title = bill.get("title") or "Untitled Bill"
    status = bill.get("status") or "Unknown"
    sponsors = bill.get("sponsors") or []
    cosponsors = bill.get("cosponsors") or []
    summary = bill.get("summary") or "No summary available."
    committee = bill.get("committee") or "Unknown"
    text_url = bill.get("text_url") or "N/A"
    bill_id = bill.get("bill_id") or f"{bill.get('congress', '')}-{bill.get('bill_type', '')}-{bill.get('number', '')}"

    sponsor_text = ", ".join(sponsors) if sponsors else "None listed"
    cosponsor_text = ", ".join(cosponsors) if cosponsors else "None listed"

    return f"# {title}\n\n" \
        f"- Bill ID: `{bill_id}`\n" \
        f"- Congress: {bill.get('congress', 'N/A')}\n" \
        f"- Bill Type: {bill.get('bill_type', 'N/A')}\n" \
        f"- Number: {bill.get('number', 'N/A')}\n" \
        f"- Status: {status}\n" \
        f"- Committee: {committee}\n" \
        f"- Sponsors: {sponsor_text}\n" \
        f"- Cosponsors: {cosponsor_text}\n" \
        f"- Text URL: {text_url}\n\n" \
        f"## Summary\n\n{summary}\n"


def save_bill_export(bill: dict, export_type: str = "yaml") -> Path:
    safe_title = slugify(bill.get("title") or bill.get("bill_id") or "bill")
    bill_id = bill.get("bill_id") or f"{bill.get('congress', 'unknown')}-{bill.get('bill_type', 'bill')}-{bill.get('number', '0')}"
    filename = f"{bill_id}-{safe_title}"

    if export_type == "markdown":
        path = OUTPUT_DIR / f"{filename}.md"
        path.write_text(format_markdown(bill), encoding="utf-8")
    else:
        path = OUTPUT_DIR / f"{filename}.yaml"
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(bill, fh, sort_keys=False, allow_unicode=True)

    return path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    query = (request.form.get("query") or "").strip()
    congress = (request.form.get("congress") or "").strip()
    bill_type = (request.form.get("bill_type") or "").strip().lower()
    limit = int(request.form.get("limit") or 10)
    status = (request.form.get("status") or "").strip()

    if not query and not congress and not bill_type and not status:
        flash("Enter at least one filter to search for bills.")
        return redirect(url_for("index"))

    try:
        bills = client.search_bills(
            query=query,
            congress=congress,
            bill_type=bill_type or None,
            status=status or None,
            limit=limit,
        )
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("index"))
    except Exception as exc:  # pragma: no cover
        flash(f"Unable to query Congress.gov: {exc}")
        return redirect(url_for("index"))

    return render_template(
        "results.html",
        bills=bills,
        query=query,
        congress=congress,
        bill_type=bill_type,
        status=status,
        limit=limit,
    )


@app.route("/export", methods=["POST"])
def export_bill():
    bill_raw = request.form.get("bill_data")
    export_type = request.form.get("export_type", "yaml")

    if not bill_raw:
        flash("No bill data was provided for export.")
        return redirect(url_for("index"))

    try:
        bill = json.loads(bill_raw)
    except json.JSONDecodeError:
        flash("The bill payload could not be parsed.")
        return redirect(url_for("index"))

    output_path = save_bill_export(bill, export_type)
    flash(f"Saved to {output_path.relative_to(Path(__file__).resolve().parent)}")
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
