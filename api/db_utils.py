import re
import sqlite3
import uuid
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
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
    "escalation_tier TEXT NOT NULL DEFAULT 'tier_1', "
    "tenant_id TEXT DEFAULT NULL REFERENCES tenants(id), "
    "unit_id TEXT DEFAULT NULL REFERENCES units(id))"
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
    "tenant.created",
    "tenant.updated",
    "tenant.balance_overdue",
    "work_order.created",
    "work_order.emergency_escalated",
    "work_order.status_changed",
    "billing.payment_received",
    "billing.charge_posted",
    "billing.late_fee_assessed",
    "billing.overdue_escalated",
    "lease_renewal.offered",
    "lease_renewal.accepted",
    "lease_renewal.signed",
    "lease_renewal.declined",
    "inspection.scheduled",
    "inspection.completed",
    "inspection.deposit_deductions_assessed",
    "inspection.keys_returned",
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

_CREATE_UNITS_TABLE = (
    "CREATE TABLE IF NOT EXISTS units ("
    "id TEXT PRIMARY KEY, "
    "property_name TEXT NOT NULL, "
    "unit_number TEXT NOT NULL, "
    "building_name TEXT NOT NULL DEFAULT '', "
    "floor INTEGER NOT NULL DEFAULT 1, "
    "address TEXT NOT NULL, "
    "city TEXT NOT NULL, "
    "state TEXT NOT NULL, "
    "zip_code TEXT NOT NULL, "
    "monthly_rent REAL NOT NULL DEFAULT 0.0, "
    "parking_spot TEXT NOT NULL DEFAULT '', "
    "gate_code TEXT NOT NULL DEFAULT '', "
    "wifi_ssid TEXT NOT NULL DEFAULT '', "
    "trash_day TEXT NOT NULL DEFAULT '', "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_UNITS_PROPERTY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_units_property ON units(property_name)"
)
_CREATE_UNITS_UNIT_NUM_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_units_number ON units(unit_number)"
)

MAX_UNIT_ID_LENGTH = 50
MAX_PROPERTY_NAME_LENGTH = 100
MAX_UNIT_NUMBER_LENGTH = 50
MAX_ADDRESS_LENGTH = 200
MAX_CITY_LENGTH = 100
MAX_STATE_LENGTH = 50
MAX_ZIP_CODE_LENGTH = 20
MAX_UNIT_NOTES_LENGTH = 2000

_CREATE_TENANTS_TABLE = (
    "CREATE TABLE IF NOT EXISTS tenants ("
    "id TEXT PRIMARY KEY, "
    "first_name TEXT NOT NULL, "
    "last_name TEXT NOT NULL, "
    "email TEXT NOT NULL UNIQUE, "
    "phone TEXT NOT NULL, "
    "unit_id TEXT DEFAULT NULL REFERENCES units(id) ON DELETE SET NULL, "
    "lease_start TEXT NOT NULL, "
    "lease_end TEXT NOT NULL, "
    "monthly_rent REAL NOT NULL DEFAULT 0.0, "
    "balance_due REAL NOT NULL DEFAULT 0.0, "
    "status TEXT NOT NULL DEFAULT 'active', "
    "emergency_contact_name TEXT NOT NULL DEFAULT '', "
    "emergency_contact_phone TEXT NOT NULL DEFAULT '', "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_TENANTS_EMAIL_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email)"
)
_CREATE_TENANTS_UNIT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_tenants_unit_id ON tenants(unit_id)"
)
_CREATE_TENANTS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status)"
)

VALID_TENANT_STATUSES = {"active", "pending", "past_due", "moved_out", "evicted"}
DEFAULT_TENANT_STATUS = "active"

MAX_TENANT_ID_LENGTH = 50
MAX_TENANT_NAME_LENGTH = 100
MAX_TENANT_EMAIL_LENGTH = 150
MAX_TENANT_PHONE_LENGTH = 50
MAX_TENANT_NOTES_LENGTH = 2000

_CREATE_WORK_ORDERS_TABLE = (
    "CREATE TABLE IF NOT EXISTS work_orders ("
    "id TEXT PRIMARY KEY, "
    "unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE, "
    "tenant_id TEXT DEFAULT NULL REFERENCES tenants(id) ON DELETE SET NULL, "
    "session_id TEXT DEFAULT NULL, "
    "title TEXT NOT NULL, "
    "description TEXT NOT NULL, "
    "category TEXT NOT NULL DEFAULT 'general', "
    "priority TEXT NOT NULL DEFAULT 'medium', "
    "status TEXT NOT NULL DEFAULT 'submitted', "
    "entry_permission TEXT NOT NULL DEFAULT 'permission_granted', "
    "assigned_to TEXT NOT NULL DEFAULT '', "
    "scheduled_date TEXT NOT NULL DEFAULT '', "
    "completed_at TEXT DEFAULT NULL, "
    "resolution_notes TEXT NOT NULL DEFAULT '', "
    "estimated_cost REAL DEFAULT NULL, "
    "actual_cost REAL DEFAULT NULL, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_WORK_ORDERS_UNIT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_work_orders_unit_id ON work_orders(unit_id)"
)
_CREATE_WORK_ORDERS_TENANT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_work_orders_tenant_id ON work_orders(tenant_id)"
)
_CREATE_WORK_ORDERS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status)"
)
_CREATE_WORK_ORDERS_PRIORITY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_work_orders_priority ON work_orders(priority)"
)
_CREATE_WORK_ORDERS_CATEGORY_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_work_orders_category ON work_orders(category)"
)

VALID_WORK_ORDER_CATEGORIES = {
    "plumbing",
    "hvac",
    "electrical",
    "appliance",
    "pest",
    "structural",
    "security",
    "general",
}
DEFAULT_WORK_ORDER_CATEGORY = "general"

VALID_WORK_ORDER_PRIORITIES = {"low", "medium", "high", "emergency"}
DEFAULT_WORK_ORDER_PRIORITY = "medium"

VALID_WORK_ORDER_STATUSES = {
    "submitted",
    "scheduled",
    "in_progress",
    "on_hold",
    "completed",
    "cancelled",
}
DEFAULT_WORK_ORDER_STATUS = "submitted"

VALID_ENTRY_PERMISSIONS = {
    "permission_granted",
    "call_first",
    "appointment_only",
}
DEFAULT_ENTRY_PERMISSION = "permission_granted"

MAX_WORK_ORDER_ID_LENGTH = 50
MAX_WORK_ORDER_TITLE_LENGTH = 200
MAX_WORK_ORDER_DESC_LENGTH = 5000
MAX_WORK_ORDER_ASSIGNEE_LENGTH = 100
MAX_WORK_ORDER_NOTES_LENGTH = 3000

_CREATE_BILLING_TRANSACTIONS_TABLE = (
    "CREATE TABLE IF NOT EXISTS billing_transactions ("
    "id TEXT PRIMARY KEY, "
    "tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, "
    "unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE, "
    "session_id TEXT DEFAULT NULL, "
    "transaction_type TEXT NOT NULL DEFAULT 'rent', "
    "amount REAL NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'posted', "
    "due_date TEXT NOT NULL DEFAULT '', "
    "paid_at TEXT DEFAULT NULL, "
    "payment_method TEXT NOT NULL DEFAULT '', "
    "reference_number TEXT NOT NULL DEFAULT '', "
    "description TEXT NOT NULL, "
    "notes TEXT NOT NULL DEFAULT '', "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_BILLING_TRANSACTIONS_TENANT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_billing_transactions_tenant_id "
    "ON billing_transactions(tenant_id)"
)
_CREATE_BILLING_TRANSACTIONS_UNIT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_billing_transactions_unit_id ON billing_transactions(unit_id)"
)
_CREATE_BILLING_TRANSACTIONS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_billing_transactions_status ON billing_transactions(status)"
)
_CREATE_BILLING_TRANSACTIONS_TYPE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_billing_transactions_type "
    "ON billing_transactions(transaction_type)"
)
_CREATE_BILLING_TRANSACTIONS_DUE_DATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_billing_transactions_due_date "
    "ON billing_transactions(due_date)"
)

VALID_TRANSACTION_TYPES = {
    "rent",
    "security_deposit",
    "late_fee",
    "utility",
    "parking_fee",
    "pet_rent",
    "maintenance_charge",
    "payment",
    "credit_refund",
}
DEFAULT_TRANSACTION_TYPE = "rent"

VALID_TRANSACTION_STATUSES = {
    "posted",
    "pending",
    "paid",
    "overdue",
    "waived",
    "refunded",
}
DEFAULT_TRANSACTION_STATUS = "posted"

VALID_PAYMENT_METHODS = {
    "",
    "ach",
    "credit_card",
    "debit_card",
    "check",
    "money_order",
    "cashier_check",
    "online_portal",
}
DEFAULT_PAYMENT_METHOD = ""

MAX_TRANSACTION_ID_LENGTH = 50
MAX_TRANSACTION_DESC_LENGTH = 500
MAX_TRANSACTION_REF_LENGTH = 100
MAX_TRANSACTION_NOTES_LENGTH = 2000

_CREATE_LEASE_RENEWALS_TABLE = (
    "CREATE TABLE IF NOT EXISTS lease_renewals ("
    "id TEXT PRIMARY KEY, "
    "tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, "
    "unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE, "
    "session_id TEXT DEFAULT NULL, "
    "current_rent REAL NOT NULL, "
    "proposed_rent REAL NOT NULL, "
    "term_months INTEGER NOT NULL DEFAULT 12, "
    "start_date TEXT NOT NULL DEFAULT '', "
    "end_date TEXT NOT NULL DEFAULT '', "
    "concession_amount REAL NOT NULL DEFAULT 0.0, "
    "concession_notes TEXT NOT NULL DEFAULT '', "
    "security_deposit_change REAL NOT NULL DEFAULT 0.0, "
    "status TEXT NOT NULL DEFAULT 'offered', "
    "expires_at TEXT NOT NULL DEFAULT '', "
    "signature_name TEXT NOT NULL DEFAULT '', "
    "signature_ip TEXT NOT NULL DEFAULT '', "
    "signed_at TEXT DEFAULT NULL, "
    "notes TEXT NOT NULL DEFAULT '', "
    "document_file_id INTEGER DEFAULT NULL, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_LEASE_RENEWALS_TENANT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_lease_renewals_tenant_id ON lease_renewals(tenant_id)"
)
_CREATE_LEASE_RENEWALS_UNIT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_lease_renewals_unit_id ON lease_renewals(unit_id)"
)
_CREATE_LEASE_RENEWALS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_lease_renewals_status ON lease_renewals(status)"
)
_CREATE_LEASE_RENEWALS_EXPIRES_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_lease_renewals_expires_at ON lease_renewals(expires_at)"
)

VALID_LEASE_RENEWAL_STATUSES = {
    "draft",
    "offered",
    "negotiating",
    "accepted",
    "signed",
    "declined",
    "expired",
}
DEFAULT_LEASE_RENEWAL_STATUS = "offered"
VALID_RENEWAL_TERM_MONTHS = {1, 3, 6, 9, 12, 18, 24, 36}
DEFAULT_RENEWAL_TERM_MONTHS = 12

MAX_LEASE_RENEWAL_ID_LENGTH = 50
MAX_SIGNATURE_NAME_LENGTH = 150
MAX_SIGNATURE_IP_LENGTH = 50
MAX_CONCESSION_NOTES_LENGTH = 1000
MAX_LEASE_RENEWAL_NOTES_LENGTH = 3000

_CREATE_INSPECTIONS_TABLE = (
    "CREATE TABLE IF NOT EXISTS inspections ("
    "id TEXT PRIMARY KEY, "
    "tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, "
    "unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE, "
    "session_id TEXT DEFAULT NULL, "
    "inspection_type TEXT NOT NULL DEFAULT 'move_out', "
    "scheduled_date TEXT NOT NULL DEFAULT '', "
    "completed_date TEXT DEFAULT NULL, "
    "inspector_name TEXT NOT NULL DEFAULT 'Property Inspector', "
    "status TEXT NOT NULL DEFAULT 'scheduled', "
    "overall_condition TEXT NOT NULL DEFAULT 'good', "
    "items_json TEXT NOT NULL DEFAULT '[]', "
    "deposit_deduction_total REAL NOT NULL DEFAULT 0.0, "
    "deposit_refund_amount REAL NOT NULL DEFAULT 0.0, "
    "key_return_status TEXT NOT NULL DEFAULT 'pending', "
    "notes TEXT NOT NULL DEFAULT '', "
    "document_file_id INTEGER DEFAULT NULL, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)
_CREATE_INSPECTIONS_TENANT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_inspections_tenant_id ON inspections(tenant_id)"
)
_CREATE_INSPECTIONS_UNIT_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_inspections_unit_id ON inspections(unit_id)"
)
_CREATE_INSPECTIONS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(status)"
)
_CREATE_INSPECTIONS_TYPE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_inspections_type ON inspections(inspection_type)"
)
_CREATE_INSPECTIONS_SCHEDULED_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_inspections_scheduled_date ON inspections(scheduled_date)"
)

VALID_INSPECTION_TYPES = {
    "move_in",
    "move_out",
    "routine",
    "annual",
    "pre_move_out",
}
DEFAULT_INSPECTION_TYPE = "move_out"

VALID_INSPECTION_STATUSES = {
    "scheduled",
    "in_progress",
    "completed",
    "cancelled",
}
DEFAULT_INSPECTION_STATUS = "scheduled"

VALID_INSPECTION_CONDITIONS = {
    "excellent",
    "good",
    "fair",
    "poor",
    "damaged",
}
DEFAULT_INSPECTION_CONDITION = "good"

VALID_KEY_RETURN_STATUSES = {
    "pending",
    "returned",
    "missing_keys",
    "not_applicable",
}
DEFAULT_KEY_RETURN_STATUS = "pending"

VALID_INSPECTION_ITEM_ACTIONS = {"none", "clean", "repair", "replace"}
DEFAULT_INSPECTION_ITEM_ACTION = "none"

MAX_INSPECTION_ID_LENGTH = 50
MAX_INSPECTOR_NAME_LENGTH = 100
MAX_INSPECTION_NOTES_LENGTH = 3000

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
    ") AS escalation_tier, "
    "(SELECT tenant_id FROM session_labels WHERE session_id = l1.session_id) AS tenant_id, "
    "(SELECT unit_id FROM session_labels WHERE session_id = l1.session_id) AS unit_id "
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
    ") AS escalation_tier, "
    "(SELECT tenant_id FROM session_labels WHERE session_id = l1.session_id) AS tenant_id, "
    "(SELECT unit_id FROM session_labels WHERE session_id = l1.session_id) AS unit_id "
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


def _matches_session_filters(  # noqa: PLR0911, PLR0913, PLR0917
    s_dict: dict,
    status: str | None = None,
    tag: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> bool:
    if status and s_dict.get("status", "active").lower() != status.strip().lower():
        return False
    if tag:
        clean_tag = tag.strip().lower()
        raw_tags = s_dict.get("tags", "") or ""
        row_tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
        if clean_tag not in row_tags:
            return False
    if assigned_agent:
        clean_assigned = assigned_agent.strip().lower()
        row_assigned = (s_dict.get("assigned_agent") or "").strip().lower()
        if clean_assigned == "unassigned":
            if row_assigned:
                return False
        elif row_assigned != clean_assigned:
            return False
    if escalation_tier:
        clean_tier = escalation_tier.strip().lower()
        row_tier = (s_dict.get("escalation_tier") or DEFAULT_AGENT_TIER).strip().lower()
        if row_tier != clean_tier:
            return False
    if tenant_id and s_dict.get("tenant_id") != tenant_id.strip():
        return False
    if unit_id:
        clean_unit = unit_id.strip().lower()
        row_unit = (s_dict.get("unit_id") or "").strip().lower()
        if row_unit != clean_unit:
            return False
    return True


def get_all_sessions(  # noqa: PLR0913, PLR0917
    status: str | None = None,
    tag: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM ({_SELECT_ALL_SESSIONS_BASE}) ORDER BY last_active DESC"
        cursor.execute(query)
        sessions = cursor.fetchall()
        results = []
        for session in sessions:
            s_dict = dict(session)
            if not _matches_session_filters(
                s_dict, status, tag, assigned_agent, escalation_tier, tenant_id, unit_id
            ):
                continue
            if not s_dict.get("label"):
                s_dict["label"] = None
            if not s_dict.get("tenant_id"):
                s_dict["tenant_id"] = None
            if not s_dict.get("unit_id"):
                s_dict["unit_id"] = None
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
                    "tenant_id": row["tenant_id"] if row["tenant_id"] else None,
                    "unit_id": row["unit_id"] if row["unit_id"] else None,
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
    """Add newer columns (status, tags, summary, notes, priority, agent, tier, tenant, unit)."""
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
        if "tenant_id" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN tenant_id TEXT DEFAULT NULL")
        if "unit_id" not in columns:
            conn.execute("ALTER TABLE session_labels ADD COLUMN unit_id TEXT DEFAULT NULL")
        conn.commit()


def update_session_metadata(  # noqa: PLR0913, PLR0915, PLR0917
    session_id: str,
    label: str | None = None,
    status: str | None = None,
    tags: str | list[str] | None = None,
    summary: str | None = None,
    resolution_notes: str | None = None,
    priority: str | None = None,
    assigned_agent: str | None = None,
    escalation_tier: str | None = None,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> bool:
    """Update metadata (label, status, tags, summary, notes, priority, agent, tier, tenant)."""
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
    clean_tenant = None
    if tenant_id is not None:
        raw_tenant = tenant_id.strip()
        clean_tenant = (
            None if (not raw_tenant or raw_tenant.lower() in ("unassigned", "none")) else raw_tenant
        )
    clean_unit = None
    if unit_id is not None:
        raw_unit = unit_id.strip()
        clean_unit = (
            None if (not raw_unit or raw_unit.lower() in ("unassigned", "none")) else raw_unit
        )

    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return False

        cur = conn.execute(
            "SELECT label, status, tags, summary, resolution_notes, "
            "priority, assigned_agent, escalation_tier, tenant_id, unit_id "
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
            new_tenant = clean_tenant
            new_unit = clean_unit
            conn.execute(
                "INSERT INTO session_labels "
                "(session_id, label, status, tags, summary, resolution_notes, "
                "priority, assigned_agent, escalation_tier, tenant_id, unit_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    new_tenant,
                    new_unit,
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
            new_tenant = clean_tenant if tenant_id is not None else cur["tenant_id"]
            new_unit = clean_unit if unit_id is not None else cur["unit_id"]
            conn.execute(
                "UPDATE session_labels "
                "SET label = ?, status = ?, tags = ?, summary = ?, resolution_notes = ?, "
                "priority = ?, assigned_agent = ?, escalation_tier = ?, tenant_id = ?, unit_id = ? "
                "WHERE session_id = ?",
                (
                    new_label,
                    new_status,
                    new_tags,
                    new_summary,
                    new_notes,
                    new_priority,
                    new_agent,
                    new_tier,
                    new_tenant,
                    new_unit,
                    session_id,
                ),
            )
        conn.commit()
        return True


def get_session_metadata(session_id: str) -> dict | None:
    """Fetch label, status, tags, summary, notes, priority, agent, tier, tenant, and unit."""
    with closing(get_db_connection()) as conn:
        exists = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        if not exists:
            return None
        row = conn.execute(
            "SELECT label, status, tags, summary, resolution_notes, "
            "priority, assigned_agent, escalation_tier, tenant_id, unit_id "
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
                "tenant_id": None,
                "unit_id": None,
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
            "tenant_id": row["tenant_id"] if row["tenant_id"] else None,
            "unit_id": row["unit_id"] if row["unit_id"] else None,
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
            "Knowledge article content_markdown exceeds max length "
            f"{MAX_KNOWLEDGE_CONTENT_LENGTH}."
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
                "Knowledge article content_markdown exceeds max length "
                f"{MAX_KNOWLEDGE_CONTENT_LENGTH}."
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


DEFAULT_SEEDED_UNITS = [
    {
        "id": "unit_101",
        "property_name": "Sunset Heights Apartments",
        "unit_number": "101",
        "building_name": "Building A",
        "floor": 1,
        "address": "742 Evergreen Terrace",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62704",
        "monthly_rent": 1450.0,
        "parking_spot": "P-12",
        "gate_code": "#1010",
        "wifi_ssid": "SunsetHeights-Guest",
        "trash_day": "Tuesday",
        "notes": "Corner 1-bedroom unit near laundry facility.",
    },
    {
        "id": "unit_204",
        "property_name": "Sunset Heights Apartments",
        "unit_number": "204",
        "building_name": "Building B",
        "floor": 2,
        "address": "742 Evergreen Terrace",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62704",
        "monthly_rent": 1850.0,
        "parking_spot": "P-24",
        "gate_code": "#2040",
        "wifi_ssid": "SunsetHeights-Guest",
        "trash_day": "Tuesday",
        "notes": "2-bedroom unit with balcony facing courtyard.",
    },
    {
        "id": "unit_PH1",
        "property_name": "Oak Ridge Tower",
        "unit_number": "PH1",
        "building_name": "Main Tower",
        "floor": 12,
        "address": "100 Grand Avenue",
        "city": "Chicago",
        "state": "IL",
        "zip_code": "60611",
        "monthly_rent": 3200.0,
        "parking_spot": "G-01 (Covered)",
        "gate_code": "*9988",
        "wifi_ssid": "OakRidge-Residents",
        "trash_day": "Daily Valet Trash",
        "notes": "Penthouse suite with skyline view and smart lock.",
    },
]


def normalize_unit_id(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Unit ID must not be blank.")
    if len(cleaned) > MAX_UNIT_ID_LENGTH:
        raise ValueError(f"Unit ID must be at most {MAX_UNIT_ID_LENGTH} characters.")
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", cleaned):
        raise ValueError(
            "Unit ID may only contain alphanumeric characters, underscores, hyphens, and periods."
        )
    return cleaned


def normalize_property_name(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Property name must not be blank.")
    if len(cleaned) > MAX_PROPERTY_NAME_LENGTH:
        raise ValueError(f"Property name must be at most {MAX_PROPERTY_NAME_LENGTH} characters.")
    return cleaned


def normalize_unit_number(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Unit number must not be blank.")
    if len(cleaned) > MAX_UNIT_NUMBER_LENGTH:
        raise ValueError(f"Unit number must be at most {MAX_UNIT_NUMBER_LENGTH} characters.")
    return cleaned


def create_units() -> None:
    """Create units table, indexes, and pre-seed initial property units if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_UNITS_TABLE)
        conn.execute(_CREATE_UNITS_PROPERTY_INDEX)
        conn.execute(_CREATE_UNITS_UNIT_NUM_INDEX)
        row = conn.execute("SELECT COUNT(*) FROM units").fetchone()
        if row and row[0] == 0:
            for u in DEFAULT_SEEDED_UNITS:
                conn.execute(
                    "INSERT INTO units "
                    "(id, property_name, unit_number, building_name, floor, address, "
                    "city, state, zip_code, monthly_rent, parking_spot, gate_code, "
                    "wifi_ssid, trash_day, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        u["id"],
                        u["property_name"],
                        u["unit_number"],
                        u["building_name"],
                        u["floor"],
                        u["address"],
                        u["city"],
                        u["state"],
                        u["zip_code"],
                        u["monthly_rent"],
                        u["parking_spot"],
                        u["gate_code"],
                        u["wifi_ssid"],
                        u["trash_day"],
                        u["notes"],
                    ),
                )
        conn.commit()


def create_unit(  # noqa: PLR0913, PLR0917
    unit_id: str,
    property_name: str,
    unit_number: str,
    address: str,
    city: str,
    state: str,
    zip_code: str,
    building_name: str = "",
    floor: int = 1,
    monthly_rent: float = 0.0,
    parking_spot: str = "",
    gate_code: str = "",
    wifi_ssid: str = "",
    trash_day: str = "",
    notes: str = "",
) -> dict[str, Any]:
    norm_id = normalize_unit_id(unit_id)
    norm_prop = normalize_property_name(property_name)
    norm_num = normalize_unit_number(unit_number)
    clean_addr = (address or "").strip()
    if not clean_addr:
        raise ValueError("Address must not be blank.")
    if len(clean_addr) > MAX_ADDRESS_LENGTH:
        raise ValueError(f"Address must be at most {MAX_ADDRESS_LENGTH} characters.")
    clean_city = (city or "").strip()
    if not clean_city:
        raise ValueError("City must not be blank.")
    clean_state = (state or "").strip()
    if not clean_state:
        raise ValueError("State must not be blank.")
    clean_zip = (zip_code or "").strip()
    if not clean_zip:
        raise ValueError("Zip code must not be blank.")
    clean_bldg = (building_name or "").strip()
    clean_parking = (parking_spot or "").strip()
    clean_gate = (gate_code or "").strip()
    clean_wifi = (wifi_ssid or "").strip()
    clean_trash = (trash_day or "").strip()
    clean_notes = (notes or "").strip()
    rent_val = max(0.0, float(monthly_rent))
    floor_val = int(floor)

    with closing(get_db_connection()) as conn:
        existing = conn.execute("SELECT id FROM units WHERE id = ?", (norm_id,)).fetchone()
        if existing:
            raise ValueError(f"Unit with ID '{norm_id}' already exists.")
        conn.execute(
            "INSERT INTO units "
            "(id, property_name, unit_number, building_name, floor, address, "
            "city, state, zip_code, monthly_rent, parking_spot, gate_code, "
            "wifi_ssid, trash_day, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                norm_id,
                norm_prop,
                norm_num,
                clean_bldg,
                floor_val,
                clean_addr,
                clean_city,
                clean_state,
                clean_zip,
                rent_val,
                clean_parking,
                clean_gate,
                clean_wifi,
                clean_trash,
                clean_notes,
            ),
        )
        conn.commit()
    res = get_unit(norm_id)
    if res is None:
        raise RuntimeError("Failed to retrieve created unit.")
    return res


def get_unit(unit_id: str) -> dict[str, Any] | None:
    cleaned_id = (unit_id or "").strip()
    if not cleaned_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM units WHERE id = ?", (cleaned_id,)).fetchone()
        return dict(row) if row else None


def list_units(
    property_name: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    query_parts = ["SELECT * FROM units"]
    count_parts = ["SELECT COUNT(*) FROM units"]
    where_clauses: list[str] = []
    params: list[Any] = []

    if property_name and property_name.strip():
        where_clauses.append("LOWER(property_name) = LOWER(?)")
        params.append(property_name.strip())

    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        where_clauses.append(
            "(LOWER(unit_number) LIKE ? OR LOWER(property_name) LIKE ? OR LOWER(address) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    if where_clauses:
        clause_str = " WHERE " + " AND ".join(where_clauses)
        query_parts.append(clause_str)
        count_parts.append(clause_str)

    query_parts.append(" ORDER BY property_name ASC, unit_number ASC LIMIT ? OFFSET ?")

    with closing(get_db_connection()) as conn:
        count_cursor = conn.execute(" ".join(count_parts), tuple(params))
        total = int(count_cursor.fetchone()[0])
        list_params = list(params) + [max(1, limit), max(0, offset)]
        rows = conn.execute(" ".join(query_parts), tuple(list_params)).fetchall()
        return [dict(r) for r in rows], total


def update_unit(  # noqa: PLR0912, PLR0913, PLR0917
    unit_id: str,
    property_name: str | None = None,
    unit_number: str | None = None,
    building_name: str | None = None,
    floor: int | None = None,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
    monthly_rent: float | None = None,
    parking_spot: str | None = None,
    gate_code: str | None = None,
    wifi_ssid: str | None = None,
    trash_day: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    current = get_unit(unit_id)
    if not current:
        return None

    new_prop = (
        normalize_property_name(property_name)
        if property_name is not None
        else current["property_name"]
    )
    new_num = (
        normalize_unit_number(unit_number)
        if unit_number is not None
        else current["unit_number"]
    )
    new_bldg = (
        building_name.strip()
        if building_name is not None
        else current["building_name"]
    )
    new_floor = int(floor) if floor is not None else current["floor"]
    new_addr = address.strip() if address is not None else current["address"]
    new_city = city.strip() if city is not None else current["city"]
    new_state = state.strip() if state is not None else current["state"]
    new_zip = zip_code.strip() if zip_code is not None else current["zip_code"]
    new_rent = (
        max(0.0, float(monthly_rent))
        if monthly_rent is not None
        else current["monthly_rent"]
    )
    new_parking = (
        parking_spot.strip()
        if parking_spot is not None
        else current["parking_spot"]
    )
    new_gate = (
        gate_code.strip()
        if gate_code is not None
        else current["gate_code"]
    )
    new_wifi = (
        wifi_ssid.strip()
        if wifi_ssid is not None
        else current["wifi_ssid"]
    )
    new_trash = (
        trash_day.strip()
        if trash_day is not None
        else current["trash_day"]
    )
    new_notes = notes.strip() if notes is not None else current["notes"]

    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE units SET "
            "property_name = ?, unit_number = ?, building_name = ?, floor = ?, "
            "address = ?, city = ?, state = ?, zip_code = ?, monthly_rent = ?, "
            "parking_spot = ?, gate_code = ?, wifi_ssid = ?, trash_day = ?, "
            "notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                new_prop,
                new_num,
                new_bldg,
                new_floor,
                new_addr,
                new_city,
                new_state,
                new_zip,
                new_rent,
                new_parking,
                new_gate,
                new_wifi,
                new_trash,
                new_notes,
                unit_id,
            ),
        )
        conn.commit()
    return get_unit(unit_id)


def delete_unit(unit_id: str) -> bool:
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM units WHERE id = ?", (unit_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


DEFAULT_SEEDED_TENANTS = [
    {
        "id": "tenant_1",
        "first_name": "Sarah",
        "last_name": "Connor",
        "email": "sarah.connor@example.com",
        "phone": "+1-555-0199",
        "unit_id": "unit_101",
        "lease_start": "2026-01-01",
        "lease_end": "2026-12-31",
        "monthly_rent": 1450.0,
        "balance_due": 0.0,
        "status": "active",
        "emergency_contact_name": "John Connor",
        "emergency_contact_phone": "+1-555-0198",
        "notes": "Prefers email notifications for routine maintenance.",
    },
    {
        "id": "tenant_2",
        "first_name": "Marcus",
        "last_name": "Vance",
        "email": "marcus.vance@example.com",
        "phone": "+1-555-0244",
        "unit_id": "unit_204",
        "lease_start": "2025-06-01",
        "lease_end": "2026-05-31",
        "monthly_rent": 1850.0,
        "balance_due": 1850.0,
        "status": "past_due",
        "emergency_contact_name": "Elena Vance",
        "emergency_contact_phone": "+1-555-0245",
        "notes": "Late payment notice sent on the 5th.",
    },
    {
        "id": "tenant_3",
        "first_name": "Elena",
        "last_name": "Rostova",
        "email": "elena.rostova@example.com",
        "phone": "+1-555-0377",
        "unit_id": "unit_PH1",
        "lease_start": "2025-09-01",
        "lease_end": "2027-08-31",
        "monthly_rent": 3200.0,
        "balance_due": 0.0,
        "status": "active",
        "emergency_contact_name": "Dmitri Rostov",
        "emergency_contact_phone": "+1-555-0378",
        "notes": "Has registered pet (small dog). Executive corporate lease.",
    },
]


def normalize_tenant_id(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Tenant ID must not be blank.")
    if len(cleaned) > MAX_TENANT_ID_LENGTH:
        raise ValueError(f"Tenant ID must be at most {MAX_TENANT_ID_LENGTH} characters.")
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", cleaned):
        raise ValueError(
            "Tenant ID may only contain alphanumeric characters, underscores, hyphens, and periods."
        )
    return cleaned


def normalize_tenant_name(value: str | None, field_name: str = "Name") -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank.")
    if len(cleaned) > MAX_TENANT_NAME_LENGTH:
        raise ValueError(f"{field_name} must be at most {MAX_TENANT_NAME_LENGTH} characters.")
    return cleaned


def normalize_tenant_email(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        raise ValueError("Tenant email must not be blank.")
    if len(cleaned) > MAX_TENANT_EMAIL_LENGTH:
        raise ValueError(f"Tenant email must be at most {MAX_TENANT_EMAIL_LENGTH} characters.")
    if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
        raise ValueError(f"Invalid tenant email format: '{cleaned}'.")
    return cleaned


def normalize_tenant_phone(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Phone number must not be blank.")
    if len(cleaned) > MAX_TENANT_PHONE_LENGTH:
        raise ValueError(f"Phone number must be at most {MAX_TENANT_PHONE_LENGTH} characters.")
    return cleaned


def normalize_tenant_status(value: str | None) -> str:
    status = (value or DEFAULT_TENANT_STATUS).strip().lower()
    if status not in VALID_TENANT_STATUSES:
        valid_opts = ", ".join(sorted(VALID_TENANT_STATUSES))
        raise ValueError(f"Invalid tenant status '{status}'. Must be one of: {valid_opts}.")
    return status


def normalize_date_str(value: str | None, field_name: str = "Date") -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank.")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format, got '{cleaned}'.")
    return cleaned


def create_tenants() -> None:
    """Create tenants table, indexes, and pre-seed initial tenants if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_TENANTS_TABLE)
        conn.execute(_CREATE_TENANTS_EMAIL_INDEX)
        conn.execute(_CREATE_TENANTS_UNIT_INDEX)
        conn.execute(_CREATE_TENANTS_STATUS_INDEX)
        row = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()
        if row and row[0] == 0:
            for t in DEFAULT_SEEDED_TENANTS:
                conn.execute(
                    "INSERT INTO tenants "
                    "(id, first_name, last_name, email, phone, unit_id, "
                    "lease_start, lease_end, monthly_rent, balance_due, status, "
                    "emergency_contact_name, emergency_contact_phone, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        t["id"],
                        t["first_name"],
                        t["last_name"],
                        t["email"],
                        t["phone"],
                        t["unit_id"],
                        t["lease_start"],
                        t["lease_end"],
                        t["monthly_rent"],
                        t["balance_due"],
                        t["status"],
                        t["emergency_contact_name"],
                        t["emergency_contact_phone"],
                        t["notes"],
                    ),
                )
        conn.commit()


def create_tenant(  # noqa: PLR0913, PLR0917
    tenant_id: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    lease_start: str,
    lease_end: str,
    unit_id: str | None = None,
    monthly_rent: float = 0.0,
    balance_due: float = 0.0,
    status: str = DEFAULT_TENANT_STATUS,
    emergency_contact_name: str = "",
    emergency_contact_phone: str = "",
    notes: str = "",
) -> dict[str, Any]:
    norm_id = normalize_tenant_id(tenant_id)
    norm_first = normalize_tenant_name(first_name, "First name")
    norm_last = normalize_tenant_name(last_name, "Last name")
    norm_email = normalize_tenant_email(email)
    clean_phone = normalize_tenant_phone(phone)
    norm_start = normalize_date_str(lease_start, "Lease start date")
    norm_end = normalize_date_str(lease_end, "Lease end date")
    norm_status = normalize_tenant_status(status)
    clean_unit = unit_id.strip() if unit_id and str(unit_id).strip() else None
    rent_val = max(0.0, float(monthly_rent))
    balance_val = float(balance_due)
    clean_em_name = (emergency_contact_name or "").strip()
    clean_em_phone = (emergency_contact_phone or "").strip()
    clean_notes = (notes or "").strip()

    with closing(get_db_connection()) as conn:
        existing_id = conn.execute("SELECT id FROM tenants WHERE id = ?", (norm_id,)).fetchone()
        if existing_id:
            raise ValueError(f"Tenant with ID '{norm_id}' already exists.")
        existing_email = conn.execute(
            "SELECT id FROM tenants WHERE email = ?", (norm_email,)
        ).fetchone()
        if existing_email:
            raise ValueError(f"Tenant with email '{norm_email}' already exists.")

        conn.execute(
            "INSERT INTO tenants "
            "(id, first_name, last_name, email, phone, unit_id, "
            "lease_start, lease_end, monthly_rent, balance_due, status, "
            "emergency_contact_name, emergency_contact_phone, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                norm_id,
                norm_first,
                norm_last,
                norm_email,
                clean_phone,
                clean_unit,
                norm_start,
                norm_end,
                rent_val,
                balance_val,
                norm_status,
                clean_em_name,
                clean_em_phone,
                clean_notes,
            ),
        )
        conn.commit()
    res = get_tenant(norm_id)
    if res is None:
        raise RuntimeError("Failed to retrieve created tenant.")
    return res


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    cleaned_id = (tenant_id or "").strip()
    if not cleaned_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (cleaned_id,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_email(email: str) -> dict[str, Any] | None:
    cleaned = (email or "").strip().lower()
    if not cleaned:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM tenants WHERE LOWER(email) = ?", (cleaned,)).fetchone()
        return dict(row) if row else None


def list_tenants(
    unit_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    query_parts = ["SELECT * FROM tenants"]
    count_parts = ["SELECT COUNT(*) FROM tenants"]
    where_clauses: list[str] = []
    params: list[Any] = []

    if unit_id and unit_id.strip():
        where_clauses.append("unit_id = ?")
        params.append(unit_id.strip())

    if status and status.strip():
        where_clauses.append("status = ?")
        params.append(status.strip().lower())

    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        where_clauses.append(
            "(LOWER(first_name) LIKE ? OR LOWER(last_name) LIKE ? OR "
            "LOWER(email) LIKE ? OR LOWER(phone) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern, pattern])

    if where_clauses:
        clause_str = " WHERE " + " AND ".join(where_clauses)
        query_parts.append(clause_str)
        count_parts.append(clause_str)

    query_parts.append(" ORDER BY last_name ASC, first_name ASC LIMIT ? OFFSET ?")

    with closing(get_db_connection()) as conn:
        count_cursor = conn.execute(" ".join(count_parts), tuple(params))
        total = int(count_cursor.fetchone()[0])
        list_params = list(params) + [max(1, limit), max(0, offset)]
        rows = conn.execute(" ".join(query_parts), tuple(list_params)).fetchall()
        return [dict(r) for r in rows], total


def update_tenant(  # noqa: PLR0912, PLR0913, PLR0917
    tenant_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    unit_id: str | None = None,
    lease_start: str | None = None,
    lease_end: str | None = None,
    monthly_rent: float | None = None,
    balance_due: float | None = None,
    status: str | None = None,
    emergency_contact_name: str | None = None,
    emergency_contact_phone: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    current = get_tenant(tenant_id)
    if not current:
        return None

    new_first = (
        normalize_tenant_name(first_name, "First name")
        if first_name is not None
        else current["first_name"]
    )
    new_last = (
        normalize_tenant_name(last_name, "Last name")
        if last_name is not None
        else current["last_name"]
    )
    new_email = (
        normalize_tenant_email(email)
        if email is not None
        else current["email"]
    )
    new_phone = phone.strip() if phone is not None else current["phone"]
    new_unit = unit_id.strip() if unit_id is not None else current["unit_id"]
    new_start = (
        normalize_date_str(lease_start, "Lease start date")
        if lease_start is not None
        else current["lease_start"]
    )
    new_end = (
        normalize_date_str(lease_end, "Lease end date")
        if lease_end is not None
        else current["lease_end"]
    )
    new_rent = (
        max(0.0, float(monthly_rent))
        if monthly_rent is not None
        else current["monthly_rent"]
    )
    new_balance = (
        float(balance_due)
        if balance_due is not None
        else current["balance_due"]
    )
    new_status = (
        normalize_tenant_status(status)
        if status is not None
        else current["status"]
    )
    new_em_name = (
        emergency_contact_name.strip()
        if emergency_contact_name is not None
        else current["emergency_contact_name"]
    )
    new_em_phone = (
        emergency_contact_phone.strip()
        if emergency_contact_phone is not None
        else current["emergency_contact_phone"]
    )
    new_notes = notes.strip() if notes is not None else current["notes"]

    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE tenants SET "
            "first_name = ?, last_name = ?, email = ?, phone = ?, unit_id = ?, "
            "lease_start = ?, lease_end = ?, monthly_rent = ?, balance_due = ?, "
            "status = ?, emergency_contact_name = ?, emergency_contact_phone = ?, "
            "notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                new_first,
                new_last,
                new_email,
                new_phone,
                new_unit,
                new_start,
                new_end,
                new_rent,
                new_balance,
                new_status,
                new_em_name,
                new_em_phone,
                new_notes,
                tenant_id,
            ),
        )
        conn.commit()
    return get_tenant(tenant_id)


def delete_tenant(tenant_id: str) -> bool:
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def get_session_tenant_context(session_id: str) -> dict[str, Any] | None:
    """Fetch consolidated tenant and unit profile context for a session."""
    with closing(get_db_connection()) as conn:
        has_logs = conn.execute(_SESSION_HAS_LOGS, (session_id,)).fetchone() is not None
        lbl = conn.execute(
            "SELECT tenant_id, unit_id FROM session_labels WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not has_logs and lbl is None:
            return None

        tenant_id = lbl["tenant_id"] if lbl and lbl["tenant_id"] else None
        unit_id = lbl["unit_id"] if lbl and lbl["unit_id"] else None

    tenant = get_tenant(tenant_id) if tenant_id else None
    effective_unit_id = unit_id or (tenant.get("unit_id") if tenant else None)
    unit = get_unit(effective_unit_id) if effective_unit_id else None

    return {
        "session_id": session_id,
        "tenant_id": tenant_id,
        "unit_id": effective_unit_id,
        "tenant": tenant,
        "unit": unit,
    }


def link_session_tenant(
    session_id: str,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> dict[str, Any]:
    """Link a customer support session to a tenant and/or unit."""
    cleaned_tenant = tenant_id.strip() if tenant_id and tenant_id.strip() else None
    if cleaned_tenant and cleaned_tenant.lower() in ("unassigned", "none"):
        cleaned_tenant = None

    cleaned_unit = unit_id.strip() if unit_id and unit_id.strip() else None
    if cleaned_unit and cleaned_unit.lower() in ("unassigned", "none"):
        cleaned_unit = None

    if cleaned_tenant is not None:
        tenant = get_tenant(cleaned_tenant)
        if tenant is None:
            raise ValueError(f"Tenant '{cleaned_tenant}' not found.")
        if cleaned_unit is None and tenant.get("unit_id"):
            cleaned_unit = tenant["unit_id"]

    if cleaned_unit is not None:
        unit = get_unit(cleaned_unit)
        if unit is None:
            raise ValueError(f"Unit '{cleaned_unit}' not found.")

    with closing(get_db_connection()) as conn:
        cur = conn.execute(
            "SELECT session_id FROM session_labels WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if cur is None:
            conn.execute(
                "INSERT INTO session_labels "
                "(session_id, label, status, tags, summary, resolution_notes, "
                "priority, assigned_agent, escalation_tier, tenant_id, unit_id) "
                "VALUES (?, '', 'active', '', '', '', 'medium', NULL, 'tier_1', ?, ?)",
                (session_id, cleaned_tenant, cleaned_unit),
            )
        else:
            conn.execute(
                "UPDATE session_labels SET tenant_id = ?, unit_id = ? WHERE session_id = ?",
                (cleaned_tenant, cleaned_unit, session_id),
            )
        conn.commit()

    context = get_session_tenant_context(session_id)
    if context is None:
        tenant = get_tenant(cleaned_tenant) if cleaned_tenant else None
        effective_unit_id = cleaned_unit or (tenant.get("unit_id") if tenant else None)
        unit = get_unit(effective_unit_id) if effective_unit_id else None
        return {
            "session_id": session_id,
            "tenant_id": cleaned_tenant,
            "unit_id": effective_unit_id,
            "tenant": tenant,
            "unit": unit,
        }
    return context


def get_tenant_support_history(tenant_id: str) -> dict[str, Any]:
    """Retrieve full support and ticket history for a tenant across all linked sessions."""
    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f"Tenant '{tenant_id}' not found.")

    with closing(get_db_connection()) as conn:
        query = (
            "SELECT sl.session_id, sl.label, sl.status, sl.tags, sl.summary, "
            "sl.resolution_notes, sl.priority, sl.assigned_agent, sl.escalation_tier, "
            "sl.unit_id, "
            "MIN(al.created_at) AS created_at, "
            "MAX(al.created_at) AS last_active, "
            "COUNT(al.id) AS message_count, "
            "(SELECT al2.user_query FROM application_logs al2 "
            "WHERE al2.session_id = sl.session_id ORDER BY al2.id ASC LIMIT 1) AS preview "
            "FROM session_labels sl "
            "LEFT JOIN application_logs al ON al.session_id = sl.session_id "
            "WHERE sl.tenant_id = ? "
            "GROUP BY sl.session_id "
            "ORDER BY last_active DESC"
        )
        rows = conn.execute(query, (tenant["id"],)).fetchall()
        sessions = []
        for r in rows:
            sid = r["session_id"]
            fb_row = conn.execute(
                "SELECT rating, comment, score FROM feedback "
                "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (sid,),
            ).fetchone()
            rating = fb_row["rating"] if fb_row else None
            fb_score = fb_row["score"] if fb_row else None
            fb_comment = fb_row["comment"] if fb_row else None

            sessions.append({
                "session_id": sid,
                "label": r["label"] if r["label"] else None,
                "status": r["status"] if r["status"] else "active",
                "priority": r["priority"] if r["priority"] else DEFAULT_SESSION_PRIORITY,
                "assigned_agent": r["assigned_agent"] if r["assigned_agent"] else None,
                "escalation_tier": (
                    r["escalation_tier"] if r["escalation_tier"] else DEFAULT_AGENT_TIER
                ),
                "tags": r["tags"] if r["tags"] else "",
                "summary": r["summary"] if r["summary"] else "",
                "resolution_notes": r["resolution_notes"] if r["resolution_notes"] else "",
                "unit_id": r["unit_id"] if r["unit_id"] else tenant.get("unit_id"),
                "message_count": r["message_count"] or 0,
                "preview": _truncate_preview(r["preview"]),
                "created_at": r["created_at"],
                "last_active": r["last_active"],
                "rating": rating,
                "feedback_score": fb_score,
                "feedback_comment": fb_comment,
            })

        return {
            "tenant": tenant,
            "total_sessions": len(sessions),
            "sessions": sessions,
        }


DEFAULT_SEEDED_WORK_ORDERS = [
    {
        "id": "wo_101",
        "unit_id": "unit_101",
        "tenant_id": "tenant_1",
        "session_id": None,
        "title": "Kitchen faucet leaking constantly",
        "description": "Steady drip from the base of the kitchen faucet. Bucket placed underneath.",
        "category": "plumbing",
        "priority": "medium",
        "status": "scheduled",
        "entry_permission": "permission_granted",
        "assigned_to": "Apex Plumbing Services",
        "scheduled_date": "2026-10-18T10:00:00",
        "completed_at": None,
        "resolution_notes": "",
        "estimated_cost": 150.0,
        "actual_cost": None,
    },
    {
        "id": "wo_102",
        "unit_id": "unit_204",
        "tenant_id": "tenant_2",
        "session_id": None,
        "title": "Living room AC blowing ambient air",
        "description": "AC unit runs and blows air but does not cool below 78 degrees.",
        "category": "hvac",
        "priority": "high",
        "status": "in_progress",
        "entry_permission": "call_first",
        "assigned_to": "CoolTech HVAC Solutions",
        "scheduled_date": "2026-10-16T14:00:00",
        "completed_at": None,
        "resolution_notes": "Technician dispatched to inspect compressor and refrigerant levels.",
        "estimated_cost": 320.0,
        "actual_cost": None,
    },
    {
        "id": "wo_103",
        "unit_id": "unit_PH1",
        "tenant_id": "tenant_3",
        "session_id": None,
        "title": "Dishwasher not draining after wash cycle",
        "description": "Standing water remaining in bottom of dishwasher basin.",
        "category": "appliance",
        "priority": "low",
        "status": "completed",
        "entry_permission": "appointment_only",
        "assigned_to": "Swift Appliance Repair",
        "scheduled_date": "2026-10-10T11:00:00",
        "completed_at": "2026-10-10T12:30:00",
        "resolution_notes": "Cleared clogged drain filter and verified pump operation.",
        "estimated_cost": 120.0,
        "actual_cost": 115.0,
    },
]


def normalize_work_order_id(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Work order ID must not be blank.")
    if len(cleaned) > MAX_WORK_ORDER_ID_LENGTH:
        raise ValueError(f"Work order ID must be at most {MAX_WORK_ORDER_ID_LENGTH} characters.")
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", cleaned):
        raise ValueError(
            "Work order ID may only contain alphanumeric characters, "
            "underscores, hyphens, and periods."
        )
    return cleaned


def normalize_work_order_title(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Work order title must not be blank.")
    if len(cleaned) > MAX_WORK_ORDER_TITLE_LENGTH:
        raise ValueError(
            f"Work order title must be at most {MAX_WORK_ORDER_TITLE_LENGTH} characters."
        )
    return cleaned


def normalize_work_order_category(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_WORK_ORDER_CATEGORY
    if cleaned not in VALID_WORK_ORDER_CATEGORIES:
        valid_cats = ", ".join(sorted(VALID_WORK_ORDER_CATEGORIES))
        raise ValueError(
            f"Invalid work order category '{cleaned}'. Expected one of: {valid_cats}."
        )
    return cleaned


def normalize_work_order_priority(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_WORK_ORDER_PRIORITY
    if cleaned not in VALID_WORK_ORDER_PRIORITIES:
        valid_pris = ", ".join(sorted(VALID_WORK_ORDER_PRIORITIES))
        raise ValueError(
            f"Invalid work order priority '{cleaned}'. Expected one of: {valid_pris}."
        )
    return cleaned


def normalize_work_order_status(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_WORK_ORDER_STATUS
    if cleaned not in VALID_WORK_ORDER_STATUSES:
        valid_stats = ", ".join(sorted(VALID_WORK_ORDER_STATUSES))
        raise ValueError(
            f"Invalid work order status '{cleaned}'. Expected one of: {valid_stats}."
        )
    return cleaned


def normalize_entry_permission(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_ENTRY_PERMISSION
    if cleaned not in VALID_ENTRY_PERMISSIONS:
        valid_perms = ", ".join(sorted(VALID_ENTRY_PERMISSIONS))
        raise ValueError(
            f"Invalid entry permission '{cleaned}'. Expected one of: {valid_perms}."
        )
    return cleaned


def create_work_orders() -> None:
    """Create work_orders table, indexes, and pre-seed initial records if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_WORK_ORDERS_TABLE)
        conn.execute(_CREATE_WORK_ORDERS_UNIT_INDEX)
        conn.execute(_CREATE_WORK_ORDERS_TENANT_INDEX)
        conn.execute(_CREATE_WORK_ORDERS_STATUS_INDEX)
        conn.execute(_CREATE_WORK_ORDERS_PRIORITY_INDEX)
        conn.execute(_CREATE_WORK_ORDERS_CATEGORY_INDEX)
        row = conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()
        if row and row[0] == 0:
            for w in DEFAULT_SEEDED_WORK_ORDERS:
                conn.execute(
                    "INSERT INTO work_orders "
                    "(id, unit_id, tenant_id, session_id, title, description, "
                    "category, priority, status, entry_permission, assigned_to, "
                    "scheduled_date, completed_at, resolution_notes, "
                    "estimated_cost, actual_cost) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        w["id"],
                        w["unit_id"],
                        w["tenant_id"],
                        w["session_id"],
                        w["title"],
                        w["description"],
                        w["category"],
                        w["priority"],
                        w["status"],
                        w["entry_permission"],
                        w["assigned_to"],
                        w["scheduled_date"],
                        w["completed_at"],
                        w["resolution_notes"],
                        w["estimated_cost"],
                        w["actual_cost"],
                    ),
                )
        conn.commit()


def create_work_order(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    work_order_id: str,
    unit_id: str,
    title: str,
    description: str,
    category: str = "general",
    priority: str = "medium",
    status: str = "submitted",
    tenant_id: str | None = None,
    session_id: str | None = None,
    entry_permission: str = "permission_granted",
    assigned_to: str = "",
    scheduled_date: str = "",
    completed_at: str | None = None,
    resolution_notes: str = "",
    estimated_cost: float | None = None,
    actual_cost: float | None = None,
) -> dict[str, Any]:
    norm_id = normalize_work_order_id(work_order_id)
    norm_unit = normalize_unit_id(unit_id)
    norm_title = normalize_work_order_title(title)
    clean_desc = (description or "").strip()
    if not clean_desc:
        raise ValueError("Work order description must not be blank.")
    if len(clean_desc) > MAX_WORK_ORDER_DESC_LENGTH:
        raise ValueError(
            f"Work order description must be at most {MAX_WORK_ORDER_DESC_LENGTH} characters."
        )
    norm_cat = normalize_work_order_category(category)
    norm_priority = normalize_work_order_priority(priority)
    norm_status = normalize_work_order_status(status)
    norm_entry = normalize_entry_permission(entry_permission)

    clean_tenant = (tenant_id or "").strip() or None
    clean_session = (session_id or "").strip() or None
    clean_assignee = (assigned_to or "").strip()
    if len(clean_assignee) > MAX_WORK_ORDER_ASSIGNEE_LENGTH:
        raise ValueError(
            f"Assigned to must be at most {MAX_WORK_ORDER_ASSIGNEE_LENGTH} characters."
        )
    clean_date = (scheduled_date or "").strip()
    clean_notes = (resolution_notes or "").strip()
    if len(clean_notes) > MAX_WORK_ORDER_NOTES_LENGTH:
        raise ValueError(
            f"Resolution notes must be at most {MAX_WORK_ORDER_NOTES_LENGTH} characters."
        )

    clean_completed = (completed_at or "").strip() or None
    if norm_status == "completed" and clean_completed is None:
        clean_completed = datetime.now(UTC).isoformat()

    est_val = float(estimated_cost) if estimated_cost is not None else None
    act_val = float(actual_cost) if actual_cost is not None else None

    with closing(get_db_connection()) as conn:
        unit_row = conn.execute("SELECT id FROM units WHERE id = ?", (norm_unit,)).fetchone()
        if not unit_row:
            raise ValueError(f"Unit with ID '{norm_unit}' does not exist.")

        if clean_tenant:
            tenant_row = conn.execute(
                "SELECT id FROM tenants WHERE id = ?", (clean_tenant,)
            ).fetchone()
            if not tenant_row:
                raise ValueError(f"Tenant with ID '{clean_tenant}' does not exist.")

        existing = conn.execute(
            "SELECT id FROM work_orders WHERE id = ?", (norm_id,)
        ).fetchone()
        if existing:
            raise ValueError(f"Work order with ID '{norm_id}' already exists.")

        conn.execute(
            "INSERT INTO work_orders "
            "(id, unit_id, tenant_id, session_id, title, description, "
            "category, priority, status, entry_permission, assigned_to, "
            "scheduled_date, completed_at, resolution_notes, "
            "estimated_cost, actual_cost) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                norm_id,
                norm_unit,
                clean_tenant,
                clean_session,
                norm_title,
                clean_desc,
                norm_cat,
                norm_priority,
                norm_status,
                norm_entry,
                clean_assignee,
                clean_date,
                clean_completed,
                clean_notes,
                est_val,
                act_val,
            ),
        )
        conn.commit()

    res = get_work_order(norm_id)
    if res is None:
        raise RuntimeError("Failed to retrieve created work order.")
    return res


def get_work_order(work_order_id: str) -> dict[str, Any] | None:
    cleaned_id = (work_order_id or "").strip()
    if not cleaned_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (cleaned_id,)).fetchone()
        return dict(row) if row else None


def list_work_orders(  # noqa: PLR0912, PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    query_parts = ["SELECT * FROM work_orders"]
    count_parts = ["SELECT COUNT(*) FROM work_orders"]
    where_clauses: list[str] = []
    params: list[Any] = []

    if unit_id and unit_id.strip():
        where_clauses.append("unit_id = ?")
        params.append(unit_id.strip())

    if tenant_id and tenant_id.strip():
        where_clauses.append("tenant_id = ?")
        params.append(tenant_id.strip())

    if status and status.strip():
        where_clauses.append("status = ?")
        params.append(status.strip().lower())

    if priority and priority.strip():
        where_clauses.append("priority = ?")
        params.append(priority.strip().lower())

    if category and category.strip():
        where_clauses.append("category = ?")
        params.append(category.strip().lower())

    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        where_clauses.append(
            "(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(assigned_to) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    if where_clauses:
        clause_str = " WHERE " + " AND ".join(where_clauses)
        query_parts.append(clause_str)
        count_parts.append(clause_str)

    order_clause = (
        " ORDER BY CASE priority "
        "WHEN 'emergency' THEN 1 "
        "WHEN 'high' THEN 2 "
        "WHEN 'medium' THEN 3 "
        "WHEN 'low' THEN 4 "
        "ELSE 5 END ASC, created_at DESC LIMIT ? OFFSET ?"
    )
    query_parts.append(order_clause)

    with closing(get_db_connection()) as conn:
        count_cursor = conn.execute(" ".join(count_parts), tuple(params))
        total = int(count_cursor.fetchone()[0])
        list_params = list(params) + [max(1, limit), max(0, offset)]
        rows = conn.execute(" ".join(query_parts), tuple(list_params)).fetchall()
        return [dict(r) for r in rows], total


def update_work_order(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    work_order_id: str,
    title: str | None = None,
    description: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    entry_permission: str | None = None,
    assigned_to: str | None = None,
    scheduled_date: str | None = None,
    completed_at: str | None = None,
    resolution_notes: str | None = None,
    estimated_cost: float | None = None,
    actual_cost: float | None = None,
    unit_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any] | None:
    current = get_work_order(work_order_id)
    if not current:
        return None

    new_title = (
        normalize_work_order_title(title) if title is not None else current["title"]
    )
    new_desc = description.strip() if description is not None else current["description"]
    if not new_desc:
        raise ValueError("Work order description must not be blank.")
    if len(new_desc) > MAX_WORK_ORDER_DESC_LENGTH:
        raise ValueError(
            f"Work order description must be at most {MAX_WORK_ORDER_DESC_LENGTH} characters."
        )

    new_cat = (
        normalize_work_order_category(category) if category is not None else current["category"]
    )
    new_priority = (
        normalize_work_order_priority(priority) if priority is not None else current["priority"]
    )
    new_status = (
        normalize_work_order_status(status) if status is not None else current["status"]
    )
    new_entry = (
        normalize_entry_permission(entry_permission)
        if entry_permission is not None
        else current["entry_permission"]
    )
    new_assignee = (
        assigned_to.strip() if assigned_to is not None else current["assigned_to"]
    )
    if len(new_assignee) > MAX_WORK_ORDER_ASSIGNEE_LENGTH:
        raise ValueError(
            f"Assigned to must be at most {MAX_WORK_ORDER_ASSIGNEE_LENGTH} characters."
        )
    new_date = (
        scheduled_date.strip() if scheduled_date is not None else current["scheduled_date"]
    )
    new_notes = (
        resolution_notes.strip() if resolution_notes is not None else current["resolution_notes"]
    )
    if len(new_notes) > MAX_WORK_ORDER_NOTES_LENGTH:
        raise ValueError(
            f"Resolution notes must be at most {MAX_WORK_ORDER_NOTES_LENGTH} characters."
        )

    new_completed = current["completed_at"]
    if completed_at is not None:
        new_completed = completed_at.strip() or None
    elif new_status == "completed" and current["status"] != "completed" and not new_completed:
        new_completed = datetime.now(UTC).isoformat()

    new_est = (
        float(estimated_cost) if estimated_cost is not None else current["estimated_cost"]
    )
    new_act = (
        float(actual_cost) if actual_cost is not None else current["actual_cost"]
    )
    new_unit = unit_id.strip() if unit_id is not None else current["unit_id"]
    new_tenant = tenant_id.strip() if tenant_id is not None else current["tenant_id"]

    with closing(get_db_connection()) as conn:
        if unit_id is not None:
            unit_exists = conn.execute(
                "SELECT id FROM units WHERE id = ?", (new_unit,)
            ).fetchone()
            if not unit_exists:
                raise ValueError(f"Unit with ID '{new_unit}' does not exist.")

        if tenant_id is not None and new_tenant:
            tenant_exists = conn.execute(
                "SELECT id FROM tenants WHERE id = ?", (new_tenant,)
            ).fetchone()
            if not tenant_exists:
                raise ValueError(f"Tenant with ID '{new_tenant}' does not exist.")

        conn.execute(
            "UPDATE work_orders SET "
            "unit_id = ?, tenant_id = ?, title = ?, description = ?, "
            "category = ?, priority = ?, status = ?, entry_permission = ?, "
            "assigned_to = ?, scheduled_date = ?, completed_at = ?, "
            "resolution_notes = ?, estimated_cost = ?, actual_cost = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                new_unit,
                new_tenant,
                new_title,
                new_desc,
                new_cat,
                new_priority,
                new_status,
                new_entry,
                new_assignee,
                new_date,
                new_completed,
                new_notes,
                new_est,
                new_act,
                work_order_id,
            ),
        )
        conn.commit()

    return get_work_order(work_order_id)


def delete_work_order(work_order_id: str) -> bool:
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM work_orders WHERE id = ?", (work_order_id,))
        conn.commit()
        return bool(cursor.rowcount and cursor.rowcount > 0)


def get_unit_work_orders(unit_id: str, open_only: bool = False) -> list[dict[str, Any]]:
    cleaned_unit = (unit_id or "").strip()
    if not cleaned_unit:
        return []
    query = (
        "SELECT * FROM work_orders WHERE unit_id = ?"
    )
    if open_only:
        query += " AND status NOT IN ('completed', 'cancelled')"
    query += " ORDER BY created_at DESC"
    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, (cleaned_unit,)).fetchall()
        return [dict(r) for r in rows]


def get_tenant_work_orders(tenant_id: str, open_only: bool = False) -> list[dict[str, Any]]:
    cleaned_tenant = (tenant_id or "").strip()
    if not cleaned_tenant:
        return []
    query = (
        "SELECT * FROM work_orders WHERE tenant_id = ?"
    )
    if open_only:
        query += " AND status NOT IN ('completed', 'cancelled')"
    query += " ORDER BY created_at DESC"
    with closing(get_db_connection()) as conn:
        rows = conn.execute(query, (cleaned_tenant,)).fetchall()
        return [dict(r) for r in rows]


def get_work_order_summary_metrics() -> dict[str, Any]:
    with closing(get_db_connection()) as conn:
        total_row = conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()
        total = int(total_row[0]) if total_row else 0

        open_row = conn.execute(
            "SELECT COUNT(*) FROM work_orders WHERE status NOT IN ('completed', 'cancelled')"
        ).fetchone()
        open_count = int(open_row[0]) if open_row else 0

        emergency_row = conn.execute(
            "SELECT COUNT(*) FROM work_orders "
            "WHERE priority = 'emergency' AND status NOT IN ('completed', 'cancelled')"
        ).fetchone()
        emergency_count = int(emergency_row[0]) if emergency_row else 0

        completed_row = conn.execute(
            "SELECT COUNT(*) FROM work_orders WHERE status = 'completed'"
        ).fetchone()
        completed_count = int(completed_row[0]) if completed_row else 0

        in_progress_row = conn.execute(
            "SELECT COUNT(*) FROM work_orders WHERE status = 'in_progress'"
        ).fetchone()
        in_progress_count = int(in_progress_row[0]) if in_progress_row else 0

        status_rows = conn.execute(
            "SELECT status, COUNT(*) FROM work_orders GROUP BY status"
        ).fetchall()
        by_status = {r[0]: int(r[1]) for r in status_rows}

        priority_rows = conn.execute(
            "SELECT priority, COUNT(*) FROM work_orders GROUP BY priority"
        ).fetchall()
        by_priority = {r[0]: int(r[1]) for r in priority_rows}

        category_rows = conn.execute(
            "SELECT category, COUNT(*) FROM work_orders GROUP BY category"
        ).fetchall()
        by_category = {r[0]: int(r[1]) for r in category_rows}

        costs_row = conn.execute(
            "SELECT COALESCE(SUM(estimated_cost), 0.0), COALESCE(SUM(actual_cost), 0.0) "
            "FROM work_orders"
        ).fetchone()
        est_cost = float(costs_row[0]) if costs_row else 0.0
        act_cost = float(costs_row[1]) if costs_row else 0.0

        return {
            "total_work_orders": total,
            "open_work_orders": open_count,
            "emergency_work_orders": emergency_count,
            "in_progress_work_orders": in_progress_count,
            "completed_work_orders": completed_count,
            "by_status": by_status,
            "by_priority": by_priority,
            "by_category": by_category,
            "total_estimated_cost": est_cost,
            "total_actual_cost": act_cost,
        }


DEFAULT_SEEDED_BILLING_TRANSACTIONS = [
    {
        "id": "tx_101",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "session_id": None,
        "transaction_type": "payment",
        "amount": 1450.0,
        "status": "paid",
        "due_date": "2026-10-01",
        "paid_at": "2026-10-01T09:30:00Z",
        "payment_method": "ach",
        "reference_number": "ACH-88412",
        "description": "October 2026 Monthly Rent",
        "notes": "Auto-pay processed successfully.",
    },
    {
        "id": "tx_102",
        "tenant_id": "tenant_2",
        "unit_id": "unit_204",
        "session_id": None,
        "transaction_type": "rent",
        "amount": 1850.0,
        "status": "overdue",
        "due_date": "2026-10-01",
        "paid_at": None,
        "payment_method": "",
        "reference_number": "",
        "description": "October 2026 Monthly Rent",
        "notes": "Payment overdue past 5-day grace period.",
    },
    {
        "id": "tx_103",
        "tenant_id": "tenant_2",
        "unit_id": "unit_204",
        "session_id": None,
        "transaction_type": "late_fee",
        "amount": 75.0,
        "status": "overdue",
        "due_date": "2026-10-06",
        "paid_at": None,
        "payment_method": "",
        "reference_number": "",
        "description": "Late Fee - October Unpaid Rent",
        "notes": "Standard late fee assessed after grace period.",
    },
    {
        "id": "tx_104",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "session_id": None,
        "transaction_type": "payment",
        "amount": 3200.0,
        "status": "paid",
        "due_date": "2026-10-01",
        "paid_at": "2026-09-30T16:45:00Z",
        "payment_method": "online_portal",
        "reference_number": "PORTAL-77194",
        "description": "October 2026 Monthly Rent",
        "notes": "Early payment received via resident portal.",
    },
]


def normalize_transaction_id(tx_id: str) -> str:
    cleaned = (tx_id or "").strip()
    if not cleaned:
        raise ValueError("Transaction ID must not be blank.")
    if len(cleaned) > MAX_TRANSACTION_ID_LENGTH:
        raise ValueError(
            f"Transaction ID must be at most {MAX_TRANSACTION_ID_LENGTH} characters."
        )
    return cleaned


def normalize_transaction_type(val: str) -> str:
    cleaned = (val or "").strip().lower()
    if not cleaned:
        return DEFAULT_TRANSACTION_TYPE
    if cleaned not in VALID_TRANSACTION_TYPES:
        valid_types = ", ".join(sorted(VALID_TRANSACTION_TYPES))
        raise ValueError(
            f"Invalid transaction type '{cleaned}'. Expected one of: {valid_types}."
        )
    return cleaned


def normalize_transaction_status(val: str) -> str:
    cleaned = (val or "").strip().lower()
    if not cleaned:
        return DEFAULT_TRANSACTION_STATUS
    if cleaned not in VALID_TRANSACTION_STATUSES:
        valid_statuses = ", ".join(sorted(VALID_TRANSACTION_STATUSES))
        raise ValueError(
            f"Invalid transaction status '{cleaned}'. Expected one of: {valid_statuses}."
        )
    return cleaned


def normalize_payment_method(val: str) -> str:
    cleaned = (val or "").strip().lower()
    if cleaned not in VALID_PAYMENT_METHODS:
        valid_methods = ", ".join(sorted(m for m in VALID_PAYMENT_METHODS if m))
        raise ValueError(
            f"Invalid payment method '{cleaned}'. Expected one of: {valid_methods}."
        )
    return cleaned


def create_billing_transactions() -> None:
    """Create billing_transactions table, indexes, and pre-seed initial records if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_BILLING_TRANSACTIONS_TABLE)
        conn.execute(_CREATE_BILLING_TRANSACTIONS_TENANT_INDEX)
        conn.execute(_CREATE_BILLING_TRANSACTIONS_UNIT_INDEX)
        conn.execute(_CREATE_BILLING_TRANSACTIONS_STATUS_INDEX)
        conn.execute(_CREATE_BILLING_TRANSACTIONS_TYPE_INDEX)
        conn.execute(_CREATE_BILLING_TRANSACTIONS_DUE_DATE_INDEX)
        row = conn.execute("SELECT COUNT(*) FROM billing_transactions").fetchone()
        if row and row[0] == 0:
            for tx in DEFAULT_SEEDED_BILLING_TRANSACTIONS:
                conn.execute(
                    "INSERT INTO billing_transactions "
                    "(id, tenant_id, unit_id, session_id, transaction_type, "
                    "amount, status, due_date, paid_at, payment_method, "
                    "reference_number, description, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tx["id"],
                        tx["tenant_id"],
                        tx["unit_id"],
                        tx["session_id"],
                        tx["transaction_type"],
                        tx["amount"],
                        tx["status"],
                        tx["due_date"],
                        tx["paid_at"],
                        tx["payment_method"],
                        tx["reference_number"],
                        tx["description"],
                        tx["notes"],
                    ),
                )
        conn.commit()


def create_billing_transaction(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    transaction_id: str,
    tenant_id: str,
    unit_id: str,
    description: str,
    amount: float,
    transaction_type: str = "rent",
    status: str = "posted",
    due_date: str = "",
    paid_at: str | None = None,
    payment_method: str = "",
    reference_number: str = "",
    session_id: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    norm_id = normalize_transaction_id(transaction_id)
    norm_tenant = normalize_tenant_id(tenant_id)
    norm_unit = normalize_unit_id(unit_id)
    norm_type = normalize_transaction_type(transaction_type)
    norm_status = normalize_transaction_status(status)
    norm_method = normalize_payment_method(payment_method)

    clean_amount = float(amount)
    if clean_amount <= 0:
        raise ValueError("Transaction amount must be greater than zero.")

    clean_desc = (description or "").strip()
    if not clean_desc:
        raise ValueError("Transaction description must not be blank.")
    if len(clean_desc) > MAX_TRANSACTION_DESC_LENGTH:
        raise ValueError(
            f"Transaction description must be at most {MAX_TRANSACTION_DESC_LENGTH} characters."
        )

    clean_ref = (reference_number or "").strip()
    if len(clean_ref) > MAX_TRANSACTION_REF_LENGTH:
        raise ValueError(
            f"Reference number must be at most {MAX_TRANSACTION_REF_LENGTH} characters."
        )

    clean_notes = (notes or "").strip()
    if len(clean_notes) > MAX_TRANSACTION_NOTES_LENGTH:
        raise ValueError(
            f"Transaction notes must be at most {MAX_TRANSACTION_NOTES_LENGTH} characters."
        )

    clean_due = (due_date or "").strip()
    clean_session = (session_id or "").strip() or None
    clean_paid = (paid_at or "").strip() or None
    if norm_status == "paid" and clean_paid is None:
        clean_paid = datetime.now(UTC).isoformat()

    with closing(get_db_connection()) as conn:
        tenant_row = conn.execute(
            "SELECT id, balance_due FROM tenants WHERE id = ?", (norm_tenant,)
        ).fetchone()
        if not tenant_row:
            raise ValueError(f"Tenant with ID '{norm_tenant}' does not exist.")

        unit_row = conn.execute(
            "SELECT id FROM units WHERE id = ?", (norm_unit,)
        ).fetchone()
        if not unit_row:
            raise ValueError(f"Unit with ID '{norm_unit}' does not exist.")

        existing = conn.execute(
            "SELECT id FROM billing_transactions WHERE id = ?", (norm_id,)
        ).fetchone()
        if existing:
            raise ValueError(
                f"Billing transaction with ID '{norm_id}' already exists."
            )

        conn.execute(
            "INSERT INTO billing_transactions "
            "(id, tenant_id, unit_id, session_id, transaction_type, "
            "amount, status, due_date, paid_at, payment_method, "
            "reference_number, description, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                norm_id,
                norm_tenant,
                norm_unit,
                clean_session,
                norm_type,
                clean_amount,
                norm_status,
                clean_due,
                clean_paid,
                norm_method,
                clean_ref,
                clean_desc,
                clean_notes,
            ),
        )

        # If a new charge is created and is unpaid, update tenant balance_due
        if norm_type not in ("payment", "credit_refund") and norm_status in ("posted", "overdue"):
            new_bal = round(float(tenant_row["balance_due"]) + clean_amount, 2)
            conn.execute(
                "UPDATE tenants SET balance_due = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_bal, norm_tenant),
            )

        conn.commit()

    res = get_billing_transaction(norm_id)
    if res is None:
        raise RuntimeError("Failed to retrieve created billing transaction.")
    return res


def get_billing_transaction(tx_id: str) -> dict[str, Any] | None:
    cleaned_id = (tx_id or "").strip()
    if not cleaned_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM billing_transactions WHERE id = ?", (cleaned_id,)
        ).fetchone()
        return dict(row) if row else None


def list_billing_transactions(  # noqa: PLR0912, PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    query_parts = ["SELECT * FROM billing_transactions"]
    count_parts = ["SELECT COUNT(*) FROM billing_transactions"]
    where_clauses: list[str] = []
    params: list[Any] = []

    if tenant_id and tenant_id.strip():
        where_clauses.append("tenant_id = ?")
        params.append(tenant_id.strip())

    if unit_id and unit_id.strip():
        where_clauses.append("unit_id = ?")
        params.append(unit_id.strip())

    if transaction_type and transaction_type.strip():
        where_clauses.append("transaction_type = ?")
        params.append(transaction_type.strip().lower())

    if status and status.strip():
        where_clauses.append("status = ?")
        params.append(status.strip().lower())

    if start_date and start_date.strip():
        where_clauses.append("due_date >= ?")
        params.append(start_date.strip())

    if end_date and end_date.strip():
        where_clauses.append("due_date <= ?")
        params.append(end_date.strip())

    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        where_clauses.append(
            "(LOWER(description) LIKE ? OR LOWER(reference_number) LIKE ? OR LOWER(notes) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    if where_clauses:
        clause_str = " WHERE " + " AND ".join(where_clauses)
        query_parts.append(clause_str)
        count_parts.append(clause_str)

    order_clause = " ORDER BY due_date DESC, created_at DESC LIMIT ? OFFSET ?"
    query_parts.append(order_clause)

    with closing(get_db_connection()) as conn:
        count_cursor = conn.execute(" ".join(count_parts), tuple(params))
        total = int(count_cursor.fetchone()[0])
        list_params = list(params) + [max(1, limit), max(0, offset)]
        rows = conn.execute(" ".join(query_parts), tuple(list_params)).fetchall()
        return [dict(r) for r in rows], total


def update_billing_transaction(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    transaction_id: str,
    status: str | None = None,
    description: str | None = None,
    due_date: str | None = None,
    paid_at: str | None = None,
    payment_method: str | None = None,
    reference_number: str | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    current = get_billing_transaction(transaction_id)
    if not current:
        return None

    new_status = (
        normalize_transaction_status(status) if status is not None else current["status"]
    )
    new_desc = (
        description.strip() if description is not None else current["description"]
    )
    if not new_desc:
        raise ValueError("Transaction description must not be blank.")
    if len(new_desc) > MAX_TRANSACTION_DESC_LENGTH:
        raise ValueError(
            f"Transaction description must be at most {MAX_TRANSACTION_DESC_LENGTH} characters."
        )

    new_method = (
        normalize_payment_method(payment_method)
        if payment_method is not None
        else current["payment_method"]
    )

    new_ref = (
        reference_number.strip() if reference_number is not None else current["reference_number"]
    )
    if len(new_ref) > MAX_TRANSACTION_REF_LENGTH:
        raise ValueError(
            f"Reference number must be at most {MAX_TRANSACTION_REF_LENGTH} characters."
        )

    new_notes = notes.strip() if notes is not None else current["notes"]
    if len(new_notes) > MAX_TRANSACTION_NOTES_LENGTH:
        raise ValueError(
            f"Transaction notes must be at most {MAX_TRANSACTION_NOTES_LENGTH} characters."
        )

    new_due = due_date.strip() if due_date is not None else current["due_date"]
    new_paid = paid_at.strip() if paid_at is not None else current["paid_at"]
    if new_status == "paid" and not new_paid:
        new_paid = datetime.now(UTC).isoformat()

    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE billing_transactions SET status = ?, description = ?, "
            "due_date = ?, paid_at = ?, payment_method = ?, reference_number = ?, "
            "notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                new_status,
                new_desc,
                new_due,
                new_paid,
                new_method,
                new_ref,
                new_notes,
                current["id"],
            ),
        )

        # Rebalance tenant if an overdue or posted charge is marked paid or waived
        prev_status = current["status"]
        if (
            current["transaction_type"] not in ("payment", "credit_refund")
            and prev_status in ("posted", "overdue")
            and new_status in ("paid", "waived")
        ):
            tenant_row = conn.execute(
                "SELECT balance_due FROM tenants WHERE id = ?", (current["tenant_id"],)
            ).fetchone()
            if tenant_row:
                updated_bal = max(0.0, round(float(tenant_row[0]) - float(current["amount"]), 2))
                conn.execute(
                    "UPDATE tenants SET balance_due = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (updated_bal, current["tenant_id"]),
                )

        conn.commit()

    return get_billing_transaction(current["id"])


def delete_billing_transaction(transaction_id: str) -> bool:
    cleaned = (transaction_id or "").strip()
    if not cleaned:
        return False
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(
            "DELETE FROM billing_transactions WHERE id = ?", (cleaned,)
        )
        conn.commit()
        return bool(cursor.rowcount > 0)


def record_tenant_payment(  # noqa: PLR0912, PLR0913, PLR0915, PLR0917
    tenant_id: str,
    amount: float,
    payment_method: str = "online_portal",
    reference_number: str = "",
    description: str = "Resident Rent Payment",
    session_id: str | None = None,
    notes: str = "",
    transaction_id: str | None = None,
) -> dict[str, Any]:
    norm_tenant = normalize_tenant_id(tenant_id)
    norm_method = normalize_payment_method(payment_method)
    clean_amount = float(amount)
    if clean_amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    tx_id = normalize_transaction_id(transaction_id or f"tx_{uuid.uuid4().hex[:10]}")
    clean_desc = (description or "Resident Rent Payment").strip()
    if len(clean_desc) > MAX_TRANSACTION_DESC_LENGTH:
        raise ValueError(
            f"Transaction description must be at most {MAX_TRANSACTION_DESC_LENGTH} characters."
        )
    clean_ref = (reference_number or "").strip()
    if len(clean_ref) > MAX_TRANSACTION_REF_LENGTH:
        raise ValueError(
            f"Reference number must be at most {MAX_TRANSACTION_REF_LENGTH} characters."
        )
    clean_notes = (notes or "").strip()
    if len(clean_notes) > MAX_TRANSACTION_NOTES_LENGTH:
        raise ValueError(
            f"Transaction notes must be at most {MAX_TRANSACTION_NOTES_LENGTH} characters."
        )
    clean_session = (session_id or "").strip() or None
    paid_now = datetime.now(UTC).isoformat()
    today_date = datetime.now(UTC).strftime("%Y-%m-%d")

    with closing(get_db_connection()) as conn:
        tenant_row = conn.execute(
            "SELECT id, unit_id, balance_due, status FROM tenants WHERE id = ?",
            (norm_tenant,),
        ).fetchone()
        if not tenant_row:
            raise ValueError(f"Tenant with ID '{norm_tenant}' does not exist.")

        unit_id = tenant_row["unit_id"]
        prev_balance = float(tenant_row["balance_due"])
        new_balance = max(0.0, round(prev_balance - clean_amount, 2))

        new_tenant_status = tenant_row["status"]
        if new_balance <= 0.0 and tenant_row["status"] == "past_due":
            new_tenant_status = "active"

        # Record payment transaction
        conn.execute(
            "INSERT INTO billing_transactions "
            "(id, tenant_id, unit_id, session_id, transaction_type, "
            "amount, status, due_date, paid_at, payment_method, "
            "reference_number, description, notes) "
            "VALUES (?, ?, ?, ?, 'payment', ?, 'paid', ?, ?, ?, ?, ?, ?)",
            (
                tx_id,
                norm_tenant,
                unit_id,
                clean_session,
                clean_amount,
                today_date,
                paid_now,
                norm_method,
                clean_ref,
                clean_desc,
                clean_notes,
            ),
        )

        # Update tenant balance and status
        conn.execute(
            "UPDATE tenants SET balance_due = ?, status = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_balance, new_tenant_status, norm_tenant),
        )

        # Reconcile overdue charges
        if new_balance == 0.0:
            conn.execute(
                "UPDATE billing_transactions SET status = 'paid', paid_at = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND status = 'overdue'",
                (paid_now, norm_tenant),
            )
        else:
            rem_pay = clean_amount
            overdue_charges = conn.execute(
                "SELECT id, amount FROM billing_transactions "
                "WHERE tenant_id = ? AND status = 'overdue' "
                "ORDER BY due_date ASC",
                (norm_tenant,),
            ).fetchall()

            for ch in overdue_charges:
                ch_id, ch_amt = ch[0], float(ch[1])
                if rem_pay >= ch_amt:
                    conn.execute(
                        "UPDATE billing_transactions SET status = 'paid', paid_at = ?, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (paid_now, ch_id),
                    )
                    rem_pay -= ch_amt

        conn.commit()

    created_tx = get_billing_transaction(tx_id)
    if not created_tx:
        raise RuntimeError("Failed to retrieve recorded payment transaction.")

    return {
        "transaction": created_tx,
        "previous_balance": prev_balance,
        "new_balance": new_balance,
        "amount_paid": clean_amount,
        "tenant_status": new_tenant_status,
    }


def get_tenant_ledger_summary(tenant_id: str) -> dict[str, Any] | None:
    norm_tenant = (tenant_id or "").strip()
    if not norm_tenant:
        return None

    with closing(get_db_connection()) as conn:
        tenant_row = conn.execute(
            "SELECT id, unit_id, monthly_rent, balance_due, status FROM tenants WHERE id = ?",
            (norm_tenant,),
        ).fetchone()
        if not tenant_row:
            return None

        # Charges sum
        charges_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) FROM billing_transactions "
            "WHERE tenant_id = ? AND transaction_type NOT IN ('payment', 'credit_refund') "
            "AND status != 'waived'",
            (norm_tenant,),
        ).fetchone()
        total_charges = float(charges_row[0]) if charges_row else 0.0

        # Payments sum
        payments_query = (
            "SELECT COALESCE(SUM(amount), 0.0) FROM billing_transactions "
            "WHERE tenant_id = ? AND transaction_type = 'payment' AND status = 'paid'"
        )
        payments_row = conn.execute(payments_query, (norm_tenant,)).fetchone()
        total_payments = float(payments_row[0]) if payments_row else 0.0

        # Overdue charges sum & count
        overdue_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0), COUNT(*) FROM billing_transactions "
            "WHERE tenant_id = ? AND status = 'overdue'",
            (norm_tenant,),
        ).fetchone()
        overdue_amount = float(overdue_row[0]) if overdue_row else 0.0
        overdue_count = int(overdue_row[1]) if overdue_row else 0

        # Last payment
        last_pay_query = (
            "SELECT * FROM billing_transactions "
            "WHERE tenant_id = ? AND "
            "(transaction_type = 'payment' OR "
            "(paid_at IS NOT NULL AND status = 'paid' AND payment_method != '')) "
            "ORDER BY paid_at DESC, created_at DESC LIMIT 1"
        )
        last_pay_row = conn.execute(last_pay_query, (norm_tenant,)).fetchone()
        last_payment = dict(last_pay_row) if last_pay_row else None

        # Recent transactions
        recent_rows = conn.execute(
            "SELECT * FROM billing_transactions WHERE tenant_id = ? "
            "ORDER BY due_date DESC, created_at DESC LIMIT 5",
            (norm_tenant,),
        ).fetchall()
        recent_transactions = [dict(r) for r in recent_rows]

        return {
            "tenant_id": tenant_row["id"],
            "unit_id": tenant_row["unit_id"],
            "current_balance": float(tenant_row["balance_due"]),
            "monthly_rent": float(tenant_row["monthly_rent"]),
            "total_charges": total_charges,
            "total_payments": total_payments,
            "overdue_amount": overdue_amount,
            "overdue_count": overdue_count,
            "tenant_status": tenant_row["status"],
            "last_payment": last_payment,
            "recent_transactions": recent_transactions,
        }


def get_billing_summary_metrics() -> dict[str, Any]:
    with closing(get_db_connection()) as conn:
        total_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0.0) FROM billing_transactions"
        ).fetchone()
        total_count = int(total_row[0]) if total_row else 0

        charges_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) FROM billing_transactions "
            "WHERE transaction_type NOT IN ('payment', 'credit_refund') AND status != 'waived'"
        ).fetchone()
        total_billed = float(charges_row[0]) if charges_row else 0.0

        collected_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) FROM billing_transactions "
            "WHERE transaction_type = 'payment' AND status = 'paid'"
        ).fetchone()
        total_collected = float(collected_row[0]) if collected_row else 0.0

        outstanding_row = conn.execute(
            "SELECT COALESCE(SUM(balance_due), 0.0) FROM tenants"
        ).fetchone()
        total_outstanding = float(outstanding_row[0]) if outstanding_row else 0.0

        overdue_tx_row = conn.execute(
            "SELECT COUNT(*) FROM billing_transactions WHERE status = 'overdue'"
        ).fetchone()
        overdue_tx_count = int(overdue_tx_row[0]) if overdue_tx_row else 0

        overdue_tenants_row = conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE balance_due > 0 OR status = 'past_due'"
        ).fetchone()
        overdue_tenants_count = int(overdue_tenants_row[0]) if overdue_tenants_row else 0

        rate = (
            round((total_collected / total_billed) * 100.0, 2)
            if total_billed > 0
            else 100.0
        )

        by_type_rows = conn.execute(
            "SELECT transaction_type, COUNT(*) FROM billing_transactions GROUP BY transaction_type"
        ).fetchall()
        by_type = {r[0]: int(r[1]) for r in by_type_rows}

        by_status_rows = conn.execute(
            "SELECT status, COUNT(*) FROM billing_transactions GROUP BY status"
        ).fetchall()
        by_status = {r[0]: int(r[1]) for r in by_status_rows}

        by_method_rows = conn.execute(
            "SELECT payment_method, COUNT(*) FROM billing_transactions "
            "WHERE payment_method != '' GROUP BY payment_method"
        ).fetchall()
        by_payment_method = {r[0]: int(r[1]) for r in by_method_rows}

        return {
            "total_transactions": total_count,
            "total_billed": total_billed,
            "total_collected": total_collected,
            "collection_rate": rate,
            "total_outstanding": total_outstanding,
            "overdue_transactions_count": overdue_tx_count,
            "overdue_tenants_count": overdue_tenants_count,
            "by_type": by_type,
            "by_status": by_status,
            "by_payment_method": by_payment_method,
        }


DEFAULT_SEEDED_LEASE_RENEWALS = [
    {
        "id": "lr_101",
        "tenant_id": "tenant_1",
        "unit_id": "unit_101",
        "session_id": None,
        "current_rent": 1450.0,
        "proposed_rent": 1500.0,
        "term_months": 12,
        "start_date": "2026-11-01",
        "end_date": "2027-10-31",
        "concession_amount": 100.0,
        "concession_notes": "First month renewal credit of $100 applied upon signing.",
        "security_deposit_change": 0.0,
        "status": "offered",
        "expires_at": "2026-10-31",
        "signature_name": "",
        "signature_ip": "",
        "signed_at": None,
        "notes": "12-month standard renewal offer with early sign incentive.",
        "document_file_id": None,
    },
    {
        "id": "lr_102",
        "tenant_id": "tenant_2",
        "unit_id": "unit_204",
        "session_id": None,
        "current_rent": 1850.0,
        "proposed_rent": 1925.0,
        "term_months": 12,
        "start_date": "2027-01-01",
        "end_date": "2027-12-31",
        "concession_amount": 0.0,
        "concession_notes": "",
        "security_deposit_change": 0.0,
        "status": "draft",
        "expires_at": "2026-11-30",
        "signature_name": "",
        "signature_ip": "",
        "signed_at": None,
        "notes": "Draft renewal under review pending payment of overdue balance.",
        "document_file_id": None,
    },
    {
        "id": "lr_103",
        "tenant_id": "tenant_3",
        "unit_id": "unit_PH1",
        "session_id": None,
        "current_rent": 3200.0,
        "proposed_rent": 3350.0,
        "term_months": 24,
        "start_date": "2026-10-01",
        "end_date": "2028-09-30",
        "concession_amount": 250.0,
        "concession_notes": "Penthouse multi-year renewal concession.",
        "security_deposit_change": 150.0,
        "status": "signed",
        "expires_at": "2026-09-25",
        "signature_name": "Eleanor Vance",
        "signature_ip": "192.168.1.105",
        "signed_at": "2026-09-24T14:30:00Z",
        "notes": "24-month executive renewal executed successfully.",
        "document_file_id": None,
    },
]


def normalize_lease_renewal_id(lr_id: str) -> str:
    cleaned = (lr_id or "").strip()
    if not cleaned:
        raise ValueError("Lease renewal ID must not be blank.")
    if len(cleaned) > MAX_LEASE_RENEWAL_ID_LENGTH:
        raise ValueError(
            f"Lease renewal ID must be at most {MAX_LEASE_RENEWAL_ID_LENGTH} characters."
        )
    return cleaned


def normalize_lease_renewal_status(val: str) -> str:
    cleaned = (val or "").strip().lower()
    if not cleaned:
        return DEFAULT_LEASE_RENEWAL_STATUS
    if cleaned not in VALID_LEASE_RENEWAL_STATUSES:
        valid_statuses = ", ".join(sorted(VALID_LEASE_RENEWAL_STATUSES))
        raise ValueError(
            f"Invalid lease renewal status '{cleaned}'. Expected one of: {valid_statuses}."
        )
    return cleaned


def normalize_renewal_term_months(val: int | None) -> int:
    if val is None:
        return DEFAULT_RENEWAL_TERM_MONTHS
    try:
        ival = int(val)
    except (ValueError, TypeError) as exc:
        raise ValueError("Renewal term months must be an integer.") from exc
    if ival not in VALID_RENEWAL_TERM_MONTHS:
        valid_terms = ", ".join(str(m) for m in sorted(VALID_RENEWAL_TERM_MONTHS))
        raise ValueError(
            f"Invalid renewal term months '{ival}'. Expected one of: {valid_terms}."
        )
    return ival


def create_lease_renewals() -> None:
    """Create lease_renewals table, indexes, and pre-seed initial records if empty."""
    with closing(get_db_connection()) as conn:
        conn.execute(_CREATE_LEASE_RENEWALS_TABLE)
        conn.execute(_CREATE_LEASE_RENEWALS_TENANT_INDEX)
        conn.execute(_CREATE_LEASE_RENEWALS_UNIT_INDEX)
        conn.execute(_CREATE_LEASE_RENEWALS_STATUS_INDEX)
        conn.execute(_CREATE_LEASE_RENEWALS_EXPIRES_INDEX)
        row = conn.execute("SELECT COUNT(*) FROM lease_renewals").fetchone()
        if row and row[0] == 0:
            for lr in DEFAULT_SEEDED_LEASE_RENEWALS:
                conn.execute(
                    "INSERT INTO lease_renewals "
                    "(id, tenant_id, unit_id, session_id, current_rent, "
                    "proposed_rent, term_months, start_date, end_date, "
                    "concession_amount, concession_notes, security_deposit_change, "
                    "status, expires_at, signature_name, signature_ip, "
                    "signed_at, notes, document_file_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        lr["id"],
                        lr["tenant_id"],
                        lr["unit_id"],
                        lr["session_id"],
                        lr["current_rent"],
                        lr["proposed_rent"],
                        lr["term_months"],
                        lr["start_date"],
                        lr["end_date"],
                        lr["concession_amount"],
                        lr["concession_notes"],
                        lr["security_deposit_change"],
                        lr["status"],
                        lr["expires_at"],
                        lr["signature_name"],
                        lr["signature_ip"],
                        lr["signed_at"],
                        lr["notes"],
                        lr["document_file_id"],
                    ),
                )
        conn.commit()


def create_lease_renewal(  # noqa: PLR0913, PLR0915, PLR0917
    tenant_id: str,
    unit_id: str | None = None,
    proposed_rent: float | None = None,
    current_rent: float | None = None,
    term_months: int = 12,
    start_date: str | None = None,
    end_date: str | None = None,
    concession_amount: float = 0.0,
    concession_notes: str = "",
    security_deposit_change: float = 0.0,
    status: str = "offered",
    expires_at: str | None = None,
    session_id: str | None = None,
    notes: str = "",
    lr_id: str | None = None,
) -> dict[str, Any]:
    """Create a new lease renewal offer with validation and auto-resolved tenant/unit details."""
    norm_tenant = (tenant_id or "").strip()
    if not norm_tenant:
        raise ValueError("Tenant ID must not be blank.")

    tenant_record = get_tenant(norm_tenant)
    if not tenant_record:
        raise ValueError(f"Tenant with ID '{norm_tenant}' does not exist.")

    resolved_unit = (unit_id or tenant_record.get("unit_id") or "").strip()
    if not resolved_unit:
        raise ValueError("Unit ID is required or must be linked to the tenant.")
    unit_record = get_unit(resolved_unit)
    if not unit_record:
        raise ValueError(f"Unit with ID '{resolved_unit}' does not exist.")

    resolved_current_rent = (
        float(current_rent)
        if current_rent is not None
        else float(tenant_record.get("monthly_rent", 0.0))
    )
    if resolved_current_rent < 0.0:
        raise ValueError("Current rent cannot be negative.")

    resolved_proposed_rent = (
        float(proposed_rent)
        if proposed_rent is not None
        else resolved_current_rent
    )
    if resolved_proposed_rent <= 0.0:
        raise ValueError("Proposed rent must be greater than zero.")

    norm_term = normalize_renewal_term_months(term_months)
    norm_status = normalize_lease_renewal_status(status)

    resolved_start = (start_date or tenant_record.get("lease_end") or "").strip()
    if not resolved_start:
        resolved_start = datetime.now(UTC).strftime("%Y-%m-%d")

    resolved_end = (end_date or "").strip()
    if not resolved_end:
        try:
            start_dt = datetime.strptime(resolved_start, "%Y-%m-%d")
            total_months = start_dt.month + norm_term
            new_year = start_dt.year + (total_months - 1) // 12
            new_month = ((total_months - 1) % 12) + 1
            new_day = min(start_dt.day, 28)
            resolved_end = f"{new_year:04d}-{new_month:02d}-{new_day:02d}"
        except Exception:
            resolved_end = resolved_start

    resolved_expires = (expires_at or "").strip()
    if not resolved_expires:
        resolved_expires = resolved_start

    clean_concession_amount = max(0.0, float(concession_amount or 0.0))
    clean_concession_notes = (concession_notes or "").strip()[:MAX_CONCESSION_NOTES_LENGTH]
    clean_deposit_change = float(security_deposit_change or 0.0)
    clean_notes = (notes or "").strip()[:MAX_LEASE_RENEWAL_NOTES_LENGTH]
    clean_session = (session_id or "").strip() or None

    renewal_id = normalize_lease_renewal_id(
        lr_id or f"lr_{uuid.uuid4().hex[:8]}"
    )

    with closing(get_db_connection()) as conn:
        existing = conn.execute(
            "SELECT id FROM lease_renewals WHERE id = ?", (renewal_id,)
        ).fetchone()
        if existing:
            raise ValueError(
                f"Lease renewal with ID '{renewal_id}' already exists."
            )

        conn.execute(
            "INSERT INTO lease_renewals "
            "(id, tenant_id, unit_id, session_id, current_rent, "
            "proposed_rent, term_months, start_date, end_date, "
            "concession_amount, concession_notes, security_deposit_change, "
            "status, expires_at, signature_name, signature_ip, "
            "signed_at, notes, document_file_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', NULL, ?, NULL)",
            (
                renewal_id,
                norm_tenant,
                resolved_unit,
                clean_session,
                resolved_current_rent,
                resolved_proposed_rent,
                norm_term,
                resolved_start,
                resolved_end,
                clean_concession_amount,
                clean_concession_notes,
                clean_deposit_change,
                norm_status,
                resolved_expires,
                clean_notes,
            ),
        )
        conn.commit()

    res = get_lease_renewal(renewal_id)
    if res is None:
        raise RuntimeError("Failed to retrieve created lease renewal.")
    return res


def get_lease_renewal(renewal_id: str) -> dict[str, Any] | None:
    cleaned_id = (renewal_id or "").strip()
    if not cleaned_id:
        return None
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM lease_renewals WHERE id = ?", (cleaned_id,)
        ).fetchone()
        return dict(row) if row else None


def list_lease_renewals(  # noqa: PLR0912, PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    query_parts = ["SELECT * FROM lease_renewals"]
    count_parts = ["SELECT COUNT(*) FROM lease_renewals"]
    where_clauses: list[str] = []
    params: list[Any] = []

    if tenant_id and tenant_id.strip():
        where_clauses.append("tenant_id = ?")
        params.append(tenant_id.strip())

    if unit_id and unit_id.strip():
        where_clauses.append("unit_id = ?")
        params.append(unit_id.strip())

    if status and status.strip():
        where_clauses.append("status = ?")
        params.append(status.strip().lower())

    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        where_clauses.append(
            "(LOWER(id) LIKE ? OR LOWER(notes) LIKE ? OR LOWER(signature_name) LIKE ?)"
        )
        params.extend([s, s, s])

    if where_clauses:
        clause_str = " WHERE " + " AND ".join(where_clauses)
        query_parts.append(clause_str)
        count_parts.append(clause_str)

    query_parts.append(" ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?")
    params_for_query = list(params) + [max(1, limit), max(0, offset)]

    full_query = "".join(query_parts)
    full_count_query = "".join(count_parts)

    with closing(get_db_connection()) as conn:
        total = conn.execute(full_count_query, params).fetchone()[0]
        rows = conn.execute(full_query, params_for_query).fetchall()
        return [dict(r) for r in rows], int(total)


def get_tenant_lease_renewals(tenant_id: str) -> list[dict[str, Any]]:
    """Retrieve all lease renewal records for a tenant ordered by created_at DESC."""
    cleaned_id = (tenant_id or "").strip()
    if not cleaned_id:
        return []
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM lease_renewals WHERE tenant_id = ? ORDER BY created_at DESC",
            (cleaned_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_lease_renewal(  # noqa: PLR0912, PLR0913, PLR0917
    renewal_id: str,
    proposed_rent: float | None = None,
    term_months: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    concession_amount: float | None = None,
    concession_notes: str | None = None,
    security_deposit_change: float | None = None,
    status: str | None = None,
    expires_at: str | None = None,
    notes: str | None = None,
    document_file_id: int | None = None,
) -> dict[str, Any] | None:
    current = get_lease_renewal(renewal_id)
    if not current:
        return None

    updates: list[str] = []
    params: list[Any] = []

    if proposed_rent is not None:
        p_val = float(proposed_rent)
        if p_val <= 0.0:
            raise ValueError("Proposed rent must be greater than zero.")
        updates.append("proposed_rent = ?")
        params.append(p_val)

    if term_months is not None:
        t_val = normalize_renewal_term_months(term_months)
        updates.append("term_months = ?")
        params.append(t_val)

    if start_date is not None:
        updates.append("start_date = ?")
        params.append(start_date.strip())

    if end_date is not None:
        updates.append("end_date = ?")
        params.append(end_date.strip())

    if concession_amount is not None:
        updates.append("concession_amount = ?")
        params.append(max(0.0, float(concession_amount)))

    if concession_notes is not None:
        updates.append("concession_notes = ?")
        params.append(concession_notes.strip()[:MAX_CONCESSION_NOTES_LENGTH])

    if security_deposit_change is not None:
        updates.append("security_deposit_change = ?")
        params.append(float(security_deposit_change))

    if status is not None:
        s_val = normalize_lease_renewal_status(status)
        updates.append("status = ?")
        params.append(s_val)

    if expires_at is not None:
        updates.append("expires_at = ?")
        params.append(expires_at.strip())

    if notes is not None:
        updates.append("notes = ?")
        params.append(notes.strip()[:MAX_LEASE_RENEWAL_NOTES_LENGTH])

    if document_file_id is not None:
        updates.append("document_file_id = ?")
        params.append(int(document_file_id))

    if not updates:
        return current

    updates.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"UPDATE lease_renewals SET {', '.join(updates)} WHERE id = ?"
    params.append(renewal_id)

    with closing(get_db_connection()) as conn:
        conn.execute(sql, params)
        conn.commit()

    return get_lease_renewal(renewal_id)


def delete_lease_renewal(renewal_id: str) -> bool:
    cleaned_id = (renewal_id or "").strip()
    if not cleaned_id:
        return False
    with closing(get_db_connection()) as conn:
        cursor = conn.execute(
            "DELETE FROM lease_renewals WHERE id = ?", (cleaned_id,)
        )
        conn.commit()
        return bool(cursor.rowcount > 0)


def sign_lease_renewal(  # noqa: PLR0913, PLR0917
    renewal_id: str,
    signature_name: str,
    signature_ip: str = "127.0.0.1",
    signed_at: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Digitally sign a renewal offer and atomically update tenant lease dates and rent."""
    current = get_lease_renewal(renewal_id)
    if not current:
        raise ValueError(f"Lease renewal with ID '{renewal_id}' does not exist.")

    if current["status"] == "signed":
        raise ValueError("Lease renewal has already been signed.")

    sig_name = (signature_name or "").strip()
    if not sig_name:
        raise ValueError("Signature name must not be blank.")
    if len(sig_name) > MAX_SIGNATURE_NAME_LENGTH:
        raise ValueError(
            f"Signature name must be at most {MAX_SIGNATURE_NAME_LENGTH} characters."
        )

    sig_ip = (signature_ip or "127.0.0.1").strip()[:MAX_SIGNATURE_IP_LENGTH]
    timestamp = signed_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    combined_notes = current["notes"] or ""
    if notes and notes.strip():
        combined_notes = f"{combined_notes} | {notes.strip()}".strip(" |")

    tenant_id = current["tenant_id"]
    new_start = current["start_date"]
    new_end = current["end_date"]
    new_rent = current["proposed_rent"]

    with closing(get_db_connection()) as conn:
        conn.execute(
            "UPDATE lease_renewals SET "
            "status = 'signed', "
            "signature_name = ?, "
            "signature_ip = ?, "
            "signed_at = ?, "
            "notes = ?, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (sig_name, sig_ip, timestamp, combined_notes, renewal_id),
        )

        # Atomically update tenant lease parameters
        if new_start and new_end and new_rent > 0:
            conn.execute(
                "UPDATE tenants SET "
                "lease_start = ?, "
                "lease_end = ?, "
                "monthly_rent = ?, "
                "status = 'active', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (new_start, new_end, new_rent, tenant_id),
            )

        conn.commit()

    updated = get_lease_renewal(renewal_id)
    if not updated:
        raise RuntimeError("Failed to retrieve signed lease renewal.")
    return updated


def get_lease_renewal_summary_metrics() -> dict[str, Any]:
    """Compute aggregated portfolio lease renewal statistics."""
    with closing(get_db_connection()) as conn:
        total_row = conn.execute("SELECT COUNT(*) FROM lease_renewals").fetchone()
        total_count = int(total_row[0]) if total_row else 0

        signed_row = conn.execute(
            "SELECT COUNT(*) FROM lease_renewals WHERE status = 'signed'"
        ).fetchone()
        signed_count = int(signed_row[0]) if signed_row else 0

        offered_row = conn.execute(
            "SELECT COUNT(*) FROM lease_renewals "
            "WHERE status IN ('offered', 'negotiating', 'accepted')"
        ).fetchone()
        offered_count = int(offered_row[0]) if offered_row else 0

        draft_row = conn.execute(
            "SELECT COUNT(*) FROM lease_renewals WHERE status = 'draft'"
        ).fetchone()
        draft_count = int(draft_row[0]) if draft_row else 0

        declined_row = conn.execute(
            "SELECT COUNT(*) FROM lease_renewals WHERE status IN ('declined', 'expired')"
        ).fetchone()
        declined_count = int(declined_row[0]) if declined_row else 0

        renewal_rate = (
            round((signed_count / total_count) * 100.0, 2)
            if total_count > 0
            else 0.0
        )

        diff_row = conn.execute(
            "SELECT AVG(((proposed_rent - current_rent) / current_rent) * 100.0) "
            "FROM lease_renewals WHERE current_rent > 0"
        ).fetchone()
        avg_rent_increase_pct = (
            round(float(diff_row[0]), 2)
            if diff_row and diff_row[0] is not None
            else 0.0
        )

        by_status_rows = conn.execute(
            "SELECT status, COUNT(*) FROM lease_renewals GROUP BY status"
        ).fetchall()
        by_status = {r[0]: int(r[1]) for r in by_status_rows}

        by_term_rows = conn.execute(
            "SELECT term_months, COUNT(*) FROM lease_renewals GROUP BY term_months"
        ).fetchall()
        by_term = {str(r[0]): int(r[1]) for r in by_term_rows}

        return {
            "total_renewals": total_count,
            "signed_renewals": signed_count,
            "pending_renewals": offered_count,
            "draft_renewals": draft_count,
            "declined_renewals": declined_count,
            "renewal_rate": renewal_rate,
            "avg_rent_increase_pct": avg_rent_increase_pct,
            "by_status": by_status,
            "by_term": by_term,
        }


# Initialize the database tables
create_application_logs()
create_document_store()
migrate_document_store()
create_units()
create_tenants()
create_work_orders()
create_billing_transactions()
create_lease_renewals()
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



