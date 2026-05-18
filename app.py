import os
import json
# import uuid
from datetime import datetime

from flask import Flask, request, jsonify, abort  # type: ignore[import]
from werkzeug.exceptions import BadRequest  # type: ignore[import]

app = Flask(__name__)

# ----------------------------
# Configuration
# ----------------------------
# We store data in a JSON text file (no database).
# Requirement: file must be called "courses.json".
DATA_FILE = "courses.json"

VALID_STATUSES = {"Not Started", "In Progress", "Completed"}


# ----------------------------
# File helpers (JSON storage)
# ----------------------------
def ensure_data_file_exists():
    """
    Requirement: Automatically create courses.json if it doesn't exist.
    We store an array of courses in the JSON file.
    """
    if not os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)  # start with an empty list
        except OSError as e:
            # File creation errors should return a 500 response
            raise RuntimeError(f"Could not create {DATA_FILE}: {e}") from e


def load_courses():
    """
    Load courses from courses.json.
    Returns a list of course dicts.
    """
    ensure_data_file_exists()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Basic safety: we expect a list
            if not isinstance(data, list):
                raise ValueError(f"{DATA_FILE} must contain a JSON array.")
            return data
    except (OSError, json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"Could not read/parse {DATA_FILE}: {e}") from e


def save_courses(courses):
    """
    Save courses list into courses.json.
    """
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise RuntimeError(f"Could not write to {DATA_FILE}: {e}") from e


# ----------------------------
# Validation helpers
# ----------------------------
def parse_json_body():
    """
    Read JSON from request safely.
    """
    if not request.is_json:
        abort(400, description="Request body must be JSON.")
    try:
        return request.get_json()
    except BadRequest:
        # werkzeug raises BadRequest for invalid JSON
        abort(400, description="Invalid JSON body.")


def validate_status(status):
    """
    Check status value is one of the allowed values.
    """
    if status not in VALID_STATUSES:
        abort(
            400,
            description=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )


def validate_date_yyyy_mm_dd(date_str):
    """
    Requirement: target_date must be in YYYY-MM-DD format.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        abort(400, description="target_date must be in format YYYY-MM-DD.")


def next_course_id(courses):
    """
    Requirement: id (auto-generated, starting from 1).
    We'll find the max existing id and add 1.
    """
    if not courses:
        return 1
    max_id = max(c.get("id", 0) for c in courses)
    return max_id + 1


def now_iso_timestamp():
    """
    Auto-generated timestamp when the course is created.
    We'll use ISO 8601 format for easy reading.
    """
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_course_by_id(courses, course_id):
    """
    Find a course by id.
    Returns course dict or None.
    """
    for c in courses:
        if c.get("id") == course_id:
            return c
    return None


def required_fields_present(payload, required_fields):
    """
    Helper to detect missing required fields.
    """
    missing = [f for f in required_fields if f not in payload]
    return missing


# ----------------------------
# Error handlers (helpful JSON responses)
# ----------------------------
@app.errorhandler(400)
def handle_400(err):
    return jsonify({"error": "Bad Request", "message": getattr(err, "description", str(err))}), 400


@app.errorhandler(404)
def handle_404(err):
    return jsonify({"error": "Not Found", "message": getattr(err, "description", str(err))}), 404


@app.errorhandler(500)
def handle_500(err):
    # For beginners: return readable message (in production you'd avoid leaking internals)
    return jsonify({
        "error": "Server Error", "message": "Something went wrong.",
        "details": str(err)
    }), 500


# ----------------------------
# Routes / REST API
# ----------------------------
@app.route("/api/courses", methods=["POST"])
def create_course():
    """
    POST /api/courses
    Add a new course.
    Expected JSON:
    {
      "name": "...",
      "description": "...",
      "target_date": "YYYY-MM-DD",
      "status": "Not Started" | "In Progress" | "Completed"
    }
    """
    payload = parse_json_body()

    required = ["name", "description", "target_date", "status"]
    missing = required_fields_present(payload, required)
    if missing:
        abort(
            400, description=f"Missing required fields: {', '.join(missing)}")

    name = payload.get("name")
    description = payload.get("description")
    target_date = payload.get("target_date")
    status = payload.get("status")

    # Validate status and date formats
    if not isinstance(name, str) or not name.strip():
        abort(400, description="name must be a non-empty string.")
    if not isinstance(description, str) or not description.strip():
        abort(400, description="description must be a non-empty string.")

    validate_date_yyyy_mm_dd(target_date)
    validate_status(status)

    try:
        courses = load_courses()
    except RuntimeError as e:
        abort(500, description=str(e))

    # Auto-generate id and created_at
    new_id = next_course_id(courses)
    new_course = {
        "id": new_id,
        "name": name,
        "description": description,
        "target_date": target_date,
        "status": status,
        "created_at": now_iso_timestamp(),
    }

    courses.append(new_course)

    try:
        save_courses(courses)
    except RuntimeError as e:
        abort(500, description=str(e))

    return jsonify(new_course), 201


@app.route("/api/courses", methods=["GET"])
def get_all_courses():
    """
    GET /api/courses
    Get all courses.
    """
    try:
        courses = load_courses()
    except RuntimeError as e:
        abort(500, description=str(e))

    return jsonify(courses), 200


@app.route("/api/courses/<int:course_id>", methods=["GET"])
def get_course(course_id):
    """
    GET /api/courses/<course_id>
    Get a specific course.
    """
    try:
        courses = load_courses()
    except RuntimeError as e:
        abort(500, description=str(e))

    course = get_course_by_id(courses, course_id)
    if not course:
        abort(404, description="Course not found.")

    return jsonify(course), 200


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
def update_course(course_id):
    """
    PUT /api/courses/<course_id>
    Update a course (full update).
    Expected JSON must include all required fields:
    {
      "name": "...",
      "description": "...",
      "target_date": "YYYY-MM-DD",
      "status": "Not Started" | "In Progress" | "Completed"
    }
    """
    payload = parse_json_body()

    required = ["name", "description", "target_date", "status"]
    missing = required_fields_present(payload, required)
    if missing:
        abort(
            400, description=f"Missing required fields: {', '.join(missing)}")

    name = payload.get("name")
    description = payload.get("description")
    target_date = payload.get("target_date")
    status = payload.get("status")

    if not isinstance(name, str) or not name.strip():
        abort(400, description="name must be a non-empty string.")
    if not isinstance(description, str) or not description.strip():
        abort(400, description="description must be a non-empty string.")

    validate_date_yyyy_mm_dd(target_date)
    validate_status(status)

    try:
        courses = load_courses()
    except RuntimeError as e:
        abort(500, description=str(e))

    course = get_course_by_id(courses, course_id)
    if not course:
        abort(404, description="Course not found.")

    # Preserve created_at, update the rest
    course["name"] = name
    course["description"] = description
    course["target_date"] = target_date
    course["status"] = status

    try:
        save_courses(courses)
    except RuntimeError as e:
        abort(500, description=str(e))

    return jsonify(course), 200


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    """
    DELETE /api/courses/<course_id>
    Delete a course.
    """
    try:
        courses = load_courses()
    except RuntimeError as e:
        abort(500, description=str(e))

    course = get_course_by_id(courses, course_id)
    if not course:
        abort(404, description="Course not found.")

    # Remove the matching course
    updated = [c for c in courses if c.get("id") != course_id]

    try:
        save_courses(updated)
    except RuntimeError as e:
        abort(500, description=str(e))

    # No content on success is typical for DELETE, but we can return a message too.
    return jsonify({"message": "Course deleted.", "id": course_id}), 200


# ----------------------------
# App entry point
# ----------------------------
if __name__ == "__main__":
    # Make sure the file exists before serving requests
    ensure_data_file_exists()
    app.run(debug=True)
