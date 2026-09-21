import os
import time

import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "guestbook")
DB_USER = os.environ.get("DB_USER", "guestbook")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "guestbook")

# Сколько раз и с каким интервалом пытаться подключиться к БД при старте.
# Полезно, если контейнер приложения стартует раньше, чем PostgreSQL
# готов принимать соединения.
DB_CONNECT_RETRIES = int(os.environ.get("DB_CONNECT_RETRIES", "10"))
DB_CONNECT_DELAY = float(os.environ.get("DB_CONNECT_DELAY", "2"))


def get_connection():
    last_error = None
    for attempt in range(1, DB_CONNECT_RETRIES + 1):
        try:
            return psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
        except psycopg2.OperationalError as exc:
            last_error = exc
            app.logger.warning(
                "Попытка %s/%s подключиться к БД не удалась: %s",
                attempt, DB_CONNECT_RETRIES, exc,
            )
            time.sleep(DB_CONNECT_DELAY)
    raise last_error


def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id SERIAL PRIMARY KEY,
                    author VARCHAR(100) NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()
    finally:
        conn.close()


@app.route("/", methods=["GET"])
def index():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, author, message, created_at "
                "FROM entries ORDER BY created_at DESC;"
            )
            entries = cur.fetchall()
    finally:
        conn.close()
    return render_template("index.html", entries=entries)


@app.route("/add", methods=["POST"])
def add_entry():
    author = request.form.get("author", "").strip() or "Аноним"
    message = request.form.get("message", "").strip()

    if not message:
        return redirect(url_for("index"))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO entries (author, message) VALUES (%s, %s);",
                (author, message),
            )
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("index"))


@app.route("/health", methods=["GET"])
def health():
    # Отдельный эндпоинт для проверки, что приложение живо И база доступна.
    try:
        conn = get_connection()
        conn.close()
        return {"status": "ok"}, 200
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}, 503


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
