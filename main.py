# main.py
import os
import time
from flask import Flask, request, jsonify

from quiz_solver import solve_quiz_sequence

SECRET = os.getenv("QUIZ_SECRET", "tds_QZ_Manasvi_27!")

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "TDS quiz solver running. Send POST to /quiz with {email, secret, url}."
    })


@app.route("/quiz", methods=["GET", "POST"])
def quiz_handler():
    if request.method == "GET":
        return jsonify({"message": "Use POST with JSON {email, secret, url}."})

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    email = payload.get("email")
    secret = payload.get("secret")
    url = payload.get("url")

    if not (email and secret and url):
        return jsonify({"error": "Missing fields"}), 400

    if secret != SECRET:
        return jsonify({"error": "Invalid secret"}), 403

    start_ts = time.time()

    try:
        history = solve_quiz_sequence(
            email=email,
            secret=secret,
            first_url=url,
            start_ts=start_ts,
            time_limit=180.0,
        )
    except Exception as e:
        return jsonify({"error": f"Internal error: {e}"}), 500

    return jsonify({"status": "completed", "history": history}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
