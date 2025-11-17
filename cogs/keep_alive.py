# keep_alive.py — Flask app (processo principal)
from flask import Flask, jsonify
import os

app = Flask("keep_alive_app")

@app.route("/")
def home():
    return "Bot está rodando!", 200

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

def serve_foreground(app, port=8080):
    # Faz run em foreground (Render espera app rodando em primeiro plano)
    # host 0.0.0.0 para aceitar conexões externas
    print(f"[KEEPALIVE] Servindo Flask em 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
