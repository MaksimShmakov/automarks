from flask import Blueprint, jsonify


bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return jsonify({"message": "Flask API работает!"})
