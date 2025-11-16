import os
import json
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# Log file path - can change with env var
LOG_FILE = os.environ.get("DELETED_PRODUCTS_LOG_FILE", "deleted_products.log")

# Optional shared secret so only Flow can call it (you can remove if not using Flow anymore)
FLOW_WEBHOOK_TOKEN = os.environ.get("FLOW_WEBHOOK_TOKEN")


@app.route("/", methods=["GET"])
def health():
    return "Shopify product deleted logger is running", 200


@app.route("/shopify/product-deleted", methods=["POST", "GET"])
def product_deleted():
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

    app.logger.info("Product deleted event: %s", event)

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        app.logger.error("Failed to write log file: %s", e)

    return jsonify({"status": "ok"}), 200


@app.route("/shopify/product-deleted-webhook", methods=["POST"])
def product_deleted_webhook():
    # Parse JSON from Shopify
    data = request.get_json(silent=True) or {}

    # Shop domain from headers
    shop_domain = request.headers.get("X-Shopify-Shop-Domain")

    # Debug logs - these should show up in Render
    print("WEBHOOK RAW BODY:", data, flush=True)
    print("WEBHOOK SHOP DOMAIN:", shop_domain, flush=True)

    app.logger.warning("WEBHOOK RAW BODY: %s", data)
    app.logger.warning("WEBHOOK SHOP DOMAIN: %s", shop_domain)

    # Build a simple event (will be improved later)
    product = {
        "id": data.get("id"),
        "title": data.get("title"),
        "handle": data.get("handle"),
        "vendor": data.get("vendor"),
        "product_type": data.get("product_type"),
    }

    event = {
        "event_type": "product_deleted",
        "shop": {"domain": shop_domain},
        "product": product,
        "payload": data,
        "received_at": datetime.utcnow().isoformat() + "Z",
    }

    # Also log the parsed event
    app.logger.warning("WEBHOOK PARSED EVENT: %s", event)

    # Write to file (optional but useful)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        app.logger.error("Failed to write log file: %s", e)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
