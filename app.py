import os
import requests
import base64
import urllib3
import traceback
import time
from flask import Flask, jsonify, render_template, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__, template_folder=".")

CW_SITE        = os.environ.get("CW_SITE", "api-eu.myconnectwise.net")
CW_COMPANY     = os.environ.get("CW_COMPANY", "")
CW_PUBLIC_KEY  = os.environ.get("CW_PUBLIC_KEY", "")
CW_PRIVATE_KEY = os.environ.get("CW_PRIVATE_KEY", "")
CW_CLIENT_ID   = os.environ.get("CW_CLIENT_ID", "")
HTTPS_PROXY    = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
VERIFY_SSL     = os.environ.get("CW_VERIFY_SSL", "true").lower() != "false"
PENDING_CACHE_TTL_SECONDS = int(os.environ.get("PENDING_CACHE_TTL_SECONDS", "20"))
_pending_cache = {"items": None, "timestamp": 0.0}

def get_session():
    s = requests.Session()
    if HTTPS_PROXY:
        s.proxies = {"https": HTTPS_PROXY, "http": HTTPS_PROXY}
    s.verify = VERIFY_SSL
    return s

def get_auth_header():
    creds = f"{CW_COMPANY}+{CW_PUBLIC_KEY}:{CW_PRIVATE_KEY}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "clientId": CW_CLIENT_ID,
        "Content-Type": "application/json"
    }

def cw_get(endpoint, params=None):
    url = f"https://{CW_SITE}/v4_6_release/apis/3.0{endpoint}"
    headers = get_auth_header()
    all_results = []
    page = 1
    page_size = 100
    if params is None: params = {}
    session = get_session()
    while True:
        paged_params = {**params, "page": page, "pageSize": page_size}
        response = session.get(url, headers=headers, params=paged_params, timeout=90)
        response.raise_for_status()
        data = response.json()
        if not data: break
        all_results.extend(data)
        if len(data) < page_size: break
        page += 1
    return all_results

def cw_get_single(endpoint):
    """Helper to fetch a single object safely without pagination."""
    url = f"https://{CW_SITE}/v4_6_release/apis/3.0{endpoint}"
    headers = get_auth_header()
    session = get_session()
    response = session.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

def cw_patch(endpoint, patch_operations):
    url = f"https://{CW_SITE}/v4_6_release/apis/3.0{endpoint}"
    headers = get_auth_header()
    session = get_session()
    response = session.patch(url, headers=headers, json=patch_operations, timeout=30)
    response.raise_for_status()
    return response.json()

def invalidate_pending_cache():
    _pending_cache["items"] = None
    _pending_cache["timestamp"] = 0.0

def build_pending_items():
    # Fetch Open Purchase Orders
    open_pos = cw_get("/procurement/purchaseorders", {"conditions": "closedFlag = false"})
    
    pending_items = []
    so_ids_to_fetch = set()
    
    # Fetch Line Items for each open PO
    for po in open_pos:
        po_id = po.get("id")
        po_number = po.get("poNumber", f"PO-{po_id}")
        vendor = po.get("vendorCompany", {}).get("name", "Unknown Vendor")
        
        line_items = cw_get(f"/procurement/purchaseorders/{po_id}/lineitems")
        
        for item in line_items:
            qty = item.get("quantity", 0)
            received = item.get("receivedQuantity", 0)
            
            # Only keep items that haven't been fully received
            if received < qty and not item.get("canceledFlag") and not item.get("closedFlag"):
                so_id = None
                if item.get("salesOrder") and len(item["salesOrder"]) > 0:
                    so_id = item["salesOrder"][0].get("id")
                    so_ids_to_fetch.add(so_id)
                    
                pending_items.append({
                    "poId": po_id,
                    "poNumber": po_number,
                    "vendor": vendor,
                    "lineItemId": item.get("id"),
                    "description": item.get("description", "Unknown Product"),
                    "quantity": qty,
                    "received": received,
                    "pending": qty - received,
                    "soId": so_id,
                    "company": "Internal Stock / No Sales Order"
                })

    # Batch Fetch Sales Orders to get the Customer Company Name
    if so_ids_to_fetch:
        so_id_list = ",".join(map(str, so_ids_to_fetch))
        sales_orders = cw_get("/sales/orders", {"conditions": f"id in ({so_id_list})"})
        so_map = {so["id"]: so.get("company", {}).get("name", "Unknown Company") for so in sales_orders}
        
        for item in pending_items:
            if item["soId"] and item["soId"] in so_map:
                item["company"] = so_map[item["soId"]]

    # Sort by Customer Company, then PO Number
    pending_items.sort(key=lambda x: (x["company"], x["poId"]))
    return pending_items

def receive_item_payload(payload):
    po_id = payload.get("poId")
    line_item_id = payload.get("lineItemId")
    current_received = payload.get("currentReceived", 0)
    qty_to_receive = payload.get("qtyToReceive", 1)
    serial_numbers = payload.get("serialNumbers", "").strip()

    if not po_id or not line_item_id:
        raise ValueError("poId and lineItemId are required")
    if not isinstance(qty_to_receive, int) or qty_to_receive < 1:
        raise ValueError("qtyToReceive must be a positive integer")

    new_total_received = current_received + qty_to_receive

    # Base PATCH operation for quantity
    patch_ops = [
        {"op": "replace", "path": "receivedQuantity", "value": new_total_received}
    ]
    
    # Optional: Append serial numbers if provided
    if serial_numbers:
        try:
            # Fetch current item to append serials without overwriting existing ones
            current_item = cw_get_single(f"/procurement/purchaseorders/{po_id}/lineitems/{line_item_id}")
            existing_serials = current_item.get("serialNumbers", "")
            
            if existing_serials:
                combined_serials = f"{existing_serials}, {serial_numbers}"
            else:
                combined_serials = serial_numbers
                
            patch_ops.append({"op": "replace", "path": "serialNumbers", "value": combined_serials})
        except Exception as e:
            print(f"Warning: Could not fetch existing serials, overwriting with new: {e}")
            patch_ops.append({"op": "replace", "path": "serialNumbers", "value": serial_numbers})

    # Send PATCH to ConnectWise
    result = cw_patch(f"/procurement/purchaseorders/{po_id}/lineitems/{line_item_id}", patch_ops)
    return result

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/pending-receipts")
def pending_receipts():
    try:
        now = time.time()
        if _pending_cache["items"] is not None and now - _pending_cache["timestamp"] <= PENDING_CACHE_TTL_SECONDS:
            return jsonify({"items": _pending_cache["items"], "cached": True})

        pending_items = build_pending_items()
        _pending_cache["items"] = pending_items
        _pending_cache["timestamp"] = now
        return jsonify({"items": pending_items})

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/api/receive-item", methods=["POST"])
def receive_item():
    try:
        result = receive_item_payload(request.json or {})
        invalidate_pending_cache()
        return jsonify({"success": True, "updatedItem": result})

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/api/receive-items", methods=["POST"])
def receive_items():
    try:
        data = request.json or {}
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"error": "items must be a non-empty array"}), 400

        results = []
        failures = 0
        for payload in items:
            line_item_id = payload.get("lineItemId")
            try:
                updated = receive_item_payload(payload)
                results.append({"lineItemId": line_item_id, "success": True, "updatedItem": updated})
            except Exception as e:
                failures += 1
                results.append({"lineItemId": line_item_id, "success": False, "error": str(e)})

        if failures < len(items):
            invalidate_pending_cache()

        return jsonify({
            "success": failures == 0,
            "results": results,
            "processed": len(items),
            "failed": failures
        }), 207 if failures else 200
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)