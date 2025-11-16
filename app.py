import os
import json
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# Log file path - can change with env var
LOG_FILE = os.environ.get("DELETED_PRODUCTS_LOG_FILE", "deleted_products.log")

# Optional shared secret so only Flow can call it
FLOW_WEBHOOK_TOKEN = os.environ.get("FLOW_WEBHOOK_TOKEN")


@app.route("/", methods=["GET"])
def health():
    return "Shopify product deleted logger is running", 200


@app.route("/shopify/product-deleted", methods=["POST", "GET"])

def product_deleted():
    if request.method == "GET":
        return jsonify({"status": "ok", "info": "GET received on product-deleted endpoint"}), 200
        
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
