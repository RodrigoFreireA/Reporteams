"""Public pages and the authenticated application shell."""

from __future__ import annotations

import os
import urllib.parse

from flask import Blueprint, g, jsonify, redirect, request


def create_public_blueprint(index_html: str, views_dir: str) -> Blueprint:
    blueprint = Blueprint("public", __name__)

    def read_html(path: str):
        with open(path, encoding="utf-8") as html_file:
            return html_file.read(), 200, {"Content-Type": "text/html; charset=utf-8"}

    @blueprint.get("/")
    def index():
        return read_html(index_html)

    @blueprint.get("/login")
    @blueprint.get("/regras-planner")
    @blueprint.get("/dashboard")
    @blueprint.get("/equipes")
    @blueprint.get("/biblioteca")
    def app_route():
        if request.path in {"/regras-planner", "/equipes", "/biblioteca"} and not g.user:
            return redirect(f"/login?next={urllib.parse.quote(request.path)}")
        return read_html(index_html)

    @blueprint.get("/views/<view_name>.html")
    def public_view(view_name: str):
        allowed_views = {"landing": "landing.html", "planner-rules": "planner-rules.html"}
        file_name = allowed_views.get(view_name)
        if not file_name:
            return jsonify({"error": "View nao encontrada."}), 404
        if view_name == "planner-rules" and not g.user:
            return jsonify({"error": "Autenticacao necessaria."}), 401
        return read_html(os.path.join(views_dir, file_name))

    return blueprint
