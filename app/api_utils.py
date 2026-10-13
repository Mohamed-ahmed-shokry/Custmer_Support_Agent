from typing import Any, cast

import requests
import streamlit as st
from api.settings import settings

API_BASE_URL = settings.api_base_url

HTTP_OK = 200
HTTP_CREATED = 201


def _request_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Headers shared by every API call; forwards the API key when configured."""
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    if settings.api_key:
        headers["X-API-Key"] = settings.api_key
    if extra:
        headers.update(extra)
    return headers


def _upload_headers() -> dict[str, str]:
    """Headers for multipart uploads; do NOT pin Content-Type.

    requests sets the multipart boundary itself; forcing "application/json"
    leaves the request with a JSON content type and no boundary, so the API
    cannot parse the multipart body and rejects it with HTTP 422.
    """
    headers = {"accept": "application/json"}
    if settings.api_key:
        headers["X-API-Key"] = settings.api_key
    return headers


def extract_error_detail(response):
    try:
        payload = response.json()
    except ValueError:
        return response.text

    if not isinstance(payload, dict):
        return response.text

    detail = payload.get("detail")
    if isinstance(detail, list):
        return "; ".join(
            item.get("msg", str(item)) if isinstance(item, dict) else str(item) for item in detail
        )
    if detail:
        return str(detail)
    return response.text


def show_api_error(action, response):
    st.error(f"{action}. Status {response.status_code}: {extract_error_detail(response)}")


def get_api_response(  # noqa: PLR0913, PLR0917 - explicit request options
    question,
    session_id,
    model,
    collections=None,
    expand_query=None,
    rerank=None,
    file_ids=None,
    use_hybrid=None,
    use_cross_encoder_rerank=None,
    cross_encoder_model=None,
):
    data = {"question": question, "model": model}
    if session_id:
        data["session_id"] = session_id
    if collections:
        data["collections"] = collections
    if file_ids:
        data["file_ids"] = file_ids
    if use_hybrid is not None:
        data["use_hybrid"] = use_hybrid
    if expand_query is not None:
        data["expand_query"] = expand_query
    if rerank is not None:
        data["rerank"] = rerank
    if use_cross_encoder_rerank is not None:
        data["use_cross_encoder_rerank"] = use_cross_encoder_rerank
    if cross_encoder_model is not None:
        data["cross_encoder_model"] = cross_encoder_model

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat", headers=_request_headers(), json=data, timeout=60
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("API request failed", response)
            return None
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None


def get_api_stream_response(  # noqa: PLR0913, PLR0917 - explicit request options
    question,
    session_id,
    model,
    collections=None,
    expand_query=None,
    rerank=None,
    file_ids=None,
    use_hybrid=None,
    use_cross_encoder_rerank=None,
    cross_encoder_model=None,
):
    """Get streaming response from the API."""
    data = {"question": question, "model": model}
    if session_id:
        data["session_id"] = session_id
    if collections:
        data["collections"] = collections
    if file_ids:
        data["file_ids"] = file_ids
    if use_hybrid is not None:
        data["use_hybrid"] = use_hybrid
    if expand_query is not None:
        data["expand_query"] = expand_query
    if rerank is not None:
        data["rerank"] = rerank
    if use_cross_encoder_rerank is not None:
        data["use_cross_encoder_rerank"] = use_cross_encoder_rerank
    if cross_encoder_model is not None:
        data["cross_encoder_model"] = cross_encoder_model

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat/stream",
            headers=_request_headers({"accept": "text/event-stream"}),
            json=data,
            timeout=120,
            stream=True,
        )
        if response.status_code == HTTP_OK:
            return response.iter_lines(decode_unicode=True)
        else:
            show_api_error("API stream request failed", response)
            return None
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None


def parse_sse_line(line):
    """Parse one Server-Sent Events line into (event_type, data).

    The API emits answer chunks as ``data: <text>`` and metadata frames as
    an ``event: <name>`` line immediately followed by a ``data: <json>``
    line. An ``event`` line yields (event_type, None) so callers can pair
    it with the next ``data`` line.
    """
    if not line:
        return None, None
    if line.startswith("event: "):
        return line[7:].strip(), None
    if line.startswith("data: "):
        return "message", line[6:]
    return None, None


def upload_documents(files, collection="default"):
    try:
        multipart = [("files", (file.name, file, file.type)) for file in files]
        response = requests.post(
            f"{API_BASE_URL}/upload-docs",
            params={"collection": collection},
            files=multipart,
            headers=_upload_headers(),
            timeout=300,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to upload files", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while uploading the files: {str(e)}")
        return None


def upload_document(file, collection="default"):
    try:
        files = {"file": (file.name, file, file.type)}
        response = requests.post(
            f"{API_BASE_URL}/upload-doc",
            params={"collection": collection},
            files=files,
            headers=_upload_headers(),
            timeout=120,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to upload file", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while uploading the file: {str(e)}")
        return None


def list_collections():
    try:
        response = requests.get(
            f"{API_BASE_URL}/collections", headers=_request_headers(), timeout=30
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch collection list", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while fetching the collection list: {str(e)}")
        return []


def get_collections_details():
    try:
        response = requests.get(
            f"{API_BASE_URL}/collections/details",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch collections details", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while fetching collections details: {str(e)}")
        return []


def rename_collection(collection, new_name):
    try:
        response = requests.patch(
            f"{API_BASE_URL}/collections/{collection}",
            json={"collection": new_name},
            headers=_request_headers(),
            timeout=60,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to rename collection", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while renaming the collection: {str(e)}")
        return None


def delete_collection(collection):
    try:
        response = requests.delete(
            f"{API_BASE_URL}/collections/{collection}", headers=_request_headers(), timeout=60
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to delete collection", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while deleting the collection: {str(e)}")
        return None


def list_documents(collection=None):
    try:
        params = {"collection": collection} if collection else None
        response = requests.get(
            f"{API_BASE_URL}/list-docs",
            params=params,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch document list", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while fetching the document list: {str(e)}")
        return []


def list_sessions(status=None, tag=None, agent=None, tier=None):
    try:
        params = {}
        if status:
            params["status"] = status
        if tag:
            params["tag"] = tag
        if agent:
            params["agent"] = agent
        if tier:
            params["tier"] = tier
        response = requests.get(
            f"{API_BASE_URL}/sessions",
            params=params or None,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch session list", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while fetching the session list: {str(e)}")
        return []


def search_sessions(query, limit=20):
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/search",
            params={"q": query, "limit": limit},
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json().get("results", [])
        else:
            show_api_error("Failed to search sessions", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while searching sessions: {str(e)}")
        return []


def delete_session(session_id):
    try:
        response = requests.delete(
            f"{API_BASE_URL}/sessions/{session_id}", headers=_request_headers(), timeout=30
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to delete session", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while deleting the session: {str(e)}")
        return None


def update_session(  # noqa: PLR0913, PLR0917
    session_id,
    label=None,
    status=None,
    priority=None,
    tags=None,
    summary=None,
    resolution_notes=None,
    assigned_agent=None,
    escalation_tier=None,
):
    payload = {}
    if label is not None:
        payload["label"] = label
    if status is not None:
        payload["status"] = status
    if priority is not None:
        payload["priority"] = priority
    if tags is not None:
        payload["tags"] = tags
    if summary is not None:
        payload["summary"] = summary
    if resolution_notes is not None:
        payload["resolution_notes"] = resolution_notes
    if assigned_agent is not None:
        payload["assigned_agent"] = assigned_agent
    if escalation_tier is not None:
        payload["escalation_tier"] = escalation_tier
    try:
        response = requests.patch(
            f"{API_BASE_URL}/sessions/{session_id}",
            json=payload,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to update session", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while updating the session: {str(e)}")
        return None


def rename_session(session_id, label):
    return update_session(session_id, label=label)


def summarize_session(session_id, model=None, save_summary=True):
    payload = {"save_summary": save_summary}
    if model:
        payload["model"] = model
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/summarize",
            json=payload,
            headers=_request_headers(),
            timeout=60,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to summarize session", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while summarizing the session: {str(e)}")
        return None


def export_session(session_id, format="markdown"):
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/export",
            params={"format": format},
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.text
        else:
            show_api_error("Failed to export session", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while exporting the session: {str(e)}")
        return None



def submit_feedback(session_id, rating, comment=None):
    payload = {"session_id": session_id, "rating": rating}
    if comment:
        payload["comment"] = comment
    try:
        response = requests.post(
            f"{API_BASE_URL}/feedback",
            json=payload,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to submit feedback", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while submitting feedback: {str(e)}")
        return None


def list_feedback(rating=None, session_id=None, limit=50, offset=0):
    params = {"limit": limit, "offset": offset}
    if rating is not None:
        params["rating"] = rating
    if session_id is not None:
        params["session_id"] = session_id
    try:
        response = requests.get(
            f"{API_BASE_URL}/feedback",
            params=params,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch feedback", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while fetching feedback: {str(e)}")
        return None


def get_session_feedback(session_id):
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/feedback",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch session feedback", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while fetching session feedback: {str(e)}")
        return None


def get_feedback_analytics(recent_comments_limit=5):
    try:
        response = requests.get(
            f"{API_BASE_URL}/feedback/analytics",
            params={"recent_comments_limit": recent_comments_limit},
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch feedback analytics", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while fetching feedback analytics: {str(e)}")
        return None


def submit_csat_feedback(  # noqa: PLR0913, PLR0917
    session_id,
    score,
    resolution_satisfaction=None,
    agent_helpfulness=None,
    response_speed=None,
    comment=None,
    assigned_agent=None,
    escalation_tier=None,
):
    payload: dict[str, Any] = {"session_id": session_id, "score": score}
    if resolution_satisfaction is not None:
        payload["resolution_satisfaction"] = resolution_satisfaction
    if agent_helpfulness is not None:
        payload["agent_helpfulness"] = agent_helpfulness
    if response_speed is not None:
        payload["response_speed"] = response_speed
    if comment:
        payload["comment"] = comment
    if assigned_agent:
        payload["assigned_agent"] = assigned_agent
    if escalation_tier:
        payload["escalation_tier"] = escalation_tier

    try:
        response = requests.post(
            f"{API_BASE_URL}/feedback/csat",
            json=payload,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_CREATED:
            return response.json()
        else:
            show_api_error("Failed to submit CSAT feedback", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while submitting CSAT feedback: {str(e)}")
        return None


def list_feedback_review_queue(  # noqa: PLR0913, PLR0917
    review_status=None,
    assigned_agent=None,
    escalation_tier=None,
    min_score=None,
    max_score=None,
    limit=50,
    offset=0,
):
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if review_status:
        params["review_status"] = review_status
    if assigned_agent:
        params["assigned_agent"] = assigned_agent
    if escalation_tier:
        params["escalation_tier"] = escalation_tier
    if min_score is not None:
        params["min_score"] = min_score
    if max_score is not None:
        params["max_score"] = max_score

    try:
        response = requests.get(
            f"{API_BASE_URL}/feedback/queue",
            params=params,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch feedback review queue", response)
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
    except Exception as e:
        st.error(f"An error occurred while fetching feedback review queue: {str(e)}")
        return {"items": [], "total": 0, "limit": limit, "offset": offset}


def update_feedback_review(feedback_id, review_status, reviewer_notes=None, reviewed_by=None):
    payload: dict[str, Any] = {"review_status": review_status}
    if reviewer_notes is not None:
        payload["reviewer_notes"] = reviewer_notes
    if reviewed_by is not None:
        payload["reviewed_by"] = reviewed_by

    try:
        response = requests.patch(
            f"{API_BASE_URL}/feedback/{feedback_id}/review",
            json=payload,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to update feedback review", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while updating feedback review: {str(e)}")
        return None


def get_csat_summary(limit=1000):
    try:
        response = requests.get(
            f"{API_BASE_URL}/feedback/csat-summary",
            params={"limit": limit},
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch CSAT summary", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while fetching CSAT summary: {str(e)}")
        return None


def get_agent_scorecards():
    try:
        response = requests.get(
            f"{API_BASE_URL}/feedback/agent-scorecards",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch agent performance scorecards", response)
            return {"scorecards": [], "total_agents": 0}
    except Exception as e:
        st.error(f"An error occurred while fetching agent performance scorecards: {str(e)}")
        return {"scorecards": [], "total_agents": 0}


def get_support_triage_analytics():
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/triage-analytics",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch support triage analytics", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while fetching support triage analytics: {str(e)}")
        return None



def get_session_history(session_id):
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/history",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch session history", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while fetching the session history: {str(e)}")
        return []


def delete_document(file_id):
    data = {"file_id": file_id}

    try:
        response = requests.post(
            f"{API_BASE_URL}/delete-doc",
            headers=_request_headers(),
            json=data,
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to delete document", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while deleting the document: {str(e)}")
        return None


def get_document_details(file_id):
    try:
        response = requests.get(
            f"{API_BASE_URL}/docs/{file_id}",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to fetch document details", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while fetching document details: {str(e)}")
        return None


def rechunk_document(
    file_id, chunking_strategy="recursive", chunk_size=1000, chunk_overlap=200
):
    try:
        response = requests.post(
            f"{API_BASE_URL}/docs/{file_id}/rechunk",
            headers=_request_headers(),
            json={
                "chunking_strategy": chunking_strategy,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
            timeout=60,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to re-chunk document", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while re-chunking document: {str(e)}")
        return None


def rechunk_collection(
    collection,
    chunking_strategy="recursive",
    chunk_size=1000,
    chunk_overlap=200,
):
    try:
        response = requests.post(
            f"{API_BASE_URL}/collections/{collection}/rechunk",
            headers=_request_headers(),
            json={
                "chunking_strategy": chunking_strategy,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
            timeout=120,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to re-chunk collection", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while re-chunking collection: {str(e)}")
        return None


def get_collection_analytics(collection):
    try:
        response = requests.get(
            f"{API_BASE_URL}/collections/{collection}/analytics",
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to load collection analytics", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while loading collection analytics: {str(e)}")
        return None


def delete_documents(file_ids):
    try:
        response = requests.post(
            f"{API_BASE_URL}/delete-docs",
            headers=_request_headers(),
            json={"file_ids": file_ids},
            timeout=60,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to delete documents", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while deleting documents: {str(e)}")
        return None


def delete_sessions(session_ids):
    try:
        response = requests.post(
            f"{API_BASE_URL}/delete-sessions",
            headers=_request_headers(),
            json={"session_ids": session_ids},
            timeout=60,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to delete sessions", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while deleting sessions: {str(e)}")
        return None



def get_health():
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == HTTP_OK:
            return response.json()
    except Exception:
        return None
    return None


def get_stats():
    try:
        response = requests.get(
            f"{API_BASE_URL}/stats", headers=_request_headers(), timeout=5
        )
        if response.status_code == HTTP_OK:
            return response.json()
    except Exception:
        return None
    return None


def get_metrics():
    try:
        response = requests.get(f"{API_BASE_URL}/metrics.json", timeout=5)
        if response.status_code == HTTP_OK:
            return response.json()
    except Exception:
        return None
    return None


def get_quota():
    try:
        response = requests.get(
            f"{API_BASE_URL}/quota", headers=_request_headers(), timeout=5
        )
        if response.status_code == HTTP_OK:
            return response.json()
    except Exception:
        return None
    return None


def get_config():
    try:
        response = requests.get(
            f"{API_BASE_URL}/config", headers=_request_headers(), timeout=5
        )
        if response.status_code == HTTP_OK:
            return response.json()
    except Exception:
        return None
    return None


def list_webhooks(active_only: bool = False, event: str | None = None):
    params: dict[str, str | bool] = {}
    if active_only:
        params["active_only"] = True
    if event:
        params["event"] = event
    try:
        response = requests.get(
            f"{API_BASE_URL}/webhooks",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error("Failed to list webhooks", response)
        return []
    except Exception as e:
        st.error(f"An error occurred while listing webhooks: {str(e)}")
        return []


def create_webhook(
    url: str,
    events: str | list[str] | None = "*",
    secret: str | None = None,
    is_active: bool = True,
):
    payload = {
        "url": url,
        "events": events or "*",
        "secret": secret or "",
        "is_active": is_active,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/webhooks",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code in (HTTP_OK, HTTP_CREATED):
            return response.json()
        show_api_error("Failed to register webhook", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while registering webhook: {str(e)}")
        return None


def update_webhook(  # noqa: PLR0913, PLR0917
    webhook_id: int,
    url: str | None = None,
    events: str | None = None,
    secret: str | None = None,
    is_active: bool | None = None,
    reset_failures: bool = False,
):
    payload: dict[str, Any] = {"reset_failures": reset_failures}
    if url is not None:
        payload["url"] = url
    if events is not None:
        payload["events"] = events
    if secret is not None:
        payload["secret"] = secret
    if is_active is not None:
        payload["is_active"] = is_active

    try:
        response = requests.patch(
            f"{API_BASE_URL}/webhooks/{webhook_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error(f"Failed to update webhook {webhook_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating webhook: {str(e)}")
        return None


def delete_webhook(webhook_id: int) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/webhooks/{webhook_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete webhook {webhook_id}", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting webhook: {str(e)}")
        return False


def ping_webhook(webhook_id: int):
    try:
        response = requests.post(
            f"{API_BASE_URL}/webhooks/{webhook_id}/ping",
            headers=_request_headers(),
            timeout=15,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error(f"Failed to ping webhook {webhook_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while pinging webhook: {str(e)}")
        return None


def list_webhook_deliveries(webhook_id: int | None = None, limit: int = 50, offset: int = 0):
    params: dict[str, int] = {"limit": limit, "offset": offset}
    if webhook_id is not None:
        params["webhook_id"] = webhook_id

    try:
        response = requests.get(
            f"{API_BASE_URL}/webhooks/deliveries",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error("Failed to fetch webhook deliveries", response)
        return {"items": [], "total": 0}
    except Exception as e:
        st.error(f"An error occurred while fetching webhook deliveries: {str(e)}")
        return {"items": [], "total": 0}


def create_macro(  # noqa: PLR0913, PLR0917
    title: str,
    shortcut: str,
    category: str,
    content: str,
    tags: list[str] | None = None,
    status_action: str | None = None,
):
    payload: dict[str, Any] = {
        "title": title,
        "shortcut": shortcut,
        "category": category,
        "content": content,
        "tags": tags or [],
        "status_action": status_action,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/macros",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return response.json()
        show_api_error("Failed to create macro", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating macro: {str(e)}")
        return None


def list_macros(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
):
    params: dict[str, str] = {}
    if category:
        params["category"] = category
    if tag:
        params["tag"] = tag
    if search:
        params["search"] = search

    try:
        response = requests.get(
            f"{API_BASE_URL}/macros",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        show_api_error("Failed to fetch macros", response)
        return []
    except Exception as e:
        st.error(f"An error occurred while fetching macros: {str(e)}")
        return []


def list_macro_categories() -> list[str]:
    try:
        response = requests.get(
            f"{API_BASE_URL}/macros/categories",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            data = response.json()
            if isinstance(data, dict):
                cats = data.get("categories", [])
                return list(cats) if isinstance(cats, list) else []
            return []
        show_api_error("Failed to fetch macro categories", response)
        return []
    except Exception as e:
        st.error(f"An error occurred while fetching macro categories: {str(e)}")
        return []


def get_macro(macro_id: int):
    try:
        response = requests.get(
            f"{API_BASE_URL}/macros/{macro_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error(f"Failed to fetch macro {macro_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching macro {macro_id}: {str(e)}")
        return None


def update_macro(  # noqa: PLR0913, PLR0917
    macro_id: int,
    title: str | None = None,
    shortcut: str | None = None,
    category: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    status_action: str | None = None,
):
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if shortcut is not None:
        payload["shortcut"] = shortcut
    if category is not None:
        payload["category"] = category
    if content is not None:
        payload["content"] = content
    if tags is not None:
        payload["tags"] = tags
    if status_action is not None:
        payload["status_action"] = status_action

    try:
        response = requests.patch(
            f"{API_BASE_URL}/macros/{macro_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error(f"Failed to update macro {macro_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating macro: {str(e)}")
        return None


def delete_macro(macro_id: int) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/macros/{macro_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete macro {macro_id}", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting macro: {str(e)}")
        return False


def render_macro(
    macro_id: int,
    variables: dict[str, str] | None = None,
    fallback_defaults: bool = True,
):
    payload: dict[str, Any] = {
        "variables": variables or {},
        "fallback_defaults": fallback_defaults,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/macros/{macro_id}/render",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error(f"Failed to render macro {macro_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while rendering macro: {str(e)}")
        return None


def apply_macro_to_session(  # noqa: PLR0913, PLR0917
    session_id: str,
    macro_id: int | None = None,
    shortcut: str | None = None,
    variables: dict[str, str] | None = None,
    update_status: bool = True,
    append_tags: bool = True,
    model: str | None = None,
    fallback_defaults: bool = True,
):
    payload: dict[str, Any] = {
        "macro_id": macro_id,
        "shortcut": shortcut,
        "variables": variables or {},
        "update_status": update_status,
        "append_tags": append_tags,
        "model": model,
        "fallback_defaults": fallback_defaults,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/apply-macro",
            json=payload,
            headers=_request_headers(),
            timeout=15,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        show_api_error(f"Failed to apply macro to session {session_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while applying macro: {str(e)}")
        return None


def suggest_macros(  # noqa: PLR0913, PLR0917
    query: str,
    session_id: str | None = None,
    category: str | None = None,
    top_k: int = 3,
    min_score: float = 0.3,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "query": query,
        "session_id": session_id,
        "category": category,
        "top_k": top_k,
        "min_score": min_score,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/macros/suggest",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch macro suggestions", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching macro suggestions: {str(e)}")
        return None


def get_session_macro_suggestions(
    session_id: str,
    top_k: int = 3,
    min_score: float = 0.3,
    category: str | None = None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "top_k": top_k,
        "min_score": min_score,
    }
    if category:
        params["category"] = category
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/macro-suggestions",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch macro suggestions for session {session_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching session macro suggestions: {str(e)}")
        return None


# ============================================================================
# SLA Policies & Escalation Alerts API Helpers
# ============================================================================


def list_sla_policies(
    priority: str | None = None,
    category: str | None = None,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"active_only": active_only}
    if priority:
        params["priority"] = priority
    if category:
        params["category"] = category
    try:
        response = requests.get(
            f"{API_BASE_URL}/sla/policies",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            data = response.json()
            return cast(list[dict[str, Any]], data.get("items", []))
        show_api_error("Failed to list SLA policies", response)
        return []
    except Exception as e:
        st.error(f"An error occurred while listing SLA policies: {str(e)}")
        return []


def create_sla_policy(  # noqa: PLR0913, PLR0917
    name: str,
    priority: str,
    category: str = "general",
    response_time_minutes: int = 60,
    resolution_time_minutes: int = 480,
    is_active: bool = True,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "name": name,
        "priority": priority,
        "category": category,
        "response_time_minutes": response_time_minutes,
        "resolution_time_minutes": resolution_time_minutes,
        "is_active": is_active,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/sla/policies",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create SLA policy", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating SLA policy: {str(e)}")
        return None


def get_sla_policy(policy_id: int) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/sla/policies/{policy_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch SLA policy {policy_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching SLA policy: {str(e)}")
        return None


def update_sla_policy(  # noqa: PLR0913, PLR0917
    policy_id: int,
    name: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    response_time_minutes: int | None = None,
    resolution_time_minutes: int | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if priority is not None:
        payload["priority"] = priority
    if category is not None:
        payload["category"] = category
    if response_time_minutes is not None:
        payload["response_time_minutes"] = response_time_minutes
    if resolution_time_minutes is not None:
        payload["resolution_time_minutes"] = resolution_time_minutes
    if is_active is not None:
        payload["is_active"] = is_active
    try:
        response = requests.patch(
            f"{API_BASE_URL}/sla/policies/{policy_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update SLA policy {policy_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating SLA policy: {str(e)}")
        return None


def delete_sla_policy(policy_id: int) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/sla/policies/{policy_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete SLA policy {policy_id}", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting SLA policy: {str(e)}")
        return False


def get_session_sla_status(session_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/sla",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching SLA status: {str(e)}")
        return None


def evaluate_sla_alerts(
    approaching_threshold_minutes: int = 30,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {"approaching_threshold_minutes": approaching_threshold_minutes}
    try:
        response = requests.post(
            f"{API_BASE_URL}/sla/evaluate-alerts",
            json=payload,
            headers=_request_headers(),
            timeout=15,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to evaluate SLA alerts", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while evaluating SLA alerts: {str(e)}")
        return None


def get_sla_compliance_analytics() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/sla/analytics",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch SLA analytics", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching SLA analytics: {str(e)}")
        return None


# =====================================================================
# Support Agents, Session Assignment & Business Hours Client Helpers
# =====================================================================


def list_support_agents(
    tier: str | None = None,
    department: str | None = None,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if tier:
        params["tier"] = tier
    if department:
        params["department"] = department
    if active_only:
        params["active_only"] = "true"

    try:
        response = requests.get(
            f"{API_BASE_URL}/agents",
            params=params or None,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(list[dict[str, Any]], response.json().get("items", []))
        show_api_error("Failed to list support agents", response)
        return []
    except Exception as e:
        st.error(f"An error occurred while fetching support agents: {str(e)}")
        return []


def create_support_agent(  # noqa: PLR0913, PLR0917
    agent_id: str,
    name: str,
    email: str,
    tier: str = "tier_1",
    department: str = "general_leasing",
    is_active: bool = True,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "id": agent_id,
        "name": name,
        "email": email,
        "tier": tier,
        "department": department,
        "is_active": is_active,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/agents",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create support agent", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating support agent: {str(e)}")
        return None


def get_support_agent(agent_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/agents/{agent_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch support agent {agent_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching support agent: {str(e)}")
        return None


def update_support_agent(  # noqa: PLR0913, PLR0917
    agent_id: str,
    name: str | None = None,
    email: str | None = None,
    tier: str | None = None,
    department: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if email is not None:
        payload["email"] = email
    if tier is not None:
        payload["tier"] = tier
    if department is not None:
        payload["department"] = department
    if is_active is not None:
        payload["is_active"] = is_active

    try:
        response = requests.patch(
            f"{API_BASE_URL}/agents/{agent_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update support agent {agent_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating support agent: {str(e)}")
        return None


def delete_support_agent(agent_id: str) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/agents/{agent_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete support agent {agent_id}", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting support agent: {str(e)}")
        return False


def get_agent_workload_analytics() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/agents/workload",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch agent workload", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching agent workload: {str(e)}")
        return None


def assign_session(
    session_id: str,
    agent_id: str | None = None,
    tier: str | None = None,
    assigned_by: str = "dispatcher",
    reason: str = "",
) -> dict[str, Any] | None:
    payload = {
        "agent_id": agent_id,
        "tier": tier,
        "assigned_by": assigned_by,
        "reason": reason,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/assign",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to assign session {session_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while assigning session: {str(e)}")
        return None


def auto_assign_session(
    session_id: str,
    strategy: str = "least_busy",
    target_tier: str | None = None,
    department: str | None = None,
    assigned_by: str = "auto_dispatcher",
) -> dict[str, Any] | None:
    payload = {
        "strategy": strategy,
        "target_tier": target_tier,
        "department": department,
        "assigned_by": assigned_by,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/auto-assign",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to auto-assign session {session_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while auto-assigning session: {str(e)}")
        return None


def get_session_assignment_history(
    session_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/assignment-history",
            params={"limit": limit},
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(list[dict[str, Any]], response.json().get("items", []))
        show_api_error(f"Failed to fetch assignment history for {session_id}", response)
        return []
    except Exception as e:
        st.error(f"An error occurred while fetching assignment history: {str(e)}")
        return []


def get_business_hours_status() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/business-hours/status",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch business hours status", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching business hours status: {str(e)}")
        return None


# ============================================================================
# Knowledge Base Gap Detection, Article Studio & Deflection Client Helpers
# ============================================================================


def record_knowledge_gap(  # noqa: PLR0913, PLR0917
    query: str,
    category: str = "general",
    source_type: str = "manual",
    session_id: str | None = None,
    priority: str = "medium",
    notes: str = "",
) -> dict[str, Any] | None:
    try:
        payload = {
            "query": query,
            "category": category,
            "source_type": source_type,
            "session_id": session_id,
            "priority": priority,
            "notes": notes,
        }
        response = requests.post(
            f"{API_BASE_URL}/knowledge/gaps",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to record knowledge gap", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while recording knowledge gap: {str(e)}")
        return None


def list_knowledge_gaps(  # noqa: PLR0913, PLR0917
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if priority:
            params["priority"] = priority
        if source_type:
            params["source_type"] = source_type

        response = requests.get(
            f"{API_BASE_URL}/knowledge/gaps",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            data = response.json()
            return cast(list[dict[str, Any]], data.get("items", [])), int(data.get("total", 0))
        show_api_error("Failed to fetch knowledge gaps", response)
        return [], 0
    except Exception as e:
        st.error(f"An error occurred while fetching knowledge gaps: {str(e)}")
        return [], 0


def scan_knowledge_gaps(limit: int = 100) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/knowledge/gaps/scan",
            params={"limit": limit},
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to scan knowledge gaps", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while scanning knowledge gaps: {str(e)}")
        return None


def update_knowledge_gap(  # noqa: PLR0913, PLR0917
    gap_id: int,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    linked_article_id: int | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if priority is not None:
            payload["priority"] = priority
        if category is not None:
            payload["category"] = category
        if linked_article_id is not None:
            payload["linked_article_id"] = linked_article_id
        if notes is not None:
            payload["notes"] = notes

        response = requests.patch(
            f"{API_BASE_URL}/knowledge/gaps/{gap_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update knowledge gap #{gap_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating knowledge gap: {str(e)}")
        return None


def delete_knowledge_gap(gap_id: int) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/knowledge/gaps/{gap_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete knowledge gap #{gap_id}", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting knowledge gap: {str(e)}")
        return False


def create_knowledge_article(  # noqa: PLR0913, PLR0917
    title: str,
    content_markdown: str,
    category: str = "general",
    question_pattern: str = "",
    tags: list[str] | None = None,
    source_session_id: str | None = None,
    source_gap_id: int | None = None,
    author: str = "support_agent",
) -> dict[str, Any] | None:
    try:
        payload = {
            "title": title,
            "content_markdown": content_markdown,
            "category": category,
            "question_pattern": question_pattern,
            "tags": tags or [],
            "source_session_id": source_session_id,
            "source_gap_id": source_gap_id,
            "author": author,
        }
        response = requests.post(
            f"{API_BASE_URL}/knowledge/articles",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create knowledge article", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating knowledge article: {str(e)}")
        return None


def draft_article_from_session(
    session_id: str,
    author: str = "support_agent",
    category: str | None = None,
    link_gap_id: int | None = None,
) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = {"author": author}
        if category:
            payload["category"] = category
        if link_gap_id is not None:
            payload["link_gap_id"] = link_gap_id

        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/draft-article",
            json=payload,
            headers=_request_headers(),
            timeout=20,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to draft article from session {session_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while drafting article: {str(e)}")
        return None


def list_knowledge_articles(
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if search:
            params["search"] = search

        response = requests.get(
            f"{API_BASE_URL}/knowledge/articles",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            data = response.json()
            return cast(list[dict[str, Any]], data.get("items", [])), int(data.get("total", 0))
        show_api_error("Failed to fetch knowledge articles", response)
        return [], 0
    except Exception as e:
        st.error(f"An error occurred while fetching knowledge articles: {str(e)}")
        return [], 0


def get_knowledge_article(article_id: int) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/knowledge/articles/{article_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch knowledge article #{article_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching knowledge article: {str(e)}")
        return None


def update_knowledge_article(  # noqa: PLR0913, PLR0917
    article_id: int,
    title: str | None = None,
    content_markdown: str | None = None,
    category: str | None = None,
    question_pattern: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if content_markdown is not None:
            payload["content_markdown"] = content_markdown
        if category is not None:
            payload["category"] = category
        if question_pattern is not None:
            payload["question_pattern"] = question_pattern
        if tags is not None:
            payload["tags"] = tags
        if status is not None:
            payload["status"] = status

        response = requests.patch(
            f"{API_BASE_URL}/knowledge/articles/{article_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update knowledge article #{article_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating knowledge article: {str(e)}")
        return None


def delete_knowledge_article(article_id: int) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/knowledge/articles/{article_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete knowledge article #{article_id}", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting knowledge article: {str(e)}")
        return False


def publish_knowledge_article(
    article_id: int,
    collection: str = "default",
    chunking_strategy: str = "markdown",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any] | None:
    try:
        payload = {
            "collection": collection,
            "chunking_strategy": chunking_strategy,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        response = requests.post(
            f"{API_BASE_URL}/knowledge/articles/{article_id}/publish",
            json=payload,
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to publish knowledge article #{article_id}", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while publishing knowledge article: {str(e)}")
        return None


def get_knowledge_analytics() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/knowledge/analytics",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch knowledge analytics", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching knowledge analytics: {str(e)}")
        return None



