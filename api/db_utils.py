import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

from api.collections import DEFAULT_COLLECTION, normalize_collection
from api.settings import settings

__all__ = ["DEFAULT_COLLECTION", "normalize_collection"]

DB_NAME = settings.sqlite_db_path

_CREATE_APP_LOGS_TABLE = (
    "CREATE TABLE IF NOT EXISTS application_logs "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "session_id TEXT, user_query TEXT, gpt_response TEXT, "
    "model TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_DOC_STORE_TABLE = (
    "CREATE TABLE IF NOT EXISTS document_store "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "filename TEXT, collection TEXT NOT NULL DEFAULT 'default', "
    "sha256 TEXT, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_DOC_SOURCES_TABLE = (
    "CREATE TABLE IF NOT EXISTS document_sources "
    "(file_id INTEGER PRIMARY KEY REFERENCES document_store(id) ON DELETE CASCADE, "
    "source_text TEXT NOT NULL, "
    "strategy TEXT NOT NULL DEFAULT 'recursive', "
    "chunk_size INTEGER NOT NULL DEFAULT 1000, "
    "chunk_overlap INTEGER NOT NULL DEFAULT 200, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_DOC_SOURCE = (
    "INSERT INTO document_sources "
    "(file_id, source_text, strategy, chunk_size, chunk_overlap) VALUES (?, ?, ?, ?, ?) "
    "ON CONFLICT(file_id) DO UPDATE SET "
    "source_text=excluded.source_text, strategy=excluded.strategy, "
    "chunk_size=excluded.chunk_size, chunk_overlap=excluded.chunk_overlap, "
    "updated_at=CURRENT_TIMESTAMP"
)

_SELECT_DOC_SOURCE = (
    "SELECT file_id, source_text, strategy, chunk_size, chunk_overlap, updated_at "
    "FROM document_sources WHERE file_id = ?"
)
_SELECT_DOC_SOURCES_BY_COLLECTION = (
    "SELECT ds.file_id, ds.source_text, ds.strategy, ds.chunk_size, "
    "ds.chunk_overlap, ds.updated_at, d.filename, d.collection "
    "FROM document_sources ds "
    "JOIN document_store d ON ds.file_id = d.id "
    "WHERE d.collection = ? "
    "ORDER BY ds.file_id ASC"
)

_DELETE_DOC_SOURCE = "DELETE FROM document_sources WHERE file_id = ?"
_DELETE_DOC_SOURCES_BY_COLLECTION = (
    "DELETE FROM document_sources "
    "WHERE file_id IN (SELECT id FROM document_store WHERE collection = ?)"
)

_CREATE_SESSION_LABELS_TABLE = (
    "CREATE TABLE IF NOT EXISTS session_labels "
    "(session_id TEXT PRIMARY KEY, label TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'active', "
    "tags TEXT NOT NULL DEFAULT '', "
    "summary TEXT DEFAULT '', "
    "resolution_notes TEXT DEFAULT '', "
    "priority TEXT NOT NULL DEFAULT 'medium', "
    "assigned_agent TEXT DEFAULT NULL, "
    "escalation_tier TEXT NOT NULL DEFAULT 'tier_1')"
)

_CREATE_SLA_POLICIES_TABLE = (
    "CREATE TABLE IF NOT EXISTS sla_policies ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "name TEXT NOT NULL, "
    "priority TEXT NOT NULL, "
    "category TEXT NOT NULL DEFAULT 'general', "
    "response_time_minutes INTEGER NOT NULL, "
    "resolution_time_minutes INTEGER NOT NULL, "
    "is_active INTEGER NOT NULL DEFAULT 1, "
    "use_business_hours INTEGER NOT NULL DEFAULT 0, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_SLA_POLICY_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sla_policies_prio_cat "
    "ON sla_policies(priority, category)"
)

_INSERT_SLA_POLICY = (
    "INSERT INTO sla_policies "
    "(name, priority, category, response_time_minutes, resolution_time_minutes, "
    "is_active, use_business_hours) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_SELECT_SLA_POLICY_BY_ID = (
    "SELECT id, name, priority, category, response_time_minutes, "
    "resolution_time_minutes, is_active, use_business_hours, created_at, updated_at "
    "FROM sla_policies WHERE id = ?"
)
_DELETE_SLA_POLICY = "DELETE FROM sla_policies WHERE id = ?"

_CREATE_SUPPORT_AGENTS_TABLE = (
    "CREATE TABLE IF NOT EXISTS support_agents ("
    "id TEXT PRIMARY KEY, "
    "name TEXT NOT NULL, "
    "email TEXT NOT NULL, "
    "tier TEXT NOT NULL DEFAULT 'tier_1', "
    "department TEXT NOT NULL DEFAULT 'general_leasing', "
    "is_active INTEGER NOT NULL DEFAULT 1, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_SESSION_ASSIGNMENT_HISTORY_TABLE = (
    "CREATE TABLE IF NOT EXISTS session_assignment_history ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "session_id TEXT NOT NULL, "
    "assigned_by TEXT DEFAULT 'system', "
    "previous_agent TEXT DEFAULT NULL, "
    "new_agent TEXT DEFAULT NULL, "
    "previous_tier TEXT DEFAULT 'tier_1', "
    "new_tier TEXT NOT NULL DEFAULT 'tier_1', "
    "reason TEXT DEFAULT '', "
    "assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_SUPPORT_AGENT = (
    "INSERT INTO support_agents "
    "(id, name, email, tier, department, is_active) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_SELECT_SUPPORT_AGENT_BY_ID = (
    "SELECT id, name, email, tier, department, is_active, created_at, updated_at "
    "FROM support_agents WHERE id = ?"
)

_DELETE_SUPPORT_AGENT = "DELETE FROM support_agents WHERE id = ?"

_INSERT_ASSIGNMENT_HISTORY = (
    "INSERT INTO session_assignment_history "
    "(session_id, assigned_by, previous_agent, new_agent, previous_tier, new_tier, reason) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_ASSIGNMENT_HISTORY = (
    "SELECT id, session_id, assigned_by, previous_agent, new_agent, "
    "previous_tier, new_tier, reason, assigned_at "
    "FROM session_assignment_history WHERE session_id = ? "
    "ORDER BY id DESC LIMIT ?"
)

_CREATE_FEEDBACK_TABLE = (
    "CREATE TABLE IF NOT EXISTS feedback ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "session_id TEXT NOT NULL, rating INTEGER NOT NULL, "
    "comment TEXT, "
    "score INTEGER DEFAULT NULL, "
    "resolution_satisfaction INTEGER DEFAULT NULL, "
    "agent_helpfulness INTEGER DEFAULT NULL, "
    "response_speed INTEGER DEFAULT NULL, "
    "review_status TEXT NOT NULL DEFAULT 'pending_review', "
    "assigned_agent TEXT DEFAULT NULL, "
    "escalation_tier TEXT NOT NULL DEFAULT 'tier_1', "
    "reviewer_notes TEXT DEFAULT NULL, "
    "reviewed_at TEXT DEFAULT NULL, "
    "reviewed_by TEXT DEFAULT NULL, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_FEEDBACK = "INSERT INTO feedback (session_id, rating, comment) VALUES (?, ?, ?)"

_SELECT_FEEDBACK_COUNT = "SELECT COUNT(*) FROM feedback WHERE rating = ?"

_CREATE_WEBHOOKS_TABLE = (
    "CREATE TABLE IF NOT EXISTS webhooks ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "url TEXT NOT NULL, "
    "events TEXT NOT NULL DEFAULT '*', "
    "secret TEXT DEFAULT '', "
    "is_active INTEGER NOT NULL DEFAULT 1, "
    "failure_count INTEGER NOT NULL DEFAULT 0, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_CREATE_WEBHOOK_DELIVERY_LOGS_TABLE = (
    "CREATE TABLE IF NOT EXISTS webhook_delivery_logs ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "webhook_id INTEGER NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE, "
    "event TEXT NOT NULL, "
    "url TEXT NOT NULL, "
    "status_code INTEGER, "
    "success INTEGER NOT NULL, "
    "payload_preview TEXT, "
    "error_message TEXT, "
    "delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

_INSERT_WEBHOOK = (
    "INSERT INTO webhooks (url, events, secret, is_active, failure_count) "
    "VALUES (?, ?, ?, ?, 0)"
)
_SELECT_WEBHOOK_BY_ID = (
    "SELECT id, url, events, secret, is_active, failure_count, created_at "
    "FROM webhooks WHERE id = ?"
)
_DELETE_WEBHOOK = "DELETE FROM webhooks WHERE id = ?"
_DELETE_WEBHOOK_LOGS_BY_WEBHOOK = "DELETE FROM webhook_delivery_logs WHERE webhook_id = ?"
_INSERT_WEBHOOK_DELIVERY = (
    "INSERT INTO webhook_delivery_logs "
    "(webhook_id, event, url, status_code, success, payload_preview, error_message) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_INCREMENT_WEBHOOK_FAILURE = (
    "UPDATE webhooks SET failure_count = failure_count + 1 WHERE id = ?"
)
_RESET_WEBHOOK_FAILURE = (
    "UPDATE webhooks SET failure_count = 0 WHERE id = ?"
)

_CREATE_SUPPORT_MACROS_TABLE = (
    "CREATE TABLE IF NOT EXISTS support_macros ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "title TEXT NOT NULL, "
    "shortcut TEXT NOT NULL UNIQUE, "
    "category TEXT NOT NULL DEFAULT 'General', "
    "content TEXT NOT NULL, "
    "tags TEXT NOT NULL DEFAULT '', "
    "status_action TEXT, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_MACRO_CATEGORY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_support_macros_category ON support_macros(category)"
)
_CREATE_MACRO_SHORTCUT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_support_macros_shortcut ON support_macros(shortcut)"
)

_INSERT_SUPPORT_MACRO = (
    "INSERT INTO support_macros (title, shortcut, category, content, tags, status_action) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
_SELECT_MACRO_BY_ID = (
    "SELECT id, title, shortcut, category, content, tags, status_action, created_at, updated_at "
    "FROM support_macros WHERE id = ?"
)
_SELECT_MACRO_BY_SHORTCUT = (
    "SELECT id, title, shortcut, category, content, tags, status_action, created_at, updated_at "
    "FROM support_macros WHERE LOWER(shortcut) = LOWER(?)"
)
_DELETE_SUPPORT_MACRO = "DELETE FROM support_macros WHERE id = ?"
_SELECT_MACRO_CATEGORIES = (
    "SELECT DISTINCT category FROM support_macros ORDER BY category ASC"
)

MAX_MACRO_TITLE_LENGTH = 100
MAX_MACRO_SHORTCUT_LENGTH = 50
MAX_MACRO_CATEGORY_LENGTH = 50
MAX_MACRO_CONTENT_LENGTH = 4000
MAX_MACRO_TAGS_LENGTH = 200

VALID_WEBHOOK_EVENTS = {
    "*",
    "session.escalated",
    "session.resolved",
    "feedback.negative",
    "feedback.low_csat",
    "ping",
    "sla.approaching_breach",
    "sla.breached",
    "session.assigned",
    "session.tier_escalated",
    "knowledge.gap_detected",
    "knowledge.article_published",
}

_CREATE_KNOWLEDGE_GAPS_TABLE = (
    "CREATE TABLE IF NOT EXISTS knowledge_gaps ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "query TEXT NOT NULL, "
    "normalized_query TEXT NOT NULL, "
    "category TEXT NOT NULL DEFAULT 'general', "
    "source_type TEXT NOT NULL DEFAULT 'unanswered_query', "
    "session_id TEXT DEFAULT NULL, "
    "frequency INTEGER NOT NULL DEFAULT 1, "
    "priority TEXT NOT NULL DEFAULT 'medium', "
    "status TEXT NOT NULL DEFAULT 'open', "
    "linked_article_id INTEGER DEFAULT NULL, "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_KNOWLEDGE_GAP_NORM_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_norm_query "
    "ON knowledge_gaps(normalized_query)"
)

VALID_KNOWLEDGE_GAP_STATUSES = {"open", "drafting", "resolved", "dismissed"}
DEFAULT_KNOWLEDGE_GAP_STATUS = "open"
VALID_KNOWLEDGE_GAP_SOURCES = {
    "unanswered_query",
    "low_csat",
    "escalated_session",
    "manual",
}
DEFAULT_KNOWLEDGE_GAP_SOURCE = "unanswered_query"
VALID_KNOWLEDGE_CATEGORIES = {
    "general",
    "maintenance",
    "lease",
    "billing",
    "policy",
}
DEFAULT_KNOWLEDGE_CATEGORY = "general"
MAX_KNOWLEDGE_QUERY_LENGTH = 500
MAX_KNOWLEDGE_NOTES_LENGTH = 2000

_CREATE_KNOWLEDGE_ARTICLES_TABLE = (
    "CREATE TABLE IF NOT EXISTS knowledge_articles ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "title TEXT NOT NULL, "
    "category TEXT NOT NULL DEFAULT 'general', "
    "question_pattern TEXT NOT NULL DEFAULT '', "
    "content_markdown TEXT NOT NULL, "
    "tags TEXT NOT NULL DEFAULT '', "
    "source_session_id TEXT DEFAULT NULL, "
    "source_gap_id INTEGER DEFAULT NULL, "
    "status TEXT NOT NULL DEFAULT 'draft', "
    "author TEXT NOT NULL DEFAULT 'support_agent', "
    "published_file_id INTEGER DEFAULT NULL, "
    "published_collection TEXT DEFAULT NULL, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_KNOWLEDGE_ARTICLE_CAT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_knowledge_articles_category "
    "ON knowledge_articles(category)"
)

VALID_KNOWLEDGE_ARTICLE_STATUSES = {"draft", "published", "archived"}
DEFAULT_KNOWLEDGE_ARTICLE_STATUS = "draft"
MAX_KNOWLEDGE_TITLE_LENGTH = 200
MAX_KNOWLEDGE_CONTENT_LENGTH = 15000
MAX_KNOWLEDGE_TAGS_LENGTH = 300
MAX_KNOWLEDGE_AUTHOR_LENGTH = 100
MAX_WEBHOOK_URL_LENGTH = 500
MAX_WEBHOOK_SECRET_LENGTH = 256
MAX_DELIVERY_PREVIEW_LENGTH = 500
MAX_DELIVERY_ERROR_LENGTH = 500

VALID_FEEDBACK_REVIEW_STATUSES = {
    "pending_review",
    "reviewed",
    "followup_required",
    "archived",
}
DEFAULT_FEEDBACK_REVIEW_STATUS = "pending_review"
MAX_REVIEWER_NOTES_LENGTH = 2000
MAX_REVIEWED_BY_LENGTH = 100

MAX_SESSION_LABEL_LENGTH = 80
VALID_SESSION_STATUSES = {"active", "resolved", "escalated", "closed"}
VALID_SESSION_PRIORITIES = {"urgent", "high", "medium", "low"}
DEFAULT_SESSION_PRIORITY = "medium"
MAX_SESSION_TAGS_LENGTH = 200
MAX_SESSION_SUMMARY_LENGTH = 2000
MAX_RESOLUTION_NOTES_LENGTH = 2000

VALID_AGENT_TIERS = {"tier_1", "tier_2", "tier_3"}
DEFAULT_AGENT_TIER = "tier_1"
VALID_AGENT_DEPARTMENTS = {"general_leasing", "maintenance", "billing", "management"}
DEFAULT_AGENT_DEPARTMENT = "general_leasing"
MAX_AGENT_ID_LENGTH = 50
MAX_AGENT_NAME_LENGTH = 100
MAX_AGENT_EMAIL_LENGTH = 150
MAX_ASSIGNMENT_REASON_LENGTH = 500

DEFAULT_SUPPORT_AGENTS = [
    ("agent_sarah", "Sarah Connor", "sarah.connor@example.com", "tier_1", "general_leasing", 1),
    ("agent_david", "David Miller", "david.miller@example.com", "tier_1", "maintenance", 1),
    ("agent_elena", "Elena Vance", "elena.vance@example.com", "tier_2", "maintenance", 1),
    ("agent_marcus", "Marcus Brody", "marcus.brody@example.com", "tier_2", "billing", 1),
    ("agent_rachel", "Rachel Green", "rachel.green@example.com", "tier_3", "management", 1),
]

MAX_SLA_POLICY_NAME_LENGTH = 100
MAX_SLA_CATEGORY_LENGTH = 50

DEFAULT_SLA_POLICIES = [
    ("Urgent Maintenance SLA", "urgent", "maintenance", 15, 120, 1, 0),
    ("Urgent General SLA", "urgent", "general", 30, 240, 1, 0),
    ("High Maintenance SLA", "high", "maintenance", 60, 480, 1, 0),
    ("High General SLA", "high", "general", 120, 720, 1, 1),
    ("Medium General SLA", "medium", "general", 240, 1440, 1, 1),
    ("Low General SLA", "low", "general", 1440, 2880, 1, 1),
]

_INSERT_APP_LOG = (
    "INSERT INTO application_logs (session_id, user_query, gpt_response, model) VALUES (?, ?, ?, ?)"
)

_SELECT_CHAT_HISTORY = (
    "SELECT user_query, gpt_response FROM application_logs "
    "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
)
_SELECT_LATEST_USER_QUERY = (
    "SELECT user_query FROM application_logs "
    "WHERE session_id = ? ORDER BY id DESC LIMIT 1"
)

_INSERT_DOC_RECORD = "INSERT INTO document_store (filename, collection, sha256) VALUES (?, ?, ?)"
_SELECT_DOC_BY_HASH = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "WHERE sha256 = ? ORDER BY id ASC LIMIT 1"
)
_SELECT_DOC_BY_ID = (
    "SELECT id, filename, collection, upload_timestamp, sha256 FROM document_store "
    "WHERE id = ? LIMIT 1"
)
_SELECT_DOC_RECORD = _SELECT_DOC_BY_ID
_DELETE_DOC_RECORD = "DELETE FROM document_store WHERE id = ?"
_SELECT_ALL_DOCS = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store ORDER BY id DESC"
)
_SELECT_DOCS_BY_COLLECTION = (
    "SELECT id, filename, collection, upload_timestamp FROM document_store "
    "WHERE collection = ? ORDER BY id DESC"
)
_RENAME_COLLECTION = "UPDATE document_store SET collection = ? WHERE collection = ?"
_DELETE_DOCS_BY_COLLECTION = "DELETE FROM document_store WHERE collection = ?"

_SELECT_ALL_COLLECTIONS = "SELECT DISTINCT collection FROM document_store ORDER BY collection"

_SELECT_ALL_SESSIONS_BASE = (
    "SELECT l1.session_id, COUNT(*) AS message_count, "
    "MAX(l1.created_at) AS last_active, "
    "(SELECT l2.user_query FROM application_logs l2 "
    "WHERE l2.session_id = l1.session_id ORDER BY l2.id ASC LIMIT 1) AS preview, "
    "(SELECT label FROM session_labels WHERE session_id = l1.session_id) AS label, "
    "COALESCE("
    "(SELECT status FROM session_labels WHERE session_id = l1.session_id), 'active'"
    ") AS status, "
    "COALESCE((SELECT tags FROM session_labels WHERE session_id = l1.session_id), '') AS tags, "
    "COALESCE("
    "(SELECT summary FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS summary, "
    "COALESCE("
    "(SELECT resolution_notes FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS resolution_notes, "
    "COALESCE("
    "(SELECT priority FROM session_labels WHERE session_id = l1.session_id), 'medium'"
    ") AS priority, "
    "(SELECT assigned_agent FROM session_labels "
    "WHERE session_id = l1.session_id) AS assigned_agent, "
    "COALESCE("
    "(SELECT escalation_tier FROM session_labels WHERE session_id = l1.session_id), 'tier_1'"
    ") AS escalation_tier "
    "FROM application_logs l1 GROUP BY l1.session_id"
)
_SELECT_ALL_SESSIONS = _SELECT_ALL_SESSIONS_BASE + " ORDER BY last_active DESC"

_SEARCH_SESSIONS = (
    "SELECT l1.session_id, COUNT(*) AS match_count, "
    "MAX(l1.created_at) AS last_active, "
    "(SELECT l2.user_query FROM application_logs l2 "
    "WHERE l2.session_id = l1.session_id ORDER BY l2.id ASC LIMIT 1) AS preview, "
    "(SELECT label FROM session_labels WHERE session_id = l1.session_id) AS label, "
    "COALESCE("
    "(SELECT status FROM session_labels WHERE session_id = l1.session_id), 'active'"
    ") AS status, "
    "COALESCE((SELECT tags FROM session_labels WHERE session_id = l1.session_id), '') AS tags, "
    "COALESCE("
    "(SELECT summary FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS summary, "
    "COALESCE("
    "(SELECT resolution_notes FROM session_labels WHERE session_id = l1.session_id), ''"
    ") AS resolution_notes, "
    "COALESCE("
    "(SELECT priority FROM session_labels WHERE session_id = l1.session_id), 'medium'"
    ") AS priority, "
    "(SELECT assigned_agent FROM session_labels "
    "WHERE session_id = l1.session_id) AS assigned_agent, "
    "COALESCE("
    "(SELECT escalation_tier FROM session_labels WHERE session_id = l1.session_id), 'tier_1'"
    ") AS escalation_tier "
    "FROM application_logs l1 "
    "WHERE l1.user_query LIKE ? OR l1.gpt_response LIKE ? "
    "GROUP BY l1.session_id ORDER BY last_active DESC LIMIT ?"
)

_SELECT_MATCHED_QUERIES = (
    "SELECT DISTINCT user_query FROM application_logs "
    "WHERE session_id = ? AND (user_query LIKE ? OR gpt_response LIKE ?) "
    "ORDER BY id ASC LIMIT 3"
)

_DELETE_SESSION = "DELETE FROM application_logs WHERE session_id = ?"
_DELETE_SESSION_LABEL = "DELETE FROM session_labels WHERE session_id = ?"
_DELETE_SESSION_FEEDBACK = "DELETE FROM feedback WHERE session_id = ?"
_STALE_SESSIONS = (
    "SELECT session_id FROM application_logs GROUP BY session_id HAVING MAX(created_at) < ?"
)
_UPSERT_SESSION_LABEL = (
    "INSERT INTO session_labels (session_id, label) VALUES (?, ?) "
    "ON CONFLICT(session_id) DO UPDATE SET label = excluded.label"
)
_SESSION_HAS_LOGS = "SELECT 1 FROM application_logs WHERE session_id = ? LIMIT 1"


def normalize_session_label(value: str | None) -> str:
    """Validate a session label, raising ValueError if blank or too long."""
    label = (value or "").strip()
    if not label:
        raise ValueError("Session label must not be blank.")
    if len(label) > MAX_SESSION_LABEL_LENGTH:
        raise ValueError(f"Session label must be at most {MAX_SESSION_LABEL_LENGTH} characters.")
    return label


def normalize_session_status(value: str | None) -> str:
    status = (value or "active").strip().lower()
    if status not in VALID_SESSION_STATUSES:
        raise ValueError(
            f"Invalid session status '{status}'. Must be one of: {sorted(VALID_SESSION_STATUSES)}."
        )
    return status


def normalize_session_tags(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        tags_list = [t.strip().lower() for t in value if t and t.strip()]
        tags_str = ", ".join(sorted(set(tags_list)))
    else:
        tags_list = [t.strip().lower() for t in value.split(",") if t and t.strip()]
        tags_str = ", ".join(sorted(set(tags_list)))
    if len(tags_str) > MAX_SESSION_TAGS_LENGTH:
        raise ValueError(f"Session tags must be at most {MAX_SESSION_TAGS_LENGTH} characters.")
    return tags_str


def normalize_session_summary(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) > MAX_SESSION_SUMMARY_LENGTH:
        raise ValueError(
            f"Session summary must be at most {MAX_SESSION_SUMMARY_LENGTH} characters."
        )
    return cleaned


def normalize_resolution_notes(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) > MAX_RESOLUTION_NOTES_LENGTH:
        raise ValueError(
            f"Resolution notes must be at most {MAX_RESOLUTION_NOTES_LENGTH} characters."
        )
    return cleaned


def normalize_session_priority(value: str | None) -> str:
    """Validate a session priority, defaulting to 'medium' or raising ValueError if invalid."""
    if value is None:
        return DEFAULT_SESSION_PRIORITY
    clean = str(value).strip().lower()
    if not clean:
        return DEFAULT_SESSION_PRIORITY
    if clean not in VALID_SESSION_PRIORITIES:
        valid_opts = sorted(VALID_SESSION_PRIORITIES)
        raise ValueError(f"Invalid session priority '{value}'. Must be one of: {valid_opts}.")
    return clean


def normalize_agent_id(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        raise ValueError("Agent ID must not be blank.")
    if len(cleaned) > MAX_AGENT_ID_LENGTH:
        raise ValueError(f"Agent ID must be at most {MAX_AGENT_ID_LENGTH} characters.")
    return cleaned


def normalize_agent_name(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Agent name must not be blank.")
    if len(cleaned) > MAX_AGENT_NAME_LENGTH:
        raise ValueError(f"Agent name must be at most {MAX_AGENT_NAME_LENGTH} characters.")
    return cleaned


def normalize_agent_email(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        raise ValueError("Agent email must not be blank.")
    if "@" not in cleaned or "." not in cleaned:
        raise ValueError("Agent email must be a valid email address.")
    if len(cleaned) > MAX_AGENT_EMAIL_LENGTH:
        raise ValueError(f"Agent email must be at most {MAX_AGENT_EMAIL_LENGTH} characters.")
    return cleaned


def normalize_agent_tier(value: str | None) -> str:
    cleaned = (value or DEFAULT_AGENT_TIER).strip().lower()
    if cleaned not in VALID_AGENT_TIERS:
        raise ValueError(
            f"Invalid agent tier '{value}'. Must be one of: {sorted(VALID_AGENT_TIERS)}."
        )
    return cleaned


def normalize_agent_department(value: str | None) -> str:
    cleaned = (value or DEFAULT_AGENT_DEPARTMENT).strip().lower()
    if cleaned not in VALID_AGENT_DEPARTMENTS:
        valid_depts = sorted(VALID_AGENT_DEPARTMENTS)
        raise ValueError(f"Invalid agent department '{value}'. Must be one of: {valid_depts}.")
    return cleaned


def normalize_feedback_review_status(value: str | None) -> str:
    cleaned = (value or DEFAULT_FEEDBACK_REVIEW_STATUS).strip().lower()
    if cleaned not in VALID_FEEDBACK_REVIEW_STATUSES:
        valid_statuses = sorted(VALID_FEEDBACK_REVIEW_STATUSES)
        raise ValueError(
            f"Invalid review status '{value}'. Must be one of: {valid_statuses}."
        )
    return cleaned


def normalize_csat_score(value: int | None, allow_none: bool = True) -> int | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError("CSAT score must not be None.")
    try:
        score_int = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("CSAT score must be an integer between 1 and 5.") from exc

    min_csat_score = 1
    max_csat_score = 5
    if not (min_csat_score <= score_int <= max_csat_score):
        raise ValueError("CSAT score must be between 1 and 5.")
    return score_int


def normalize_reviewer_notes(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) > MAX_REVIEWER_NOTES_LENGTH:
        raise ValueError(
            f"Reviewer notes must be at most {MAX_REVIEWER_NOTES_LENGTH} characters."
        )
    return cleaned


def normalize_webhook_url(value: str | None) -> str:
    """Validate webhook URL, ensuring http/https scheme and reasonable length."""
    url = (value or "").strip()
    if not url:
        raise ValueError("Webhook URL must not be blank.")
    if len(url) > MAX_WEBHOOK_URL_LENGTH:
        raise ValueError(f"Webhook URL must be at most {MAX_WEBHOOK_URL_LENGTH} characters.")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Webhook URL must start with 'http://' or 'https://'.")
    return url


def normalize_webhook_events(value: str | list[str] | None) -> str:
    """Validate subscribed events, returning comma-separated canonical string."""
    if value is None:
        return "*"
    if isinstance(value, list):
        raw_events = [ev.strip().lower() for ev in value if ev and ev.strip()]
    else:
        raw_events = [ev.strip().lower() for ev in value.split(",") if ev and ev.strip()]

    if not raw_events:
        return "*"
    if "*" in raw_events:
        return "*"

    for ev in raw_events:
        if ev not in VALID_WEBHOOK_EVENTS:
            raise ValueError(
                f"Invalid webhook event '{ev}'. Valid events are: {sorted(VALID_WEBHOOK_EVENTS)}."
            )

    return ", ".join(sorted(set(raw_events)))


def normalize_webhook_secret(value: str | None) -> str:
    """Validate optional HMAC secret string."""
    if value is None:
        return ""
    secret = value.strip()
    if len(secret) > MAX_WEBHOOK_SECRET_LENGTH:
        raise ValueError(
            f"Webhook secret must be at most {MAX_WEBHOOK_SECRET_LENGTH} characters."
        )
    return secret


def normalize_macro_title(value: str | None) -> str:
    """Validate macro title, raising ValueError if blank or too long."""
    title = (value or "").strip()
    if not title:
        raise ValueError("Macro title must not be blank.")
    if len(title) > MAX_MACRO_TITLE_LENGTH:
        raise ValueError(f"Macro title must be at most {MAX_MACRO_TITLE_LENGTH} characters.")
    return title


def normalize_macro_shortcut(value: str | None) -> str:
    """Validate macro shortcut, ensuring slash prefix and alphanumeric characters."""
    raw = (value or "").strip().lower()
    if not raw:
        raise ValueError("Macro shortcut must not be blank.")
    shortcut = raw if raw.startswith("/") else f"/{raw}"
    if len(shortcut) > MAX_MACRO_SHORTCUT_LENGTH:
        raise ValueError(
            f"Macro shortcut must be at most {MAX_MACRO_SHORTCUT_LENGTH} characters."
        )
    identifier = shortcut[1:]
    if not identifier or not all(c.isalnum() or c in "-_" for c in identifier):
        raise ValueError(
            "Macro shortcut must contain only alphanumeric characters, hyphens, and underscores."
        )
    return shortcut


def normalize_macro_category(value: str | None) -> str:
    """Validate macro category, defaulting to 'General' if blank."""
    category = (value or "").strip()
    if not category:
        return "General"
    if len(category) > MAX_MACRO_CATEGORY_LENGTH:
        raise ValueError(
            f"Macro category must be at most {MAX_MACRO_CATEGORY_LENGTH} characters."
        )
    return category


def normalize_macro_content(value: str | None) -> str:
    """Validate macro content, raising ValueError if blank or too long."""
    content = (value or "").strip()
    if not content:
        raise ValueError("Macro content must not be blank.")
    if len(content) > MAX_MACRO_CONTENT_LENGTH:
        raise ValueError(
            f"Macro content must be at most {MAX_MACRO_CONTENT_LENGTH} characters."
        )
    return content


def normalize_macro_status_action(value: str | None) -> str | None:
    """Validate optional status action against valid session statuses."""
    if not value or not str(value).strip():
        return None
    status = str(value).strip().lower()
    if status not in VALID_SESSION_STATUSES:
        valid_options = ", ".join(sorted(VALID_SESSION_STATUSES))
        raise ValueError(f"Invalid status_action '{value}'. Must be one of: {valid_options}")
    return status


PREVIEW_MAX_LENGTH = 80


def get_db_connection():
    db_path = Path(DB_NAME)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def ping_db() -> None:
    """Verify database connectivity with a cheap query (used by readiness)."""
    with closing(get_db_connection()) as conn:
        conn.execute("SELECT 1").fetchone()


def create_application_logs():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_APP_LOGS_TABLE)
        conn.commit()


def insert_application_logs(session_id, user_query, gpt_response, model):
    with closing(get_db_connection()) as conn:
        conn.execute(_INSERT_APP_LOG, (session_id, user_query, gpt_response, model))
        conn.commit()


def get_chat_history(session_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_CHAT_HISTORY, (session_id,))
        messages = []
        for row in cursor.fetchall():
            messages.extend(
                [
                    {"role": "human", "content": row["user_query"]},
                    {"role": "ai", "content": row["gpt_response"]},
                ]
            )
        return messages


def get_session_latest_user_query(session_id: str | None) -> str | None:
    """Return the most recent user query for a given session, or None if no queries exist."""
    if not session_id or not session_id.strip():
        return None
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_LATEST_USER_QUERY, (session_id.strip(),))
        row = cursor.fetchone()
        if row and row["user_query"]:
            return str(row["user_query"])
    return None


def truncate_history(messages, max_turns):
    """Keep only the most recent turns (a turn is one human+AI pair)."""
    if max_turns is None or max_turns <= 0:
        return messages
    return messages[-2 * max_turns :]


def create_document_store():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_DOC_STORE_TABLE)
        conn.execute(_CREATE_DOC_SOURCES_TABLE)
        conn.commit()


def migrate_document_store():
    """Add newer columns to pre-existing databases (no-op otherwise)."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_DOC_SOURCES_TABLE)
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(document_store)")]
        if "collection" not in columns:
            conn.execute(
                "ALTER TABLE document_store ADD COLUMN collection TEXT NOT NULL DEFAULT 'default'"
            )
        if "sha256" not in columns:
            conn.execute("ALTER TABLE document_store ADD COLUMN sha256 TEXT")
        conn.commit()


def insert_document_record(filename, collection=DEFAULT_COLLECTION, sha256=None):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_DOC_RECORD, (filename, collection, sha256))
        file_id = cursor.lastrowid
        conn.commit()
        return file_id


def get_document_by_hash(sha256):
    """Return the earliest document with identical content, if any."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_DOC_BY_HASH, (sha256,))
        document = cursor.fetchone()
        return dict(document) if document else None


def get_document_record(file_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_DOC_RECORD, (file_id,))
        document = cursor.fetchone()
        return dict(document) if document else None


def delete_document_record(file_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOC_RECORD, (file_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


def save_document_source(
    file_id,
    source_text,
    strategy="recursive",
    chunk_size=1000,
    chunk_overlap=200,
):
    """Insert or refresh the stored source text and chunking options for a document."""
    with closing(get_db_connection()) as conn:
        conn.execute(
            _INSERT_DOC_SOURCE,
            (file_id, source_text, strategy, chunk_size, chunk_overlap),
        )
        conn.commit()


def get_document_source(file_id):
    """Return the stored source row (with chunking options) for a document, if any."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_SELECT_DOC_SOURCE, (file_id,))
        source = cursor.fetchone()
        return dict(source) if source else None


def get_document_sources_by_collection(collection):
    """Return all stored document source rows and options for a given collection."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_SELECT_DOC_SOURCES_BY_COLLECTION, (collection,))
        return [dict(row) for row in cursor.fetchall()]


def delete_document_source(file_id):
    """Remove the stored source text for a document, returning whether a row existed."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOC_SOURCE, (file_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


def delete_document_sources_by_collection(collection):
    """Remove stored source rows for every document in a collection."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOC_SOURCES_BY_COLLECTION, (collection,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted


def delete_documents_by_collection(collection):
    """Delete every document record in a collection, returning the count."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_DOCS_BY_COLLECTION, (collection,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted


def rename_collection(old, new):
    """Move every document record to another collection, returning the count."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_RENAME_COLLECTION, (new, old))
        renamed = cursor.rowcount
        conn.commit()
        return renamed


def get_all_documents(collection=None):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        if collection is None:
            cursor.execute(_SELECT_ALL_DOCS)
        else:
            cursor.execute(_SELECT_DOCS_BY_COLLECTION, (collection,))
        documents = cursor.fetchall()
        return [dict(doc) for doc in documents]


def get_all_collections():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_ALL_COLLECTIONS)
        return [row["collection"] for row in cursor.fetchall()]


def get_collections_details() -> list[dict]:
    """Return aggregated metrics per document collection."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT id, filename, collection, upload_timestamp "
            "FROM document_store ORDER BY collection ASC, id ASC"
        ).fetchall()

    collections_map: dict[str, dict] = {}
    for row in rows:
        col = row["collection"]
        if col not in collections_map:
            collections_map[col] = {
                "collection": col,
                "document_count": 0,
                "file_formats": {},
                "earliest_upload": None,
                "latest_upload": None,
            }
        data = collections_map[col]
        data["document_count"] += 1

        filename = row["filename"] or ""
        ext = Path(filename).suffix.lstrip(".").lower() or "unknown"
        data["file_formats"][ext] = data["file_formats"].get(ext, 0) + 1

        ts = str(row["upload_timestamp"]) if row["upload_timestamp"] else None
        if ts:
            if data["earliest_upload"] is None or ts < data["earliest_upload"]:
                data["earliest_upload"] = ts
            if data["latest_upload"] is None or ts > data["latest_upload"]:
                data["latest_upload"] = ts

    return list(collections_map.values())


def get_library_stats():
    """Return library totals without loading any rows."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        documents = cursor.execute("SELECT COUNT(*) FROM document_store").fetchone()[0]
        collections = cursor.execute(
            "SELECT COUNT(DISTINCT collection) FROM document_store"
        ).fetchone()[0]
        sessions = cursor.execute(
            "SELECT COUNT(DISTINCT session_id) FROM application_logs"
        ).fetchone()[0]
        messages = cursor.execute("SELECT COUNT(*) FROM application_logs").fetchone()[0]
        feedback_up = cursor.execute("SELECT COUNT(*) FROM feedback WHERE rating = 1").fetchone()[0]
        feedback_down = cursor.execute(
            "SELECT COUNT(*) FROM feedback WHERE rating = -1"
        ).fetchone()[0]
        return {
            "documents": documents,
            "collections": collections,
            "sessions": sessions,
            "messages": messages,
            "feedback_up": feedback_up,
            "feedback_down": feedback_down,
        }


def _truncate_preview(preview: str | None) -> str:
    if not preview:
        return ""
    preview = preview.strip()
    if len(preview) <= PREVIEW_MAX_LENGTH:
        return preview
    return preview[: PREVIEW_MAX_LENGTH - 1].rstrip() + "…"


def get_all_sessions(
    status: str | None = None,
    tag: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM ({_SELECT_ALL_SESSIONS_BASE}) ORDER BY last_active DESC"
        cursor.execute(query)
        sessions = cursor.fetchall()
        results = []
        for session in sessions:
            s_dict = dict(session)
            if status:
                clean_status = status.strip().lower()
                if s_dict.get("status", "active").lower() != clean_status:
                    continue
            if tag:
                clean_tag = tag.strip().lower()
                raw_tags = s_dict.get("tags", "") or ""
                row_tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
                if clean_tag not in row_tags:
                    continue
            if assigned_agent:
                clean_assigned = assigned_agent.strip().lower()
                row_assigned = (s_dict.get("assigned_agent") or "").strip().lower()
                if clean_assigned == "unassigned":
                    if row_assigned:
                        continue
                elif row_assigned != clean_assigned:
                    continue
            if escalation_tier:
                clean_tier = escalation_tier.strip().lower()
                row_tier = (s_dict.get("escalation_tier") or DEFAULT_AGENT_TIER).strip().lower()
                if row_tier != clean_tier:
                    continue
            if not s_dict.get("label"):
                s_dict["label"] = None
            s_dict["preview"] = _truncate_preview(s_dict.get("preview"))
            results.append(s_dict)
        return results


def search_sessions(query: str, limit: int = 20) -> list[dict]:
    """Search sessions matching query text in user_query or gpt_response."""
    cleaned = (query or "").strip()
    if not cleaned:
        return []
    pattern = f"%{cleaned}%"
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SEARCH_SESSIONS, (pattern, pattern, max(1, limit)))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            sid = row["session_id"]
            q_cursor = conn.cursor()
            q_cursor.execute(_SELECT_MATCHED_QUERIES, (sid, pattern, pattern))
            matched_queries = [r["user_query"] for r in q_cursor.fetchall() if r["user_query"]]
            prio_val = row["priority"] if row["priority"] else DEFAULT_SESSION_PRIORITY
            agent_val = row["assigned_agent"] if row["assigned_agent"] else None
            tier_val = (
                row["escalation_tier"]
                if row["escalation_tier"]
                else DEFAULT_AGENT_TIER
            )
            results.append(
                {
                    "session_id": sid,
                    "label": row["label"] if row["label"] else None,
                    "status": row["status"] if row["status"] else "active",
                    "tags": row["tags"] if row["tags"] else "",
                    "priority": prio_val,
                    "assigned_agent": agent_val,
                    "escalation_tier": tier_val,
                    "match_count": row["match_count"],
                    "preview": _truncate_preview(row["preview"]),
                    "last_active": row["last_active"],
                    "matched_queries": matched_queries,
                }
            )
        return results


def delete_session(session_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_SESSION, (session_id,))
        deleted = cursor.rowcount > 0
        conn.execute(_DELETE_SESSION_LABEL, (session_id,))
        conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
        conn.commit()
        return deleted


def delete_sessions(session_ids: list[str]) -> dict[str, str]:
    """Delete multiple sessions cascade; returns map of session_id to status."""
    results: dict[str, str] = {}

    with closing(get_db_connection()) as conn:
        for session_id in session_ids:
            cursor = conn.execute(_DELETE_SESSION, (session_id,))
            if cursor.rowcount > 0:
                conn.execute(_DELETE_SESSION_LABEL, (session_id,))
                conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
                results[session_id] = "deleted"
            else:
                label_cursor = conn.execute(_DELETE_SESSION_LABEL, (session_id,))
                feedback_cursor = conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
                if label_cursor.rowcount > 0 or feedback_cursor.rowcount > 0:
                    results[session_id] = "deleted"
                else:
                    results[session_id] = "not_found"
        conn.commit()
    return results


def prune_sessions_before(cutoff_iso):
    """Delete sessions inactive since `cutoff_iso`, returning the count."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute(_STALE_SESSIONS, (cutoff_iso,)).fetchall()
        stale_ids = [row["session_id"] for row in rows]
        for session_id in stale_ids:
            conn.execute(_DELETE_SESSION, (session_id,))
            conn.execute(_DELETE_SESSION_LABEL, (session_id,))
            conn.execute(_DELETE_SESSION_FEEDBACK, (session_id,))
        conn.commit()
        return len(stale_ids)


def create_session_labels():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SESSION_LABELS_TABLE)
        conn.commit()


def create_feedback():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_FEEDBACK_TABLE)
        conn.commit()


def migrate_feedback():
    """Add newer columns to feedback table if missing (no-op otherwise)."""
    with closing(get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(feedback)")]
        if "comment" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN comment TEXT")
        if "score" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN score INTEGER DEFAULT NULL")
        if "resolution_satisfaction" not in columns:
            conn.execute(
                "ALTER TABLE feedback ADD COLUMN resolution_satisfaction INTEGER DEFAULT NULL"
            )
        if "agent_helpfulness" not in columns:
            conn.execute(
                "ALTER TABLE feedback ADD COLUMN agent_helpfulness INTEGER DEFAULT NULL"
            )
        if "response_speed" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN response_speed INTEGER DEFAULT NULL")
        if "review_status" not in columns:
            conn.execute(
                "ALTER TABLE feedback ADD COLUMN review_status TEXT "
                "NOT NULL DEFAULT 'pending_review'"
            )
        if "assigned_agent" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN assigned_agent TEXT DEFAULT NULL")
        if "escalation_tier" not in columns:
            conn.execute(
                "ALTER TABLE feedback ADD COLUMN escalation_tier TEXT NOT NULL DEFAULT 'tier_1'"
            )
        if "reviewer_notes" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN reviewer_notes TEXT DEFAULT NULL")
        if "reviewed_at" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN reviewed_at TEXT DEFAULT NULL")
        if "reviewed_by" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN reviewed_by TEXT DEFAULT NULL")
        conn.commit()


def insert_feedback(session_id, rating, comment=None):
    """Record a +1/-1 answer rating with optional comment; raises ValueError for other ratings."""
    if rating not in (1, -1):
        raise ValueError("Rating must be 1 or -1.")
    clean_comment = comment.strip() if comment and isinstance(comment, str) else None

    # Infer score from binary rating: 1 -> 5 stars, -1 -> 1 star
    score = 5 if rating == 1 else 1

    # Fetch active session metadata to capture assignee and escalation tier
    meta = get_session_metadata(session_id) or {}
    assigned_agent = meta.get("assigned_agent")
    escalation_tier = meta.get("escalation_tier") or DEFAULT_AGENT_TIER

    insert_sql = (
        "INSERT INTO feedback ("
        "session_id, rating, comment, score, review_status, assigned_agent, escalation_tier"
        ") VALUES (?, ?, ?, ?, 'pending_review', ?, ?)"
    )
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (session_id, rating, clean_comment, score, assigned_agent, escalation_tier),
        )
        feedback_id = cursor.lastrowid
        conn.commit()
        return feedback_id


def submit_csat_feedback(  # noqa: PLR0913, PLR0917
    session_id: str,
    score: int,
    resolution_satisfaction: int | None = None,
    agent_helpfulness: int | None = None,
    response_speed: int | None = None,
    comment: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
) -> dict[str, Any]:
    if not session_id or not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Session ID must not be empty.")
    clean_session_id = session_id.strip()

    norm_score = normalize_csat_score(score, allow_none=False)
    if norm_score is None:
        raise ValueError("CSAT overall score is required.")
    norm_res = normalize_csat_score(resolution_satisfaction)
    norm_help = normalize_csat_score(agent_helpfulness)
    norm_speed = normalize_csat_score(response_speed)
    clean_comment = comment.strip() if comment and isinstance(comment, str) else None

    # Derive binary rating for legacy backward compatibility: >=4 is +1, <=2 is -1, 3 is 0
    neutral_score_threshold = 3
    if norm_score > neutral_score_threshold:
        legacy_rating = 1
    elif norm_score < neutral_score_threshold:
        legacy_rating = -1
    else:
        legacy_rating = 0

    # Auto-resolve session assignee and tier if not explicitly passed
    meta = get_session_metadata(clean_session_id) or {}
    agent_val = assigned_agent if assigned_agent is not None else meta.get("assigned_agent")
    tier_val = (
        normalize_agent_tier(escalation_tier)
        if escalation_tier is not None
        else (meta.get("escalation_tier") or DEFAULT_AGENT_TIER)
    )

    insert_sql = (
        "INSERT INTO feedback ("
        "session_id, rating, comment, score, "
        "resolution_satisfaction, agent_helpfulness, response_speed, "
        "review_status, assigned_agent, escalation_tier"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)"
    )
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (
                clean_session_id,
                legacy_rating,
                clean_comment,
                norm_score,
                norm_res,
                norm_help,
                norm_speed,
                agent_val,
                tier_val,
            ),
        )
        feedback_id = cursor.lastrowid
        conn.commit()

        row = conn.execute(
            "SELECT id, session_id, rating, comment, score, "
            "resolution_satisfaction, agent_helpfulness, response_speed, "
            "review_status, assigned_agent, escalation_tier, reviewer_notes, "
            "reviewed_at, reviewed_by, created_at "
            "FROM feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()
        return dict(row) if row else {}


def update_feedback_review(  # noqa: PLR0913, PLR0917
    feedback_id: int,
    review_status: str,
    reviewer_notes: str | None = None,
    reviewed_by: str | None = "operator",
) -> dict[str, Any] | None:
    """Update operator review status, reviewer notes, and review timestamp."""
    norm_status = normalize_feedback_review_status(review_status)
    norm_notes = normalize_reviewer_notes(reviewer_notes)
    norm_by = (reviewed_by or "operator").strip()
    if len(norm_by) > MAX_REVIEWED_BY_LENGTH:
        norm_by = norm_by[:MAX_REVIEWED_BY_LENGTH]

    update_sql = (
        "UPDATE feedback SET "
        "review_status = ?, "
        "reviewer_notes = ?, "
        "reviewed_by = ?, "
        "reviewed_at = CURRENT_TIMESTAMP "
        "WHERE id = ?"
    )
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(update_sql, (norm_status, norm_notes, norm_by, feedback_id))
        if cursor.rowcount == 0:
            return None
        conn.commit()

        row = conn.execute(
            "SELECT id, session_id, rating, comment, score, "
            "resolution_satisfaction, agent_helpfulness, response_speed, "
            "review_status, assigned_agent, escalation_tier, reviewer_notes, "
            "reviewed_at, reviewed_by, created_at "
            "FROM feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()
        return dict(row) if row else None


def get_feedback_by_id(feedback_id: int) -> dict[str, Any] | None:
    """Fetch a single feedback record by primary key id."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT id, session_id, rating, comment, score, "
            "resolution_satisfaction, agent_helpfulness, response_speed, "
            "review_status, assigned_agent, escalation_tier, reviewer_notes, "
            "reviewed_at, reviewed_by, created_at "
            "FROM feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()
        return dict(row) if row else None


def list_feedback_review_queue(  # noqa: PLR0913, PLR0917
    review_status: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Query feedback queue for operator review with filters and pagination."""
    query = (
        "SELECT id, session_id, rating, comment, score, "
        "resolution_satisfaction, agent_helpfulness, response_speed, "
        "review_status, assigned_agent, escalation_tier, reviewer_notes, "
        "reviewed_at, reviewed_by, created_at FROM feedback"
    )
    count_query = "SELECT COUNT(*) FROM feedback"
    clauses: list[str] = []
    params: list[Any] = []

    if review_status:
        clauses.append("review_status = ?")
        params.append(normalize_feedback_review_status(review_status))
    if assigned_agent:
        clauses.append("assigned_agent = ?")
        params.append(assigned_agent.strip().lower())
    if escalation_tier:
        clauses.append("escalation_tier = ?")
        params.append(normalize_agent_tier(escalation_tier))
    if min_score is not None:
        clauses.append("score >= ?")
        params.append(int(min_score))
    if max_score is not None:
        clauses.append("score <= ?")
        params.append(int(max_score))

    if clauses:
        where_clause = " WHERE " + " AND ".join(clauses)
        query += where_clause
        count_query += where_clause

    query += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    query_params = list(params) + [max(1, limit), max(0, offset)]

    with closing(get_db_connection()) as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(query, query_params).fetchall()
        return [dict(row) for row in rows], total


def list_feedback(
    rating=None,
    session_id=None,
    limit=50,
    offset=0,
):
    """List feedback with optional filters and pagination, returning (items, total)."""
    query = (
        "SELECT id, session_id, rating, comment, score, "
        "resolution_satisfaction, agent_helpfulness, response_speed, "
        "review_status, assigned_agent, escalation_tier, reviewer_notes, "
        "reviewed_at, reviewed_by, created_at FROM feedback"
    )

    count_query = "SELECT COUNT(*) FROM feedback"
    clauses = []
    params = []

    if rating is not None:
        clauses.append("rating = ?")
        params.append(rating)
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)

    if clauses:
        where_clause = " WHERE " + " AND ".join(clauses)
        query += where_clause
        count_query += where_clause

    query += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    query_params = list(params) + [limit, offset]

    with closing(get_db_connection()) as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(query, query_params).fetchall()
        items = [dict(row) for row in rows]
        return items, total


def get_session_feedback(session_id):
    """Return all feedback records for a specific session ordered by created_at."""
    query = (
        "SELECT id, session_id, rating, comment, score, "
        "resolution_satisfaction, agent_helpfulness, response_speed, "
        "review_status, assigned_agent, escalation_tier, reviewer_notes, "
        "reviewed_at, reviewed_by, created_at FROM feedback "
        "WHERE session_id = ? ORDER BY created_at ASC, id ASC"
    )
    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, (session_id,)).fetchall()
        return [dict(row) for row in rows]


def get_agent_performance_analytics() -> list[dict[str, Any]]:
    """Compute aggregate CSAT scorecards attributed per agent and tier."""
    query = (
        "SELECT "
        "COALESCE(assigned_agent, 'unassigned') AS agent_id, "
        "COALESCE(escalation_tier, 'tier_1') AS tier, "
        "COUNT(*) AS total_ratings, "
        "ROUND(AVG(CASE WHEN score IS NOT NULL THEN score "
        "               WHEN rating = 1 THEN 5 "
        "               WHEN rating = -1 THEN 1 "
        "               ELSE 3 END), 2) AS avg_csat_score, "
        "ROUND(AVG(resolution_satisfaction), 2) AS avg_resolution_score, "
        "ROUND(AVG(agent_helpfulness), 2) AS avg_helpfulness_score, "
        "ROUND(AVG(response_speed), 2) AS avg_speed_score, "
        "SUM(CASE WHEN (score >= 4 OR (score IS NULL AND rating = 1)) "
        "     THEN 1 ELSE 0 END) AS positive_count, "
        "SUM(CASE WHEN (score <= 2 OR (score IS NULL AND rating = -1)) "
        "     THEN 1 ELSE 0 END) AS negative_count "
        "FROM feedback "
        "GROUP BY assigned_agent, escalation_tier "
        "ORDER BY avg_csat_score DESC, total_ratings DESC"
    )
    with closing(get_db_connection()) as conn:
        rows = conn.execute(query).fetchall()
        scorecards: list[dict[str, Any]] = []
        for r in rows:
            tot = r["total_ratings"]
            pos = r["positive_count"]
            satisfaction_pct = round((pos / tot * 100), 1) if tot > 0 else 0.0
            avg_res = (
                float(r["avg_resolution_score"])
                if r["avg_resolution_score"] is not None
                else None
            )
            avg_help = (
                float(r["avg_helpfulness_score"])
                if r["avg_helpfulness_score"] is not None
                else None
            )
            avg_speed = (
                float(r["avg_speed_score"])
                if r["avg_speed_score"] is not None
                else None
            )
            scorecards.append(
                {
                    "agent_id": r["agent_id"],
                    "tier": r["tier"],
                    "total_ratings": tot,
                    "avg_csat_score": float(r["avg_csat_score"] or 0.0),
                    "avg_resolution_score": avg_res,
                    "avg_helpfulness_score": avg_help,
                    "avg_speed_score": avg_speed,
                    "positive_count": pos,
                    "negative_count": r["negative_count"],
                    "satisfaction_rate": satisfaction_pct,
                }
            )
        return scorecards


def count_feedback(rating):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT_FEEDBACK_COUNT, (rating,))
        return cursor.fetchone()[0]


def get_feedback_analytics(recent_comments_limit: int = 5) -> dict:
    """Aggregate customer satisfaction (CSAT) and feedback metrics."""
    with closing(get_db_connection()) as conn:
        stats_query = (
            "SELECT "
            "COUNT(*) AS total_feedback, "
            "COALESCE(SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END), 0) AS positive_feedback, "
            "COALESCE(SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END), 0) AS negative_feedback, "
            "COALESCE(SUM(CASE WHEN comment IS NOT NULL AND trim(comment) != '' "
            "THEN 1 ELSE 0 END), 0) AS total_comments "
            "FROM feedback"
        )
        row = conn.execute(stats_query).fetchone()
        total = row["total_feedback"] if row else 0
        positive = row["positive_feedback"] if row else 0
        negative = row["negative_feedback"] if row else 0
        comments_count = row["total_comments"] if row else 0

        satisfaction_rate = round((positive / total * 100), 1) if total > 0 else 0.0
        comment_rate = round((comments_count / total * 100), 1) if total > 0 else 0.0

        comments_query = (
            "SELECT id, session_id, rating, comment, created_at FROM feedback "
            "WHERE comment IS NOT NULL AND trim(comment) != '' "
            "ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        comment_rows = conn.execute(comments_query, (recent_comments_limit,)).fetchall()
        recent_comments = [dict(r) for r in comment_rows]

        return {
            "total_feedback": total,
            "positive_feedback": positive,
            "negative_feedback": negative,
            "satisfaction_rate": satisfaction_rate,
            "total_comments": comments_count,
            "comment_rate": comment_rate,
            "recent_comments": recent_comments,
        }


def migrate_session_labels():
    """Add newer columns (status, tags, summary, notes, priority, agent, tier) if missing."""
    with closing(get_db_connection()) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(session_labels)")]
        if "status" not in columns:
            conn.execute(
                "ALTER TABLE session_labels ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
        if "tags" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
        if "summary" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN summary TEXT DEFAULT ''")
        if "resolution_notes" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN resolution_notes TEXT DEFAULT ''")
        if "priority" not in columns:
            conn.execute(
                "ALTER TABLE session_labels ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'"
            )
        if "assigned_agent" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN assigned_agent TEXT DEFAULT NULL")
        if "escalation_tier" not in columns:
            conn.execute(
                "ALTER TABLE session_labels "
                "ADD COLUMN escalation_tier TEXT NOT NULL DEFAULT 'tier_1'"
            )
        conn.commit()


def update_session_metadata(  # noqa: PLR0913, PLR0917
    session_id: str,
    label: str | None = None,
    status: str | None = None,
    tags: str | list[str] | None = None,
    summary: str | None = None,
    resolution_notes: str | None = None,
    priority: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
) -> bool:
    """Update metadata (label, status, tags, summary, notes, priority, agent, tier)."""
    clean_label = normalize_session_label(label) if label is not None else None
    clean_status = normalize_session_status(status) if status is not None else None
    clean_tags = normalize_session_tags(tags) if tags is not None else None
    clean_summary = normalize_session_summary(summary) if summary is not None else None
    clean_notes = (
        normalize_resolution_notes(resolution_notes) if resolution_notes is not None else None
    )
    clean_priority = normalize_session_priority(priority) if priority is not None else None
    clean_agent = None
    if assigned_agent is not None:
        raw_agent = assigned_agent.strip().lower()
        clean_agent = None if (not raw_agent or raw_agent == "unassigned") else raw_agent
    clean_tier = normalize_agent_tier(escalation_tier) if escalation_tier is not None else None

    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return False

        cur = conn.execute(
            "SELECT label, status, tags, summary, resolution_notes, "
            "priority, assigned_agent, escalation_tier "
            "FROM session_labels WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if cur is None:
            new_label = clean_label or ""
            new_status = clean_status or "active"
            new_tags = clean_tags or ""
            new_summary = clean_summary or ""
            new_notes = clean_notes or ""
            new_priority = clean_priority or DEFAULT_SESSION_PRIORITY
            new_agent = clean_agent
            new_tier = clean_tier or DEFAULT_AGENT_TIER
            conn.execute(
                "INSERT INTO session_labels "
                "(session_id, label, status, tags, summary, resolution_notes, "
                "priority, assigned_agent, escalation_tier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    new_label,
                    new_status,
                    new_tags,
                    new_summary,
                    new_notes,
                    new_priority,
                    new_agent,
                    new_tier,
                ),
            )
        else:
            new_label = clean_label if clean_label is not None else cur["label"]
            new_status = clean_status if clean_status is not None else cur["status"]
            new_tags = clean_tags if clean_tags is not None else cur["tags"]
            new_summary = clean_summary if clean_summary is not None else (cur["summary"] or "")
            new_notes = clean_notes if clean_notes is not None else (cur["resolution_notes"] or "")
            cur_prio = cur["priority"] if cur["priority"] else DEFAULT_SESSION_PRIORITY
            new_priority = clean_priority if clean_priority is not None else cur_prio
            cur_agent = cur["assigned_agent"] if cur["assigned_agent"] else None
            new_agent = clean_agent if assigned_agent is not None else cur_agent
            cur_tier = cur["escalation_tier"] if cur["escalation_tier"] else DEFAULT_AGENT_TIER
            new_tier = clean_tier if clean_tier is not None else cur_tier
            conn.execute(
                "UPDATE session_labels "
                "SET label = ?, status = ?, tags = ?, summary = ?, resolution_notes = ?, "
                "priority = ?, assigned_agent = ?, escalation_tier = ? WHERE session_id = ?",
                (
                    new_label,
                    new_status,
                    new_tags,
                    new_summary,
                    new_notes,
                    new_priority,
                    new_agent,
                    new_tier,
                    session_id,
                ),
            )
        conn.commit()
        return True


def get_session_metadata(session_id: str) -> dict | None:
    """Fetch label, status, tags, summary, notes, priority, agent, and tier for a session."""
    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return None
        row = conn.execute(
            "SELECT label, status, tags, summary, resolution_notes, "
            "priority, assigned_agent, escalation_tier "
            "FROM session_labels WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return {
                "session_id": session_id,
                "label": None,
                "status": "active",
                "tags": "",
                "summary": "",
                "resolution_notes": "",
                "priority": DEFAULT_SESSION_PRIORITY,
                "assigned_agent": None,
                "escalation_tier": DEFAULT_AGENT_TIER,
            }
        prio_val = row["priority"] if row["priority"] else DEFAULT_SESSION_PRIORITY
        cur_agent = row["assigned_agent"] if row["assigned_agent"] else None
        cur_tier = row["escalation_tier"] if row["escalation_tier"] else DEFAULT_AGENT_TIER
        return {
            "session_id": session_id,
            "label": row["label"] if row["label"] else None,
            "status": row["status"] if row["status"] else "active",
            "tags": row["tags"] if row["tags"] else "",
            "summary": row["summary"] if row["summary"] else "",
            "resolution_notes": row["resolution_notes"] if row["resolution_notes"] else "",
            "priority": prio_val,
            "assigned_agent": cur_agent,
            "escalation_tier": cur_tier,
        }


def get_support_triage_analytics() -> dict:
    """Compute operational triage metrics across all customer support sessions."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        query = f"SELECT session_id, message_count, status, tags FROM ({_SELECT_ALL_SESSIONS_BASE})"
        rows = cursor.execute(query).fetchall()

        total_sessions = len(rows)
        if total_sessions == 0:
            return {
                "total_sessions": 0,
                "active_count": 0,
                "resolved_count": 0,
                "escalated_count": 0,
                "closed_count": 0,
                "resolution_rate": 0.0,
                "escalation_rate": 0.0,
                "avg_turns_per_session": 0.0,
                "top_tags": [],
            }

        active_count = 0
        resolved_count = 0
        escalated_count = 0
        closed_count = 0
        total_messages = 0
        tag_counter: Counter[str] = Counter()

        for r in rows:
            st = (r["status"] or "active").lower()
            if st == "resolved":
                resolved_count += 1
            elif st == "escalated":
                escalated_count += 1
            elif st == "closed":
                closed_count += 1
            else:
                active_count += 1

            total_messages += int(r["message_count"] or 0)
            raw_tags = r["tags"] or ""
            if raw_tags:
                for tag in raw_tags.split(","):
                    clean = tag.strip().lower()
                    if clean:
                        tag_counter[clean] += 1

        resolution_rate = round(((resolved_count + closed_count) / total_sessions) * 100.0, 2)
        escalation_rate = round((escalated_count / total_sessions) * 100.0, 2)
        avg_turns = round(total_messages / total_sessions, 2)

        top_tags = [
            {"tag": tag, "count": count}
            for tag, count in tag_counter.most_common(10)
        ]

        return {
            "total_sessions": total_sessions,
            "active_count": active_count,
            "resolved_count": resolved_count,
            "escalated_count": escalated_count,
            "closed_count": closed_count,
            "resolution_rate": resolution_rate,
            "escalation_rate": escalation_rate,
            "avg_turns_per_session": avg_turns,
            "top_tags": top_tags,
        }


def rename_session(session_id, label):
    """Label a session that has chat history; returns False when unknown."""
    return update_session_metadata(session_id, label=label)


def create_webhooks():
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_WEBHOOKS_TABLE)
        conn.execute(_CREATE_WEBHOOK_DELIVERY_LOGS_TABLE)
        conn.commit()


def create_webhook(
    url: str,
    events: str | list[str] | None = "*",
    secret: str | None = None,
    is_active: bool = True,
) -> dict:
    """Register a new webhook subscription, returning the created webhook dict."""
    clean_url = normalize_webhook_url(url)
    clean_events = normalize_webhook_events(events)
    clean_secret = normalize_webhook_secret(secret)
    active_int = 1 if is_active else 0

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_INSERT_WEBHOOK, (clean_url, clean_events, clean_secret, active_int))
        webhook_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(_SELECT_WEBHOOK_BY_ID, (webhook_id,)).fetchone()
        return {
            "id": row["id"],
            "url": row["url"],
            "events": row["events"] or "*",
            "secret": row["secret"] or "",
            "is_active": bool(row["is_active"]),
            "failure_count": row["failure_count"],
            "created_at": row["created_at"],
        }


def get_webhook(webhook_id: int) -> dict | None:
    """Retrieve a single webhook subscription by its ID."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_WEBHOOK_BY_ID, (webhook_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "url": row["url"],
            "events": row["events"] or "*",
            "secret": row["secret"] or "",
            "is_active": bool(row["is_active"]),
            "failure_count": row["failure_count"],
            "created_at": row["created_at"],
        }


def list_webhooks(active_only: bool = False, event: str | None = None) -> list[dict]:
    """List webhook subscriptions with optional active and event filters."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, url, events, secret, is_active, failure_count, created_at "
            "FROM webhooks ORDER BY id ASC"
        )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            r_active = bool(row["is_active"])
            if active_only and not r_active:
                continue
            r_events = row["events"] or "*"
            if event is not None:
                clean_event = event.strip().lower()
                event_set = {e.strip() for e in r_events.split(",") if e.strip()}
                if "*" not in event_set and clean_event not in event_set:
                    continue
            results.append(
                {
                    "id": row["id"],
                    "url": row["url"],
                    "events": r_events,
                    "secret": row["secret"] or "",
                    "is_active": r_active,
                    "failure_count": row["failure_count"],
                    "created_at": row["created_at"],
                }
            )
        return results


def update_webhook(  # noqa: PLR0913, PLR0917
    webhook_id: int,
    url: str | None = None,
    events: str | list[str] | None = None,
    secret: str | None = None,
    is_active: bool | None = None,
    reset_failures: bool = False,
) -> dict | None:
    """Update fields on an existing webhook subscription."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_WEBHOOK_BY_ID, (webhook_id,)).fetchone()
        if row is None:
            return None

        new_url = normalize_webhook_url(url) if url is not None else row["url"]
        new_events = normalize_webhook_events(events) if events is not None else row["events"]
        new_secret = normalize_webhook_secret(secret) if secret is not None else row["secret"]
        new_is_active = (
            (1 if is_active else 0) if is_active is not None else row["is_active"]
        )
        new_failure_count = 0 if reset_failures else row["failure_count"]

        conn.execute(
            "UPDATE webhooks SET url = ?, events = ?, secret = ?, is_active = ?, "
            "failure_count = ? WHERE id = ?",
            (new_url, new_events, new_secret, new_is_active, new_failure_count, webhook_id),
        )
        conn.commit()

        return {
            "id": webhook_id,
            "url": new_url,
            "events": new_events,
            "secret": new_secret,
            "is_active": bool(new_is_active),
            "failure_count": new_failure_count,
            "created_at": row["created_at"],
        }


def delete_webhook(webhook_id: int) -> bool:
    """Delete a webhook subscription and its delivery logs."""
    with closing(get_db_connection()) as conn:
        conn.execute(_DELETE_WEBHOOK_LOGS_BY_WEBHOOK, (webhook_id,))
        cursor = conn.execute(_DELETE_WEBHOOK, (webhook_id,))
        conn.commit()
        return bool(cursor.rowcount > 0)


def record_webhook_delivery(  # noqa: PLR0913, PLR0917
    webhook_id: int,
    event: str,
    url: str,
    status_code: int | None,
    success: bool,
    payload_preview: str = "",
    error_message: str | None = None,
) -> int:
    """Record a delivery log attempt, updating failure_count on the webhook."""
    clean_preview = (payload_preview or "")[:MAX_DELIVERY_PREVIEW_LENGTH]
    clean_error = (error_message or "")[:MAX_DELIVERY_ERROR_LENGTH] if error_message else None
    success_int = 1 if success else 0

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            _INSERT_WEBHOOK_DELIVERY,
            (
                webhook_id,
                event,
                url,
                status_code,
                success_int,
                clean_preview,
                clean_error,
            ),
        )
        log_id = cursor.lastrowid
        if success:
            conn.execute(_RESET_WEBHOOK_FAILURE, (webhook_id,))
        else:
            conn.execute(_INCREMENT_WEBHOOK_FAILURE, (webhook_id,))
        conn.commit()
        return int(log_id) if log_id is not None else 0


def get_webhook_delivery_logs(
    webhook_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Return paginated delivery audit logs, optionally filtered by webhook_id."""
    query = (
        "SELECT id, webhook_id, event, url, status_code, success, "
        "payload_preview, error_message, delivered_at "
        "FROM webhook_delivery_logs"
    )
    count_query = "SELECT COUNT(*) FROM webhook_delivery_logs"
    clauses = []
    params = []

    if webhook_id is not None:
        clauses.append("webhook_id = ?")
        params.append(webhook_id)

    if clauses:
        where_clause = " WHERE " + " AND ".join(clauses)
        query += where_clause
        count_query += where_clause

    query += " ORDER BY delivered_at DESC, id DESC LIMIT ? OFFSET ?"
    query_params = list(params) + [limit, offset]

    with closing(get_db_connection()) as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(query, query_params).fetchall()
        items = [
            {
                "id": row["id"],
                "webhook_id": row["webhook_id"],
                "event": row["event"],
                "url": row["url"],
                "status_code": row["status_code"],
                "success": bool(row["success"]),
                "payload_preview": row["payload_preview"] or "",
                "error_message": row["error_message"],
                "delivered_at": row["delivered_at"],
            }
            for row in rows
        ]
        return items, total


DEFAULT_MACROS: list[dict] = [
    {
        "title": "Lease Renewal Offer",
        "shortcut": "/lease-renewal",
        "category": "Leasing",
        "content": (
            "Hello {customer_name},\n\n"
            "We would love to extend your stay with us! Your current lease is eligible "
            "for renewal. Please review the renewal options sent to your email or let us know "
            "if you would like to discuss custom lease terms.\n\n"
            "Best regards,\n{agent_name}\nProperty Management Team"
        ),
        "tags": "leasing, renewal",
        "status_action": "active",
    },
    {
        "title": "Emergency Maintenance Dispatch",
        "shortcut": "/emerg-maint",
        "category": "Maintenance",
        "content": (
            "Hello {customer_name},\n\n"
            "Thank you for alerting us regarding the urgent maintenance issue at unit {unit_id}. "
            "An emergency work order has been created, and our on-call technician has been "
            "dispatched.\n\n"
            "If you experience active water flooding, gas odor, or total power loss, please "
            "immediately call our 24/7 emergency dispatch line at {support_contact}.\n\n"
            "Ticket Reference: {session_id}"
        ),
        "tags": "maintenance, urgent, emergency",
        "status_action": "escalated",
    },
    {
        "title": "Routine Maintenance Scheduled",
        "shortcut": "/maint-scheduled",
        "category": "Maintenance",
        "content": (
            "Hello {customer_name},\n\n"
            "Your maintenance request for unit {unit_id} has been received and scheduled "
            "with our facilities team. A technician is estimated to visit within 24-48 business "
            "hours. You will receive an SMS update prior to arrival.\n\n"
            "Thank you for your cooperation!"
        ),
        "tags": "maintenance, routine",
        "status_action": "active",
    },
    {
        "title": "Online Rent Payment Instructions",
        "shortcut": "/rent-pay",
        "category": "Billing",
        "content": (
            "Hello {customer_name},\n\n"
            "Rent payments can be submitted securely online through our resident portal at "
            "https://portal.propertymanager.com.\n\n"
            "Accepted payment methods include ACH direct debit (no convenience fee), "
            "credit card, and debit card. Rent is due on the 1st of each month with a grace "
            "period through the 5th.\n\n"
            "If you have any questions regarding your statement, please let us know."
        ),
        "tags": "billing, rent, payment",
        "status_action": "resolved",
    },
    {
        "title": "Move-Out Inspection & Deposit Timeline",
        "shortcut": "/move-out",
        "category": "Leasing",
        "content": (
            "Hello {customer_name},\n\n"
            "As your move-out date approaches, please note that a final walkthrough inspection "
            "will be conducted within 48 hours of key handover. Any refundable security deposit, "
            "accompanied by an itemized deduction statement, will be processed within 21 business "
            "days in accordance with state regulations.\n\n"
            "Please ensure you provide your forwarding mailing address."
        ),
        "tags": "move-out, deposit, inspection",
        "status_action": "resolved",
    },
    {
        "title": "General Inquiry Resolution",
        "shortcut": "/resolve",
        "category": "General",
        "content": (
            "Hello {customer_name},\n\n"
            "I am glad I could assist you with your inquiry today! Please don't hesitate to "
            "reach back out if there is anything else we can help you with.\n\n"
            "Have a wonderful day!\n{agent_name}"
        ),
        "tags": "general, closing",
        "status_action": "resolved",
    },
]


def _format_macro_row(row: sqlite3.Row) -> dict:
    raw_tags = row["tags"] or ""
    tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
    return {
        "id": row["id"],
        "title": row["title"],
        "shortcut": row["shortcut"],
        "category": row["category"],
        "content": row["content"],
        "tags": tags_list,
        "status_action": row["status_action"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def seed_default_macros(force: bool = False) -> int:
    """Seed standard property management default macros if table is empty."""
    with closing(get_db_connection()) as conn:
        if not force:
            count = conn.execute("SELECT COUNT(*) FROM support_macros").fetchone()[0]
            if count > 0:
                return 0
        inserted = 0
        for item in DEFAULT_MACROS:
            existing = conn.execute(
                _SELECT_MACRO_BY_SHORTCUT, (item["shortcut"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    _INSERT_SUPPORT_MACRO,
                    (
                        item["title"],
                        item["shortcut"],
                        item["category"],
                        item["content"],
                        normalize_session_tags(item.get("tags")),
                        item.get("status_action"),
                    ),
                )
                inserted += 1
        conn.commit()
        return inserted


def create_support_macros() -> None:
    """Create support_macros table and indices, seeding initial templates."""
    db_path = Path(DB_NAME)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SUPPORT_MACROS_TABLE)
        conn.execute(_CREATE_MACRO_CATEGORY_INDEX)
        conn.execute(_CREATE_MACRO_SHORTCUT_INDEX)
        conn.commit()
    seed_default_macros()


def create_macro(  # noqa: PLR0913, PLR0917
    title: str,
    shortcut: str,
    content: str,
    category: str = "General",
    tags: str | list[str] | None = None,
    status_action: str | None = None,
) -> dict:
    """Register a new macro template."""
    norm_title = normalize_macro_title(title)
    norm_shortcut = normalize_macro_shortcut(shortcut)
    norm_category = normalize_macro_category(category)
    norm_content = normalize_macro_content(content)
    norm_tags = normalize_session_tags(tags)
    norm_status = normalize_macro_status_action(status_action)

    with closing(get_db_connection()) as conn:
        existing = conn.execute(_SELECT_MACRO_BY_SHORTCUT, (norm_shortcut,)).fetchone()
        if existing:
            raise ValueError(f"Macro shortcut '{norm_shortcut}' already exists.")
        cursor = conn.execute(
            _INSERT_SUPPORT_MACRO,
            (norm_title, norm_shortcut, norm_category, norm_content, norm_tags, norm_status),
        )
        macro_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(_SELECT_MACRO_BY_ID, (macro_id,)).fetchone()
        return _format_macro_row(row)


def get_macro(macro_id: int) -> dict | None:
    """Retrieve a macro by ID."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_MACRO_BY_ID, (macro_id,)).fetchone()
        return _format_macro_row(row) if row else None


def get_macro_by_shortcut(shortcut: str) -> dict | None:
    """Retrieve a macro by its trigger shortcut."""
    norm_shortcut = normalize_macro_shortcut(shortcut)
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_MACRO_BY_SHORTCUT, (norm_shortcut,)).fetchone()
        return _format_macro_row(row) if row else None


def list_macros(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List macros with optional filtering by category, tag, or search term."""
    query = (
        "SELECT id, title, shortcut, category, content, tags, "
        "status_action, created_at, updated_at "
        "FROM support_macros"
    )
    clauses = []
    params = []
    if category and category.strip():
        clauses.append("LOWER(category) = LOWER(?)")
        params.append(category.strip())
    if search and search.strip():
        term = f"%{search.strip()}%"
        clauses.append("(title LIKE ? OR shortcut LIKE ? OR content LIKE ?)")
        params.extend([term, term, term])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY category ASC, title ASC"

    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
        macros = [_format_macro_row(row) for row in rows]
        if tag and tag.strip():
            target_tag = tag.strip().lower()
            macros = [m for m in macros if any(target_tag == t.lower() for t in m["tags"])]
        return macros


def list_macro_categories() -> list[str]:
    """Return distinct categories across all registered macros."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute(_SELECT_MACRO_CATEGORIES).fetchall()
        return [row["category"] for row in rows if row["category"]]


def update_macro(  # noqa: PLR0913, PLR0917
    macro_id: int,
    title: str | None = None,
    shortcut: str | None = None,
    category: str | None = None,
    content: str | None = None,
    tags: str | list[str] | None = None,
    status_action: str | None = None,
) -> dict | None:
    """Update macro template attributes."""
    updates: list[str] = []
    params: list[Any] = []
    if title is not None:
        updates.append("title = ?")
        params.append(normalize_macro_title(title))
    if shortcut is not None:
        norm_sc = normalize_macro_shortcut(shortcut)
        with closing(get_db_connection()) as conn:
            existing = conn.execute(
                "SELECT id FROM support_macros WHERE LOWER(shortcut) = LOWER(?) AND id != ?",
                (norm_sc, macro_id),
            ).fetchone()
            if existing:
                raise ValueError(f"Macro shortcut '{norm_sc}' is already taken.")
        updates.append("shortcut = ?")
        params.append(norm_sc)
    if category is not None:
        updates.append("category = ?")
        params.append(normalize_macro_category(category))
    if content is not None:
        updates.append("content = ?")
        params.append(normalize_macro_content(content))
    if tags is not None:
        updates.append("tags = ?")
        params.append(normalize_session_tags(tags))
    if status_action is not None:
        updates.append("status_action = ?")
        params.append(normalize_macro_status_action(status_action))

    if not updates:
        return get_macro(macro_id)

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(macro_id)
    sql = f"UPDATE support_macros SET {', '.join(updates)} WHERE id = ?"
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(sql, params)
        if cursor.rowcount == 0:
            return None
        conn.commit()
        row = conn.execute(_SELECT_MACRO_BY_ID, (macro_id,)).fetchone()
        return _format_macro_row(row) if row else None


def delete_macro(macro_id: int) -> bool:
    """Delete a macro template by ID."""
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(_DELETE_SUPPORT_MACRO, (macro_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def get_session_timestamps(session_id: str) -> dict:
    """Return session start, first response, latest turn time, and turn counts."""
    with closing(get_db_connection()) as conn:
        query = (
            "SELECT MIN(created_at) AS session_start, "
            "MIN(CASE WHEN gpt_response IS NOT NULL AND TRIM(gpt_response) != '' "
            "THEN created_at END) AS first_response_at, "
            "MAX(created_at) AS last_activity, "
            "COUNT(*) AS total_turns "
            "FROM application_logs WHERE session_id = ?"
        )
        row = conn.execute(query, (session_id,)).fetchone()
        if not row or not row["session_start"]:
            return {
                "session_start": None,
                "first_response_at": None,
                "last_activity": None,
                "total_turns": 0,
            }
        return {
            "session_start": row["session_start"],
            "first_response_at": row["first_response_at"],
            "last_activity": row["last_activity"],
            "total_turns": row["total_turns"],
        }


def create_sla_policies():
    """Create sla_policies table, unique index, migrate columns, seed defaults if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SLA_POLICIES_TABLE)
        conn.execute(_CREATE_SLA_POLICY_INDEX)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(sla_policies)").fetchall()]
        if "use_business_hours" not in cols:
            conn.execute(
                "ALTER TABLE sla_policies ADD COLUMN use_business_hours INTEGER NOT NULL DEFAULT 0"
            )
        count = conn.execute("SELECT COUNT(*) FROM sla_policies").fetchone()[0]
        if count == 0:
            for item in DEFAULT_SLA_POLICIES:
                conn.execute(_INSERT_SLA_POLICY, item)
        conn.commit()


def create_sla_policy(  # noqa: PLR0913, PLR0917
    name: str,
    priority: str,
    category: str = "general",
    response_time_minutes: int = 60,
    resolution_time_minutes: int = 480,
    is_active: int = 1,
    use_business_hours: int | bool = 0,
) -> int:
    """Create a new SLA policy."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("SLA policy name must not be blank.")
    if len(clean_name) > MAX_SLA_POLICY_NAME_LENGTH:
        raise ValueError(f"SLA policy name exceeds max length {MAX_SLA_POLICY_NAME_LENGTH}.")

    clean_prio = normalize_session_priority(priority)
    clean_cat = (category or "general").strip().lower()
    if not clean_cat:
        clean_cat = "general"
    if len(clean_cat) > MAX_SLA_CATEGORY_LENGTH:
        raise ValueError(f"SLA category exceeds max length {MAX_SLA_CATEGORY_LENGTH}.")

    if response_time_minutes <= 0:
        raise ValueError("response_time_minutes must be greater than zero.")
    if resolution_time_minutes < response_time_minutes:
        raise ValueError(
            "resolution_time_minutes must be greater than or equal to response_time_minutes."
        )

    clean_active = 1 if is_active else 0
    clean_biz = 1 if use_business_hours else 0

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            _INSERT_SLA_POLICY,
            (
                clean_name,
                clean_prio,
                clean_cat,
                response_time_minutes,
                resolution_time_minutes,
                clean_active,
                clean_biz,
            ),
        )
        policy_id = cursor.lastrowid
        conn.commit()
        return int(policy_id or 0)


def get_sla_policy(policy_id: int) -> dict | None:
    """Fetch SLA policy by primary key ID, or None if not found."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_SLA_POLICY_BY_ID, (policy_id,)).fetchone()
        return dict(row) if row else None


def get_matching_sla_policy(priority: str, category: str = "general") -> dict | None:
    """Find the best active SLA policy matching priority and category with graceful fallbacks."""
    clean_prio = normalize_session_priority(priority)
    clean_cat = (category or "general").strip().lower()

    with closing(get_db_connection()) as conn:
        # 1. Exact priority & category match
        q1 = (
            "SELECT * FROM sla_policies "
            "WHERE priority = ? AND category = ? AND is_active = 1 LIMIT 1"
        )
        row = conn.execute(q1, (clean_prio, clean_cat)).fetchone()
        if row:
            return dict(row)

        # 2. Priority & 'general' fallback
        q2 = (
            "SELECT * FROM sla_policies "
            "WHERE priority = ? AND category = 'general' AND is_active = 1 LIMIT 1"
        )
        row = conn.execute(q2, (clean_prio,)).fetchone()
        if row:
            return dict(row)

        # 3. Any active policy with this priority
        q3 = (
            "SELECT * FROM sla_policies "
            "WHERE priority = ? AND is_active = 1 ORDER BY id ASC LIMIT 1"
        )
        row = conn.execute(q3, (clean_prio,)).fetchone()
        if row:
            return dict(row)

        # 4. Fallback to active 'medium' / 'general' or any active policy
        q4 = (
            "SELECT * FROM sla_policies "
            "WHERE priority = 'medium' AND category = 'general' AND is_active = 1 LIMIT 1"
        )
        row = conn.execute(q4).fetchone()
        if row:
            return dict(row)

        row = conn.execute("SELECT * FROM sla_policies WHERE is_active = 1 LIMIT 1").fetchone()
        return dict(row) if row else None


def list_sla_policies(
    priority: str | None = None,
    category: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """List SLA policies with optional priority, category, and active filters."""
    query = (
        "SELECT id, name, priority, category, response_time_minutes, "
        "resolution_time_minutes, is_active, use_business_hours, created_at, updated_at "
        "FROM sla_policies"
    )
    clauses = []
    params: list[object] = []

    if priority:
        clean_prio = normalize_session_priority(priority)
        clauses.append("priority = ?")
        params.append(clean_prio)

    if category:
        clean_cat = category.strip().lower()
        clauses.append("category = ?")
        params.append(clean_cat)

    if active_only:
        clauses.append("is_active = 1")

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += (
        " ORDER BY CASE priority "
        "WHEN 'urgent' THEN 1 "
        "WHEN 'high' THEN 2 "
        "WHEN 'medium' THEN 3 "
        "WHEN 'low' THEN 4 ELSE 5 END, id ASC"
    )

    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_sla_policy(  # noqa: PLR0912, PLR0913, PLR0917
    policy_id: int,
    name: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    response_time_minutes: int | None = None,
    resolution_time_minutes: int | None = None,
    is_active: int | None = None,
    use_business_hours: int | bool | None = None,
) -> bool:
    """Update an existing SLA policy; returns True if updated, False if not found."""
    current = get_sla_policy(policy_id)
    if current is None:
        return False

    new_name = current["name"]
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("SLA policy name must not be blank.")
        if len(clean_name) > MAX_SLA_POLICY_NAME_LENGTH:
            raise ValueError(f"SLA policy name exceeds max length {MAX_SLA_POLICY_NAME_LENGTH}.")
        new_name = clean_name

    new_priority = current["priority"]
    if priority is not None:
        new_priority = normalize_session_priority(priority)

    new_category = current["category"]
    if category is not None:
        clean_cat = category.strip().lower()
        if not clean_cat:
            clean_cat = "general"
        if len(clean_cat) > MAX_SLA_CATEGORY_LENGTH:
            raise ValueError(f"SLA category exceeds max length {MAX_SLA_CATEGORY_LENGTH}.")
        new_category = clean_cat

    new_resp = current["response_time_minutes"]
    if response_time_minutes is not None:
        if response_time_minutes <= 0:
            raise ValueError("response_time_minutes must be greater than zero.")
        new_resp = response_time_minutes

    new_resol = current["resolution_time_minutes"]
    if resolution_time_minutes is not None:
        if resolution_time_minutes <= 0:
            raise ValueError("resolution_time_minutes must be greater than zero.")
        new_resol = resolution_time_minutes

    if new_resol < new_resp:
        raise ValueError(
            "resolution_time_minutes must be greater than or equal to response_time_minutes."
        )

    new_active = current["is_active"]
    if is_active is not None:
        new_active = 1 if is_active else 0

    new_biz = current.get("use_business_hours", 0)
    if use_business_hours is not None:
        new_biz = 1 if use_business_hours else 0

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sla_policies "
            "SET name = ?, priority = ?, category = ?, response_time_minutes = ?, "
            "resolution_time_minutes = ?, is_active = ?, use_business_hours = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                new_name,
                new_priority,
                new_category,
                new_resp,
                new_resol,
                new_active,
                new_biz,
                policy_id,
            ),
        )
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def delete_sla_policy(policy_id: int) -> bool:
    """Delete an SLA policy by ID; returns True if deleted, False if not found."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_DELETE_SLA_POLICY, (policy_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def create_support_agents() -> None:
    """Create support_agents table and seed defaults if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SUPPORT_AGENTS_TABLE)
        count = conn.execute("SELECT COUNT(*) FROM support_agents").fetchone()[0]
        if count == 0:
            for aid, name, email, tier, dept, act in DEFAULT_SUPPORT_AGENTS:
                conn.execute(_INSERT_SUPPORT_AGENT, (aid, name, email, tier, dept, act))
        conn.commit()


def create_session_assignment_history() -> None:
    """Create session_assignment_history table."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_SESSION_ASSIGNMENT_HISTORY_TABLE)
        conn.commit()


def create_support_agent(  # noqa: PLR0913, PLR0917
    agent_id: str,
    name: str,
    email: str,
    tier: str = "tier_1",
    department: str = "general_leasing",
    is_active: bool | int = 1,
) -> dict:
    """Create a support agent profile."""
    clean_id = normalize_agent_id(agent_id)
    clean_name = normalize_agent_name(name)
    clean_email = normalize_agent_email(email)
    clean_tier = normalize_agent_tier(tier)
    clean_dept = normalize_agent_department(department)
    clean_active = 1 if is_active else 0

    with closing(get_db_connection()) as conn:
        conn.execute(
            _INSERT_SUPPORT_AGENT,
            (clean_id, clean_name, clean_email, clean_tier, clean_dept, clean_active),
        )
        conn.commit()
    res = get_support_agent(clean_id)
    if res is None:
        raise RuntimeError("Failed to retrieve created support agent.")
    return res


def get_support_agent(agent_id: str) -> dict | None:
    """Fetch support agent by agent_id, or None if not found."""
    clean_id = (agent_id or "").strip().lower()
    if not clean_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute(_SELECT_SUPPORT_AGENT_BY_ID, (clean_id,)).fetchone()
        return dict(row) if row else None


def list_support_agents(
    tier: str | None = None,
    department: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """List support agents with optional filters."""
    query = (
        "SELECT id, name, email, tier, department, is_active, created_at, updated_at "
        "FROM support_agents"
    )
    clauses: list[str] = []
    params: list[object] = []

    if tier:
        clean_tier = normalize_agent_tier(tier)
        clauses.append("tier = ?")
        params.append(clean_tier)

    if department:
        clean_dept = normalize_agent_department(department)
        clauses.append("department = ?")
        params.append(clean_dept)

    if active_only:
        clauses.append("is_active = 1")

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += (
        " ORDER BY CASE tier "
        "WHEN 'tier_1' THEN 1 "
        "WHEN 'tier_2' THEN 2 "
        "WHEN 'tier_3' THEN 3 ELSE 4 END, name ASC"
    )

    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_support_agent(  # noqa: PLR0912, PLR0913, PLR0917
    agent_id: str,
    name: str | None = None,
    email: str | None = None,
    tier: str | None = None,
    department: str | None = None,
    is_active: bool | int | None = None,
) -> bool:
    """Update support agent profile; returns True if updated, False if not found."""
    current = get_support_agent(agent_id)
    if current is None:
        return False

    new_name = normalize_agent_name(name) if name is not None else current["name"]
    new_email = normalize_agent_email(email) if email is not None else current["email"]
    new_tier = normalize_agent_tier(tier) if tier is not None else current["tier"]
    new_dept = (
        normalize_agent_department(department) if department is not None else current["department"]
    )
    new_active = (1 if is_active else 0) if is_active is not None else current["is_active"]

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE support_agents "
            "SET name = ?, email = ?, tier = ?, department = ?, is_active = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_name, new_email, new_tier, new_dept, new_active, current["id"]),
        )
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def delete_support_agent(agent_id: str) -> bool:
    """Delete support agent by ID; returns True if deleted, False if not found."""
    clean_id = (agent_id or "").strip().lower()
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(_DELETE_SUPPORT_AGENT, (clean_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def record_session_assignment(  # noqa: PLR0913, PLR0917
    session_id: str,
    assigned_by: str = "system",
    previous_agent: str | None = None,
    new_agent: str | None = None,
    previous_tier: str = "tier_1",
    new_tier: str = "tier_1",
    reason: str = "",
) -> dict:
    """Record a session assignment / tier transition in history."""
    clean_by = (assigned_by or "system").strip()
    clean_reason = (reason or "").strip()
    if len(clean_reason) > MAX_ASSIGNMENT_REASON_LENGTH:
        clean_reason = clean_reason[:MAX_ASSIGNMENT_REASON_LENGTH]

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            _INSERT_ASSIGNMENT_HISTORY,
            (
                session_id,
                clean_by,
                previous_agent,
                new_agent,
                previous_tier,
                new_tier,
                clean_reason,
            ),
        )
        entry_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT id, session_id, assigned_by, previous_agent, new_agent, "
            "previous_tier, new_tier, reason, assigned_at "
            "FROM session_assignment_history WHERE id = ?",
            (entry_id,),
        ).fetchone()
        return dict(row) if row else {}


def get_session_assignment_history(session_id: str, limit: int = 50) -> list[dict]:
    """Fetch assignment history for a session."""
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            _SELECT_ASSIGNMENT_HISTORY,
            (session_id, max(1, limit)),
        ).fetchall()
        return [dict(r) for r in rows]


def create_knowledge_gaps() -> None:
    """Create knowledge_gaps table and index."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_KNOWLEDGE_GAPS_TABLE)
        conn.execute(_CREATE_KNOWLEDGE_GAP_NORM_INDEX)
        conn.commit()


def normalize_knowledge_query(query: str | None) -> str:
    """Normalize a customer query into a canonical lowercase alphanumeric form."""
    cleaned = (query or "").strip()
    if not cleaned:
        raise ValueError("Knowledge gap query must not be blank.")
    if len(cleaned) > MAX_KNOWLEDGE_QUERY_LENGTH:
        raise ValueError(
            f"Knowledge gap query exceeds max length {MAX_KNOWLEDGE_QUERY_LENGTH}."
        )
    tokens = re.findall(r"[a-z0-9]+", cleaned.lower())
    return " ".join(tokens) if tokens else cleaned.lower()


def normalize_knowledge_category(category: str | None) -> str:
    """Validate and normalize knowledge category."""
    clean_cat = (category or DEFAULT_KNOWLEDGE_CATEGORY).strip().lower()
    if not clean_cat:
        clean_cat = DEFAULT_KNOWLEDGE_CATEGORY
    if clean_cat not in VALID_KNOWLEDGE_CATEGORIES:
        allowed = ", ".join(sorted(VALID_KNOWLEDGE_CATEGORIES))
        raise ValueError(f"Invalid knowledge category '{clean_cat}'. Allowed: {allowed}.")
    return clean_cat


def normalize_knowledge_gap_status(status: str | None) -> str:
    """Validate and normalize knowledge gap status."""
    clean_status = (status or DEFAULT_KNOWLEDGE_GAP_STATUS).strip().lower()
    if not clean_status:
        clean_status = DEFAULT_KNOWLEDGE_GAP_STATUS
    if clean_status not in VALID_KNOWLEDGE_GAP_STATUSES:
        allowed = ", ".join(sorted(VALID_KNOWLEDGE_GAP_STATUSES))
        raise ValueError(f"Invalid knowledge gap status '{clean_status}'. Allowed: {allowed}.")
    return clean_status


def normalize_knowledge_gap_source(source_type: str | None) -> str:
    """Validate and normalize knowledge gap source_type."""
    clean_src = (source_type or DEFAULT_KNOWLEDGE_GAP_SOURCE).strip().lower()
    if not clean_src:
        clean_src = DEFAULT_KNOWLEDGE_GAP_SOURCE
    if clean_src not in VALID_KNOWLEDGE_GAP_SOURCES:
        allowed = ", ".join(sorted(VALID_KNOWLEDGE_GAP_SOURCES))
        raise ValueError(
            f"Invalid knowledge gap source_type '{clean_src}'. Allowed: {allowed}."
        )
    return clean_src


_PRIORITY_RANK = {"urgent": 4, "high": 3, "medium": 2, "low": 1}


def record_knowledge_gap(  # noqa: PLR0913, PLR0917
    query: str,
    category: str = DEFAULT_KNOWLEDGE_CATEGORY,
    source_type: str = DEFAULT_KNOWLEDGE_GAP_SOURCE,
    session_id: str | None = None,
    priority: str = DEFAULT_SESSION_PRIORITY,
    notes: str = "",
) -> dict[str, Any]:
    """Record a knowledge gap, deduplicating and incrementing frequency on active matches."""
    clean_query = (query or "").strip()
    norm_query = normalize_knowledge_query(clean_query)
    clean_cat = normalize_knowledge_category(category)
    clean_src = normalize_knowledge_gap_source(source_type)
    clean_prio = normalize_session_priority(priority)
    clean_sid = (session_id or "").strip() or None
    clean_notes = (notes or "").strip()
    if len(clean_notes) > MAX_KNOWLEDGE_NOTES_LENGTH:
        raise ValueError(
            f"Knowledge gap notes exceed max length {MAX_KNOWLEDGE_NOTES_LENGTH}."
        )

    with closing(get_db_connection()) as conn:
        existing = conn.execute(
            "SELECT * FROM knowledge_gaps "
            "WHERE normalized_query = ? AND status IN ('open', 'drafting') "
            "ORDER BY id DESC LIMIT 1",
            (norm_query,),
        ).fetchone()

        if existing:
            gap_id = int(existing["id"])
            new_freq = int(existing["frequency"]) + 1
            curr_prio = str(existing["priority"] or DEFAULT_SESSION_PRIORITY)
            target_prio = (
                clean_prio
                if _PRIORITY_RANK.get(clean_prio, 2) > _PRIORITY_RANK.get(curr_prio, 2)
                else curr_prio
            )
            if new_freq >= 3 and _PRIORITY_RANK.get(target_prio, 2) < _PRIORITY_RANK["high"]:  # noqa: PLR2004
                target_prio = "high"

            new_sid = clean_sid or existing["session_id"]
            new_notes = clean_notes if clean_notes else existing["notes"]

            conn.execute(
                "UPDATE knowledge_gaps "
                "SET frequency = ?, priority = ?, session_id = ?, notes = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_freq, target_prio, new_sid, new_notes, gap_id),
            )
            conn.commit()
            updated_row = conn.execute(
                "SELECT * FROM knowledge_gaps WHERE id = ?", (gap_id,)
            ).fetchone()
            res = dict(updated_row) if updated_row else {}
            res["deduplicated"] = True
            return res

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO knowledge_gaps "
            "(query, normalized_query, category, source_type, session_id, "
            "frequency, priority, status, notes) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 'open', ?)",
            (
                clean_query,
                norm_query,
                clean_cat,
                clean_src,
                clean_sid,
                clean_prio,
                clean_notes,
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        conn.commit()
        created_row = conn.execute(
            "SELECT * FROM knowledge_gaps WHERE id = ?", (new_id,)
        ).fetchone()
        res = dict(created_row) if created_row else {}
        res["deduplicated"] = False
        return res


def get_knowledge_gap(gap_id: int) -> dict[str, Any] | None:
    """Fetch a knowledge gap by ID, or None if not found."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_gaps WHERE id = ?", (gap_id,)
        ).fetchone()
        return dict(row) if row else None


def list_knowledge_gaps(  # noqa: PLR0913, PLR0917
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List knowledge gaps with optional filtering and pagination."""
    clauses: list[str] = []
    params: list[Any] = []

    if status:
        clauses.append("status = ?")
        params.append(normalize_knowledge_gap_status(status))
    if category:
        clauses.append("category = ?")
        params.append(normalize_knowledge_category(category))
    if priority:
        clauses.append("priority = ?")
        params.append(normalize_session_priority(priority))
    if source_type:
        clauses.append("source_type = ?")
        params.append(normalize_knowledge_gap_source(source_type))

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    count_sql = f"SELECT COUNT(*) FROM knowledge_gaps{where_sql}"
    select_sql = (
        f"SELECT * FROM knowledge_gaps{where_sql} "
        "ORDER BY CASE priority "
        "WHEN 'urgent' THEN 1 "
        "WHEN 'high' THEN 2 "
        "WHEN 'medium' THEN 3 "
        "WHEN 'low' THEN 4 ELSE 5 END, frequency DESC, id DESC "
        "LIMIT ? OFFSET ?"
    )

    with closing(get_db_connection()) as conn:
        total = int(conn.execute(count_sql, params).fetchone()[0])
        rows = conn.execute(
            select_sql, [*params, max(1, limit), max(0, offset)]
        ).fetchall()
        return [dict(r) for r in rows], total


def update_knowledge_gap(  # noqa: PLR0913, PLR0917
    gap_id: int,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    linked_article_id: int | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    """Update a knowledge gap record; returns updated dict or None if not found."""
    current = get_knowledge_gap(gap_id)
    if current is None:
        return None

    new_status = (
        normalize_knowledge_gap_status(status)
        if status is not None
        else current["status"]
    )
    new_prio = (
        normalize_session_priority(priority)
        if priority is not None
        else current["priority"]
    )
    new_cat = (
        normalize_knowledge_category(category)
        if category is not None
        else current["category"]
    )
    new_linked = (
        linked_article_id
        if linked_article_id is not None
        else current["linked_article_id"]
    )
    new_notes = current["notes"]
    if notes is not None:
        clean_notes = notes.strip()
        if len(clean_notes) > MAX_KNOWLEDGE_NOTES_LENGTH:
            raise ValueError(
                f"Knowledge gap notes exceed max length {MAX_KNOWLEDGE_NOTES_LENGTH}."
            )
        new_notes = clean_notes

    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE knowledge_gaps "
            "SET status = ?, priority = ?, category = ?, linked_article_id = ?, "
            "notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, new_prio, new_cat, new_linked, new_notes, gap_id),
        )
        conn.commit()
    return get_knowledge_gap(gap_id)


def delete_knowledge_gap(gap_id: int) -> bool:
    """Delete a knowledge gap by ID; returns True if deleted, False if not found."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_gaps WHERE id = ?", (gap_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def create_knowledge_articles() -> None:
    """Create knowledge_articles table and index."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_KNOWLEDGE_ARTICLES_TABLE)
        conn.execute(_CREATE_KNOWLEDGE_ARTICLE_CAT_INDEX)
        conn.commit()


def normalize_knowledge_article_status(status: str | None) -> str:
    """Validate and normalize knowledge article status."""
    clean_status = (status or DEFAULT_KNOWLEDGE_ARTICLE_STATUS).strip().lower()
    if not clean_status:
        clean_status = DEFAULT_KNOWLEDGE_ARTICLE_STATUS
    if clean_status not in VALID_KNOWLEDGE_ARTICLE_STATUSES:
        allowed = ", ".join(sorted(VALID_KNOWLEDGE_ARTICLE_STATUSES))
        raise ValueError(
            f"Invalid knowledge article status '{clean_status}'. Allowed: {allowed}."
        )
    return clean_status


def _normalize_article_tags(tags: str | list[str] | None) -> str:
    if tags is None:
        return ""
    if isinstance(tags, list):
        items = [str(t).strip().lower() for t in tags if str(t).strip()]
    else:
        items = [t.strip().lower() for t in str(tags).split(",") if t.strip()]
    deduped = list(dict.fromkeys(items))
    joined = ",".join(deduped)
    if len(joined) > MAX_KNOWLEDGE_TAGS_LENGTH:
        raise ValueError(
            f"Knowledge article tags exceed max length {MAX_KNOWLEDGE_TAGS_LENGTH}."
        )
    return joined


def _format_article_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    raw_tags = data.get("tags") or ""
    if isinstance(raw_tags, list):
        data["tags"] = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        data["tags"] = [t.strip() for t in str(raw_tags).split(",") if t.strip()]
    return data


def create_knowledge_article(  # noqa: PLR0913, PLR0917
    title: str,
    content_markdown: str,
    category: str = DEFAULT_KNOWLEDGE_CATEGORY,
    question_pattern: str = "",
    tags: str | list[str] | None = None,
    source_session_id: str | None = None,
    source_gap_id: int | None = None,
    status: str = DEFAULT_KNOWLEDGE_ARTICLE_STATUS,
    author: str = "support_agent",
) -> dict[str, Any]:
    """Create a new knowledge base article or draft."""
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Knowledge article title must not be blank.")
    if len(clean_title) > MAX_KNOWLEDGE_TITLE_LENGTH:
        raise ValueError(
            f"Knowledge article title exceeds max length {MAX_KNOWLEDGE_TITLE_LENGTH}."
        )

    clean_content = (content_markdown or "").strip()
    if not clean_content:
        raise ValueError("Knowledge article content_markdown must not be blank.")
    if len(clean_content) > MAX_KNOWLEDGE_CONTENT_LENGTH:
        raise ValueError(
            f"Knowledge article content_markdown exceeds max length {MAX_KNOWLEDGE_CONTENT_LENGTH}."
        )

    clean_cat = normalize_knowledge_category(category)
    clean_q_pat = (question_pattern or "").strip()[:MAX_KNOWLEDGE_QUERY_LENGTH]
    clean_tags = _normalize_article_tags(tags)
    clean_sid = (source_session_id or "").strip() or None
    clean_status = normalize_knowledge_article_status(status)
    clean_author = (author or "support_agent").strip() or "support_agent"
    if len(clean_author) > MAX_KNOWLEDGE_AUTHOR_LENGTH:
        raise ValueError(
            f"Knowledge article author exceeds max length {MAX_KNOWLEDGE_AUTHOR_LENGTH}."
        )

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO knowledge_articles "
            "(title, category, question_pattern, content_markdown, tags, "
            "source_session_id, source_gap_id, status, author) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                clean_title,
                clean_cat,
                clean_q_pat,
                clean_content,
                clean_tags,
                clean_sid,
                source_gap_id,
                clean_status,
                clean_author,
            ),
        )
        article_id = int(cursor.lastrowid or 0)
        conn.commit()

    created = get_knowledge_article(article_id)
    if created is None:
        raise RuntimeError("Failed to retrieve created knowledge article.")
    return created


def get_knowledge_article(article_id: int) -> dict[str, Any] | None:
    """Fetch a knowledge article by ID, or None if not found."""
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_articles WHERE id = ?", (article_id,)
        ).fetchone()
        return _format_article_row(row) if row else None


def list_knowledge_articles(
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List knowledge articles with optional status, category, or keyword search filtering."""
    clauses: list[str] = []
    params: list[Any] = []

    if status:
        clauses.append("status = ?")
        params.append(normalize_knowledge_article_status(status))
    if category:
        clauses.append("category = ?")
        params.append(normalize_knowledge_category(category))
    if search and search.strip():
        like_pat = f"%{search.strip()}%"
        clauses.append(
            "(title LIKE ? OR question_pattern LIKE ? OR content_markdown LIKE ? OR tags LIKE ?)"
        )
        params.extend([like_pat, like_pat, like_pat, like_pat])

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    count_sql = f"SELECT COUNT(*) FROM knowledge_articles{where_sql}"
    select_sql = (
        f"SELECT * FROM knowledge_articles{where_sql} "
        "ORDER BY id DESC LIMIT ? OFFSET ?"
    )

    with closing(get_db_connection()) as conn:
        total = int(conn.execute(count_sql, params).fetchone()[0])
        rows = conn.execute(
            select_sql, [*params, max(1, limit), max(0, offset)]
        ).fetchall()
        return [_format_article_row(r) for r in rows], total


def update_knowledge_article(  # noqa: PLR0912, PLR0913, PLR0917
    article_id: int,
    title: str | None = None,
    category: str | None = None,
    question_pattern: str | None = None,
    content_markdown: str | None = None,
    tags: str | list[str] | None = None,
    status: str | None = None,
    published_file_id: int | None = None,
    published_collection: str | None = None,
) -> dict[str, Any] | None:
    """Update a knowledge article; returns updated dict or None if not found."""
    current = get_knowledge_article(article_id)
    if current is None:
        return None

    new_title = current["title"]
    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Knowledge article title must not be blank.")
        if len(clean_title) > MAX_KNOWLEDGE_TITLE_LENGTH:
            raise ValueError(
                f"Knowledge article title exceeds max length {MAX_KNOWLEDGE_TITLE_LENGTH}."
            )
        new_title = clean_title

    new_cat = (
        normalize_knowledge_category(category)
        if category is not None
        else current["category"]
    )
    new_q_pat = (
        question_pattern.strip()[:MAX_KNOWLEDGE_QUERY_LENGTH]
        if question_pattern is not None
        else current["question_pattern"]
    )

    new_content = current["content_markdown"]
    if content_markdown is not None:
        clean_content = content_markdown.strip()
        if not clean_content:
            raise ValueError("Knowledge article content_markdown must not be blank.")
        if len(clean_content) > MAX_KNOWLEDGE_CONTENT_LENGTH:
            raise ValueError(
                f"Knowledge article content_markdown exceeds max length {MAX_KNOWLEDGE_CONTENT_LENGTH}."
            )
        new_content = clean_content

    new_tags = (
        _normalize_article_tags(tags)
        if tags is not None
        else _normalize_article_tags(current["tags"])
    )
    new_status = (
        normalize_knowledge_article_status(status)
        if status is not None
        else current["status"]
    )
    new_pub_fid = (
        published_file_id
        if published_file_id is not None
        else current["published_file_id"]
    )
    new_pub_col = (
        published_collection
        if published_collection is not None
        else current["published_collection"]
    )

    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE knowledge_articles "
            "SET title = ?, category = ?, question_pattern = ?, content_markdown = ?, "
            "tags = ?, status = ?, published_file_id = ?, published_collection = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                new_title,
                new_cat,
                new_q_pat,
                new_content,
                new_tags,
                new_status,
                new_pub_fid,
                new_pub_col,
                article_id,
            ),
        )
        conn.commit()
    return get_knowledge_article(article_id)


def delete_knowledge_article(article_id: int) -> bool:
    """Delete a knowledge article by ID; returns True if deleted, False if not found."""
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_articles WHERE id = ?", (article_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


# Initialize the database tables
create_application_logs()
create_document_store()
migrate_document_store()
create_session_labels()
migrate_session_labels()
create_feedback()
migrate_feedback()
create_webhooks()
create_support_macros()
create_sla_policies()
create_support_agents()
create_session_assignment_history()
create_knowledge_gaps()
create_knowledge_articles()

