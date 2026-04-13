import flask
from flask import redirect, jsonify
import os
import pymongo

app = flask.Flask(__name__)

# --- CONFIGURATION ---
# MongoDB URI should be set in Render Environment Variables
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://student:smartparking@cluster0.z8wvn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
CLUSTER_NAME = "parking_db"
COLLECTION_NAME = "config"

@app.route('/')
def home():
    return "<h1>Smart Parking Gateway is Running</h1><p>Active Redirector.</p>"

@app.route('/qr/<slot_id>')
def qr_redirect(slot_id):
    """
    GATEWAY:
    1. Scan QR (at render url).
    2. Hit this route.
    3. Look up current 'tunnel_url' from MongoDB.
    4. Redirect user to {tunnel_url}/scan/{slot_id} OR /mobile.
    """
    redirect_base = None
    
    # 1. Fetch Tunnel URL from MongoDB
    try:
        client = pymongo.MongoClient(MONGODB_URI)
        db = client[CLUSTER_NAME]
        collection = db[COLLECTION_NAME]
        doc = collection.find_one({"config_id": "main_tunnel"})
        if doc and "tunnel_url" in doc:
            redirect_base = doc["tunnel_url"]
    except Exception as e:
        return f"<h1>Error: MongoDB Lookup Failed</h1><p>{str(e)}</p>", 500

    # 2. Fallback
    if not redirect_base:
        return "<h1>Error: Parking System Offline</h1><p>The local node is not connected to the cloud.</p>", 503

    # 3. Perform Redirect
    if slot_id.lower() == 'app':
        full_url = f"{redirect_base}/mobile"
    else:
        full_url = f"{redirect_base}/scan/{slot_id}"
        
    return redirect(full_url)

if __name__ == '__main__':
    app.run(host = "0.0.0.0", port = 5000, debug=True)
