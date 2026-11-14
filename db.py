import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "infra_designer.db")


def init_db():
    """Creates the tables if they don't exist yet. Safe to call every run."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_path TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            scan_result_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS questionnaire_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            answers_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            report_text TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    conn.commit()
    conn.close()


def save_project(repo_path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("INSERT INTO projects (repo_path) VALUES (?)", (repo_path,))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def save_scan(project_id, scan_result):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO scans (project_id, scan_result_json) VALUES (?, ?)",
        (project_id, json.dumps(scan_result)),
    )
    conn.commit()
    conn.close()


def save_report(project_id, report_text):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO reports (project_id, report_text) VALUES (?, ?)",
        (project_id, report_text),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database ready at {DB_PATH}")
