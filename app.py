import os
import json
from datetime import datetime

from flask import Flask, request, jsonify
import smtplib
from email.message import EmailMessage

app = Flask(__name__)

# File log
LOG_FILE = os.environ.get("DELETED_PRODUCTS_LOG_FILE", "deleted_products.log")

# Optional Flow token - safe to leave even if you do not use Flow anymore
FLOW_WEBHOOK_TOKEN = os.environ.get("FLOW_WEBHOOK_TOKEN")

# Email config
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")


def send_deletion_email(event: dict) -> None:
    """Send an email alert about a deleted product."""
    if not (ALERT_EMAIL_FROM and ALERT_EMAIL_TO and SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        app.logger.warning("Email not configured, skipping send")
        return

    product = event.get("product") or {}
    shop = event.get("shop") or {}
    payload = event.get("payload") or {}

    shop_domain = shop.get("domain") or ""
    shop_id = shop.get("id") or "Unknown"
    deleted_at = event.get("received_at")

    skus = product.get("skus") or []
    skus_str = ", ".join(skus) if skus else "None"

    subject = f"[Shopify] Product deleted - {product.get('id')}"

    lines = [
        "A product was deleted in Shopify.",
        "",
        f"Store domain: {shop_domain}",
        f"Store id: {shop_id}",
        "",
        f"Product id: {product.get('id')}",
        f"Product handle: {product.get('handle')}",
        f"Product title: {product.get('title')}",
        f"Vendor: {product.get('vendor')}",
        f"Product type: {product.get('product_type')}",
        f"SKUs: {skus_str}",
        "",
        f"Received at: {deleted_at}",
        "",
        "Raw webhook payload:",
        json.dumps(payload, ensure_ascii=False, indent=2),
    ]
    body = "\n".join(lines)

    msg = EmailMessage()
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ALERT_EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        app.logger.info("Deletion email sent successfully")
    except Exception as e:
        app.logger.error("Failed to send deletion email: %s", e)


@app.route("/", methods=["GET"])
def health():
    return "Shopify product deleted logger is running", 200


@app.route("/shopify/product-deleted", methods=["POST", "GET"])
def product_deleted():
    """Old Flow endpoint - safe to keep or remove."""

    # For browser testing
    if request.method == "GET":
        return jsonify({"status": "ok", "info": "GET received on product-deleted endpoint"}), 200

    # Optional Flow token check
    if FLOW_WEBHOOK_TOKEN:
        header_token = request.headers.get("X-Flow-Token")
        if header_token != FLOW_WEBHOOK_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    event = {
        "event_type": data.get("event_type", "product_deleted"),
        "shop": data.get("shop"),
        "product": data.get("product"),
        "user": data.get("user"),
        "deleted_at": data.get("deleted_at"),
        "received_at": datetime.utcnow().isoformat() + "Z",
    }

    app.logger.info("Product deleted event (Flow): %s", event)

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        app.logger.error("Failed to write log file: %s", e)

    return jsonify({"status": "ok"}), 200


@app.route("/shopify/product-deleted-webhook", methods=["POST"])
def product_deleted_webhook():
    """Shopify products/delete webhook."""

    data = request.get_json(silent=True) or {}

    # Store info from headers
    shop_domain = request.headers.get("X-Shopify-Shop-Domain")
    shop_id = request.headers.get("X-Shopify-Shop-Id")

    # Debug logs to Render
    print("WEBHOOK RAW BODY:", data, flush=True)
    print("WEBHOOK SHOP DOMAIN:", shop_domain, flush=True)
    print("WEBHOOK SHOP ID:", shop_id, flush=True)

    app.logger.warning("WEBHOOK RAW BODY: %s", data)
    app.logger.warning("WEBHOOK SHOP DOMAIN: %s", shop_domain)
    app.logger.warning("WEBHOOK SHOP ID: %s", shop_id)

    # Variants and SKUs - this will only work if Shopify actually sends variants
    variants = data.get("variants") or []
    skus = [v.get("sku") for v in variants if v.get("sku")]

    product = {
        "id": data.get("id"),
        "title": data.get("title"),
        "handle": data.get("handle"),
        "vendor": data.get("vendor"),
        "product_type": data.get("product_type"),
        "skus": skus,
    }

    event = {
        "event_type": "product_deleted",
        "shop": {
            "domain": shop_domain,
            "id": shop_id,
        },
        "product": product,
        "payload": data,
        "received_at": datetime.utcnow().isoformat() + "Z",
    }

    app.logger.warning("WEBHOOK PARSED EVENT: %s", event)

    # Write to file
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        app.logger.error("Failed to write log file: %s", e)

    # Send email
    send_deletion_email(event)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
