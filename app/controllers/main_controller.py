from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app.services.gemini_service import gemini_generate_text_result


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


def _local_chatbot_fallback(question: str) -> str:
    q = (question or "").strip().lower()
    if not q:
        return "Please enter a question."
    if "activity cost" in q:
        return "Activity cost is the sum of itinerary ticket prices for all planned activities."
    if "food cost" in q or "hotel cost" in q or "service charge" in q:
        return "Food, hotel, and service charge are estimated separately and then added to total group cost."
    if "budget" in q:
        return "Budget uses transport + hotel + food + activity + service charge, with ML guidance and safety floor values."
    if "trip" in q and "create" in q:
        return "Create a trip from Traveler or Agent module, then the app generates itinerary and budget automatically."
    return "AI response is unavailable now. Please try again in a moment."


@main_bp.route("/chatbot", methods=["GET", "POST"])
@login_required
def chatbot():
    question = ""
    answer = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            api_key = current_app.config.get("GOOGLE_GEMINI_AI_API_KEY")
            model = current_app.config.get("GEMINI_MODEL", "gemini-flash-latest")
            if api_key:
                prompt = (
                    "You are the assistant for AI AIR TRIP PLANNER.\n"
                    "Answer briefly and clearly. If asked about unavailable data, say it honestly.\n\n"
                    f"User question: {question}"
                )
                result = gemini_generate_text_result(
                    prompt=prompt,
                    api_key=api_key,
                    model=model,
                    temperature=0.3,
                )
                answer = result.get("text", "").strip()
                if not answer:
                    status_code = result.get("status_code")
                    error_message = (result.get("error") or "").strip()
                    if status_code == 429:
                        answer = (
                            "Chatbot is unavailable right now because the Gemini API quota is exceeded (HTTP 429). "
                            "Wait a bit or increase API quota/billing, then try again."
                        )
                    elif status_code:
                        answer = f"Chatbot API error ({status_code}). {error_message or 'Please verify API settings.'}"
                    elif error_message:
                        answer = f"Chatbot request failed. {error_message}"
            if not answer:
                answer = _local_chatbot_fallback(question)
    return render_template("chatbot.html", question=question, answer=answer)


@main_bp.route("/docs/<string:name>")
@login_required
def docs(name: str):
    allowed = {
        "auth-security": "01_auth_and_security.pdf",
        "trip-regeneration": "02_trip_generation_and_regeneration.pdf",
        "agent-faq": "03_agent_module_faq.pdf",
        "notifications": "04_notifications_whatsapp_plan.pdf",
        "system-architecture": "05_system_architecture.pdf",
        "recommendations": "06_additional_recommendations.pdf",
    }
    filename = allowed.get((name or "").strip().lower())
    if not filename:
        abort(404)
    pdf_dir = Path(current_app.root_path).parent / "docs" / "pdfs"
    return send_from_directory(pdf_dir, filename)
