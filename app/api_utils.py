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
        payload: dict[str, Any] = {
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


# --- Property Units Client Helpers ---


def list_units(
    property_name: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if property_name and property_name.strip():
            params["property_name"] = property_name.strip()
        if search and search.strip():
            params["search"] = search.strip()
        response = requests.get(
            f"{API_BASE_URL}/units",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to list property units", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while listing units: {str(e)}")
        return None


def get_unit(unit_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/units/{unit_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch unit '{unit_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching unit: {str(e)}")
        return None


def create_unit(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/units",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create property unit", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating unit: {str(e)}")
        return None


def update_unit(unit_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.patch(
            f"{API_BASE_URL}/units/{unit_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update unit '{unit_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating unit: {str(e)}")
        return None


def delete_unit(unit_id: str) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/units/{unit_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete unit '{unit_id}'", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting unit: {str(e)}")
        return False


# --- Tenants Client Helpers ---


def list_tenants(
    unit_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if unit_id and unit_id.strip():
            params["unit_id"] = unit_id.strip()
        if status and status.strip():
            params["status"] = status.strip()
        if search and search.strip():
            params["search"] = search.strip()
        response = requests.get(
            f"{API_BASE_URL}/tenants",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to list tenants", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while listing tenants: {str(e)}")
        return None


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/tenants/{tenant_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant: {str(e)}")
        return None


def create_tenant(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/tenants",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create tenant", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating tenant: {str(e)}")
        return None


def update_tenant(tenant_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.patch(
            f"{API_BASE_URL}/tenants/{tenant_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating tenant: {str(e)}")
        return None


def delete_tenant(tenant_id: str) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/tenants/{tenant_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete tenant '{tenant_id}'", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting tenant: {str(e)}")
        return False


# --- Session Tenant Linking & Context Client Helpers ---


def link_session_tenant(
    session_id: str,
    tenant_id: str | None = None,
    unit_id: str | None = None,
) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = {"tenant_id": tenant_id, "unit_id": unit_id}
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/link-tenant",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to link tenant to session '{session_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while linking tenant to session: {str(e)}")
        return None


def get_session_tenant_context(session_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/tenant-context",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch tenant context for session '{session_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant context: {str(e)}")
        return None


def get_tenant_support_history(tenant_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/tenants/{tenant_id}/support-history",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch support history for tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant support history: {str(e)}")
        return None


# --- Maintenance Work Orders & Dispatch Client Helpers ---


def list_work_orders(  # noqa: PLR0913, PLR0917
    unit_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if unit_id and unit_id.strip():
            params["unit_id"] = unit_id.strip()
        if tenant_id and tenant_id.strip():
            params["tenant_id"] = tenant_id.strip()
        if status and status.strip():
            params["status"] = status.strip()
        if priority and priority.strip():
            params["priority"] = priority.strip()
        if category and category.strip():
            params["category"] = category.strip()
        if search and search.strip():
            params["search"] = search.strip()
        response = requests.get(
            f"{API_BASE_URL}/work-orders",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to list work orders", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while listing work orders: {str(e)}")
        return None


def get_work_order(work_order_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/work-orders/{work_order_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch work order '{work_order_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching work order: {str(e)}")
        return None


def get_work_order_metrics() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/work-orders/metrics",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch work order metrics", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching work order metrics: {str(e)}")
        return None


def create_work_order(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/work-orders",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create work order", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating work order: {str(e)}")
        return None


def update_work_order(
    work_order_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        response = requests.patch(
            f"{API_BASE_URL}/work-orders/{work_order_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update work order '{work_order_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating work order: {str(e)}")
        return None


def delete_work_order(work_order_id: str) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/work-orders/{work_order_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete work order '{work_order_id}'", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting work order: {str(e)}")
        return False


def create_work_order_from_session(
    session_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/create-work-order",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error(
            f"Failed to create work order from session '{session_id}'", response
        )
        return None
    except Exception as e:
        st.error(f"An error occurred while creating work order from session: {str(e)}")
        return None


def get_unit_work_orders(
    unit_id: str, open_only: bool = False
) -> dict[str, Any] | None:
    try:
        params = {"open_only": str(open_only).lower()}
        response = requests.get(
            f"{API_BASE_URL}/units/{unit_id}/work-orders",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch work orders for unit '{unit_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching unit work orders: {str(e)}")
        return None


def get_tenant_work_orders(
    tenant_id: str, open_only: bool = False
) -> dict[str, Any] | None:
    try:
        params = {"open_only": str(open_only).lower()}
        response = requests.get(
            f"{API_BASE_URL}/tenants/{tenant_id}/work-orders",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(
            f"Failed to fetch work orders for tenant '{tenant_id}'", response
        )
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant work orders: {str(e)}")
        return None


def create_billing_transaction(
    payload: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/billing/transactions",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create billing transaction", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating billing transaction: {str(e)}")
        return None


def list_billing_transactions(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tenant_id:
            params["tenant_id"] = tenant_id
        if unit_id:
            params["unit_id"] = unit_id
        if transaction_type:
            params["transaction_type"] = transaction_type
        if status:
            params["status"] = status
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if search:
            params["search"] = search

        response = requests.get(
            f"{API_BASE_URL}/billing/transactions",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch billing transactions", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching billing transactions: {str(e)}")
        return None


def get_billing_metrics() -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/billing/metrics",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch billing metrics", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching billing metrics: {str(e)}")
        return None


def get_billing_transaction(transaction_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/billing/transactions/{transaction_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch transaction '{transaction_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching billing transaction: {str(e)}")
        return None


def update_billing_transaction(
    transaction_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        response = requests.patch(
            f"{API_BASE_URL}/billing/transactions/{transaction_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update transaction '{transaction_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating billing transaction: {str(e)}")
        return None


def delete_billing_transaction(transaction_id: str) -> bool:
    try:
        response = requests.delete(
            f"{API_BASE_URL}/billing/transactions/{transaction_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete transaction '{transaction_id}'", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting billing transaction: {str(e)}")
        return False


def record_tenant_payment(
    tenant_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/tenants/{tenant_id}/payments",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to record payment for tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while recording payment: {str(e)}")
        return None


def get_tenant_ledger(tenant_id: str) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/tenants/{tenant_id}/ledger",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch ledger for tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant ledger: {str(e)}")
        return None


def record_session_payment(
    session_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/record-payment",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error(
            f"Failed to record payment from session '{session_id}'", response
        )
        return None
    except Exception as e:
        st.error(f"An error occurred while recording session payment: {str(e)}")
        return None


# ---------------------------------------------------------------------------
# Lease Renewals & Documents Client Helpers (v0.38.0)
# ---------------------------------------------------------------------------


def list_lease_renewals(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    """Retrieve paginated list of lease renewal offers and agreements."""
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tenant_id:
            params["tenant_id"] = tenant_id
        if unit_id:
            params["unit_id"] = unit_id
        if status:
            params["status"] = status
        if search:
            params["search"] = search

        response = requests.get(
            f"{API_BASE_URL}/lease-renewals",
            params=params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch lease renewals", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching lease renewals: {str(e)}")
        return None


def get_lease_renewal(renewal_id: str) -> dict[str, Any] | None:
    """Retrieve single lease renewal offer details by ID."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/lease-renewals/{renewal_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch lease renewal '{renewal_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching lease renewal: {str(e)}")
        return None


def get_lease_renewal_metrics() -> dict[str, Any] | None:
    """Retrieve portfolio-level lease renewal analytics and conversion metrics."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/lease-renewals/metrics",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch lease renewal metrics", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching renewal metrics: {str(e)}")
        return None


def create_lease_renewal(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Create a new lease renewal offer for a resident."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/lease-renewals",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create lease renewal offer", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating lease renewal offer: {str(e)}")
        return None


def update_lease_renewal(
    renewal_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Update renewal offer terms, concessions, or status."""
    try:
        response = requests.patch(
            f"{API_BASE_URL}/lease-renewals/{renewal_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update lease renewal '{renewal_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating lease renewal: {str(e)}")
        return None


def delete_lease_renewal(renewal_id: str) -> bool:
    """Delete a lease renewal record."""
    try:
        response = requests.delete(
            f"{API_BASE_URL}/lease-renewals/{renewal_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete lease renewal '{renewal_id}'", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting lease renewal: {str(e)}")
        return False


def sign_lease_renewal(
    renewal_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Record digital e-signature and execute lease renewal."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/lease-renewals/{renewal_id}/sign",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to digitally sign renewal '{renewal_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while signing lease renewal: {str(e)}")
        return None


def publish_lease_renewal_document(
    renewal_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Synthesize Markdown agreement and publish to vector knowledge base."""
    try:
        body = payload or {
            "collection": "default",
            "chunking_strategy": "markdown",
            "chunk_size": 1000,
            "chunk_overlap": 200,
        }
        response = requests.post(
            f"{API_BASE_URL}/lease-renewals/{renewal_id}/publish-document",
            json=body,
            headers=_request_headers(),
            timeout=15,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to publish agreement for renewal '{renewal_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while publishing renewal agreement: {str(e)}")
        return None


def create_session_lease_renewal(
    session_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Generate 1-click renewal offer directly from active session card."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/create-lease-renewal",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error(
            f"Failed to create renewal offer from session '{session_id}'", response
        )
        return None
    except Exception as e:
        st.error(f"An error occurred while creating session renewal offer: {str(e)}")
        return None


def get_tenant_lease_renewals(tenant_id: str) -> dict[str, Any] | None:
    """Retrieve all lease renewal records for a resident."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/tenants/{tenant_id}/lease-renewals",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch renewals for tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant renewals: {str(e)}")
        return None


# ---------------------------------------------------------------------------
# Resident Move-In/Move-Out Inspection & Turnover Helpers (v0.39.0)
# ---------------------------------------------------------------------------


def create_inspection(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Schedule and create a resident inspection."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/inspections",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to create inspection", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while creating inspection: {str(e)}")
        return None


def list_inspections(params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """List inspection records with optional status/type/tenant filters."""
    try:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        response = requests.get(
            f"{API_BASE_URL}/inspections",
            params=clean_params,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch inspections", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching inspections: {str(e)}")
        return None


def get_inspection(insp_id: str) -> dict[str, Any] | None:
    """Fetch inspection details by ID."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/inspections/{insp_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch inspection '{insp_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching inspection: {str(e)}")
        return None


def update_inspection(insp_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Update inspection details, status, or checklist items."""
    try:
        response = requests.patch(
            f"{API_BASE_URL}/inspections/{insp_id}",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to update inspection '{insp_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while updating inspection: {str(e)}")
        return None


def delete_inspection(insp_id: str) -> bool:
    """Delete or cancel an inspection record."""
    try:
        response = requests.delete(
            f"{API_BASE_URL}/inspections/{insp_id}",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return True
        show_api_error(f"Failed to delete inspection '{insp_id}'", response)
        return False
    except Exception as e:
        st.error(f"An error occurred while deleting inspection: {str(e)}")
        return False


def complete_inspection(
    insp_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Finalize an inspection and calculate deposit settlement."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/inspections/{insp_id}/complete",
            json=payload or {},
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to complete inspection '{insp_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while completing inspection: {str(e)}")
        return None


def convert_inspection_item_to_work_order(
    insp_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Convert an inspection deficiency item to a maintenance work order."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/inspections/{insp_id}/convert-to-work-order",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to convert punchlist item for inspection '{insp_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while converting inspection punchlist item: {str(e)}")
        return None


def publish_inspection_document(
    insp_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Synthesize inspection Markdown statement and index into vector knowledge base."""
    try:
        body = payload or {
            "collection": "default",
            "chunking_strategy": "markdown",
            "chunk_size": 1000,
            "chunk_overlap": 200,
        }
        response = requests.post(
            f"{API_BASE_URL}/inspections/{insp_id}/publish-document",
            json=body,
            headers=_request_headers(),
            timeout=15,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to publish report for inspection '{insp_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while publishing inspection report: {str(e)}")
        return None


def create_session_inspection(
    session_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Schedule inspection directly from resident support chat session card."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/sessions/{session_id}/create-inspection",
            json=payload,
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_CREATED:
            return cast(dict[str, Any], response.json())
        show_api_error(
            f"Failed to schedule inspection from session '{session_id}'", response
        )
        return None
    except Exception as e:
        st.error(f"An error occurred while creating session inspection: {str(e)}")
        return None


def get_tenant_inspections(tenant_id: str) -> dict[str, Any] | None:
    """Retrieve all inspection records for a resident."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/tenants/{tenant_id}/inspections",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch inspections for tenant '{tenant_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching tenant inspections: {str(e)}")
        return None


def get_unit_inspections(unit_id: str) -> dict[str, Any] | None:
    """Retrieve all inspection records for a unit."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/units/{unit_id}/inspections",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error(f"Failed to fetch inspections for unit '{unit_id}'", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching unit inspections: {str(e)}")
        return None


def get_inspection_metrics() -> dict[str, Any] | None:
    """Retrieve portfolio turnover & inspection KPI metrics."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/inspections/metrics",
            headers=_request_headers(),
            timeout=10,
        )
        if response.status_code == HTTP_OK:
            return cast(dict[str, Any], response.json())
        show_api_error("Failed to fetch inspection metrics", response)
        return None
    except Exception as e:
        st.error(f"An error occurred while fetching inspection metrics: {str(e)}")
        return None











# --- Maintenance Vendor Directory & Dispatch Client Helpers ---


def _vendor_call(  # noqa: PLR0913
    method: str,
    path: str,
    expected_status: int,
    failure_message: str,
    error_context: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Issue an authenticated vendor API request; show an error and return None on failure."""
    try:
        response = getattr(requests, method)(
            f"{API_BASE_URL}{path}",
            headers=_request_headers(),
            timeout=10,
            **kwargs,
        )
        if response.status_code == expected_status:
            return cast(dict[str, Any], response.json())
        show_api_error(failure_message, response)
        return None
    except Exception as e:
        st.error(f"An error occurred while {error_context}: {str(e)}")
        return None


def list_vendors(  # noqa: PLR0913
    trade: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    for key, value in (("trade", trade), ("status", status), ("search", search)):
        if value and value.strip():
            params[key] = value.strip()
    return _vendor_call(
        "get", "/vendors", HTTP_OK, "Failed to list vendors", "listing vendors", params=params
    )


def get_vendor(vendor_id: str) -> dict[str, Any] | None:
    return _vendor_call(
        "get",
        f"/vendors/{vendor_id}",
        HTTP_OK,
        f"Failed to fetch vendor '{vendor_id}'",
        "fetching vendor",
    )


def get_vendor_metrics() -> dict[str, Any] | None:
    return _vendor_call(
        "get",
        "/vendors/metrics",
        HTTP_OK,
        "Failed to fetch vendor metrics",
        "fetching vendor metrics",
    )


def create_vendor(payload: dict[str, Any]) -> dict[str, Any] | None:
    return _vendor_call(
        "post",
        "/vendors",
        HTTP_CREATED,
        "Failed to create vendor",
        "creating vendor",
        json=payload,
    )


def update_vendor(vendor_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return _vendor_call(
        "patch",
        f"/vendors/{vendor_id}",
        HTTP_OK,
        f"Failed to update vendor '{vendor_id}'",
        "updating vendor",
        json=payload,
    )


def delete_vendor(vendor_id: str) -> bool:
    result = _vendor_call(
        "delete",
        f"/vendors/{vendor_id}",
        HTTP_OK,
        f"Failed to delete vendor '{vendor_id}'",
        "deleting vendor",
    )
    return result is not None


def dispatch_vendor_to_work_order(
    work_order_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    return _vendor_call(
        "post",
        f"/work-orders/{work_order_id}/dispatch-vendor",
        HTTP_CREATED,
        f"Failed to dispatch a vendor to work order '{work_order_id}'",
        "dispatching vendor",
        json=payload,
    )


def complete_vendor_dispatch(dispatch_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return _vendor_call(
        "post",
        f"/vendor-dispatches/{dispatch_id}/complete",
        HTTP_OK,
        f"Failed to complete vendor dispatch '{dispatch_id}'",
        "completing vendor dispatch",
        json=payload,
    )


def list_vendor_dispatches(
    vendor_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status and status.strip():
        params["status"] = status.strip()
    return _vendor_call(
        "get",
        f"/vendors/{vendor_id}/dispatches",
        HTTP_OK,
        f"Failed to list dispatches for vendor '{vendor_id}'",
        "listing vendor dispatches",
        params=params,
    )


def list_work_order_dispatches(
    work_order_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status and status.strip():
        params["status"] = status.strip()
    return _vendor_call(
        "get",
        f"/work-orders/{work_order_id}/dispatches",
        HTTP_OK,
        f"Failed to list dispatches for work order '{work_order_id}'",
        "listing work order dispatches",
        params=params,
    )


# --- Resident Packages & Parcel Delivery Lockers (v0.42.0) ---


def _package_call(  # noqa: PLR0913
    method: str,
    path: str,
    expected_status: int,
    failure_message: str,
    error_context: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Issue an authenticated package/parcel API request.

    Shows an error and returns None on failure.
    """
    try:
        response = getattr(requests, method)(
            f"{API_BASE_URL}{path}",
            headers=_request_headers(),
            timeout=10,
            **kwargs,
        )
        if response.status_code == expected_status:
            return cast(dict[str, Any], response.json())
        show_api_error(failure_message, response)
        return None
    except Exception as e:
        st.error(f"An error occurred while {error_context}: {str(e)}")
        return None


def create_package_api(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Intake an incoming parcel delivery into parcel locker management."""
    return _package_call(
        "post",
        "/packages",
        HTTP_CREATED,
        "Failed to intake package",
        "intaking package",
        json=payload,
    )


def list_packages_api(  # noqa: PLR0913, PLR0917
    tenant_id: str | None = None,
    unit_id: str | None = None,
    carrier: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    """List and filter resident packages and locker deliveries."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    for key, val in (
        ("tenant_id", tenant_id),
        ("unit_id", unit_id),
        ("carrier", carrier),
        ("status", status),
        ("search", search),
    ):
        if val and val.strip():
            params[key] = val.strip()
    return _package_call(
        "get",
        "/packages",
        HTTP_OK,
        "Failed to list packages",
        "listing packages",
        params=params,
    )


def get_package_api(package_id: str) -> dict[str, Any] | None:
    """Retrieve details for a specific parcel."""
    return _package_call(
        "get",
        f"/packages/{package_id}",
        HTTP_OK,
        f"Failed to fetch package '{package_id}'",
        "fetching package",
    )


def update_package_api(package_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Update location, notes, or status for an existing parcel."""
    return _package_call(
        "patch",
        f"/packages/{package_id}",
        HTTP_OK,
        f"Failed to update package '{package_id}'",
        "updating package",
        json=payload,
    )


def delete_package_api(package_id: str) -> bool:
    """Delete a parcel from parcel locker storage."""
    res = _package_call(
        "delete",
        f"/packages/{package_id}",
        HTTP_OK,
        f"Failed to delete package '{package_id}'",
        "deleting package",
    )
    return res is not None


def pickup_package_api(
    package_id: str, pickup_pin: str, picked_up_at: str | None = None
) -> dict[str, Any] | None:
    """Verify resident pickup PIN and release parcel."""
    payload: dict[str, Any] = {"pickup_pin": pickup_pin}
    if picked_up_at:
        payload["picked_up_at"] = picked_up_at
    return _package_call(
        "post",
        f"/packages/{package_id}/pickup",
        HTTP_OK,
        f"Failed to pickup package '{package_id}'",
        "picking up package",
        json=payload,
    )


def get_package_metrics_api() -> dict[str, Any] | None:
    """Retrieve parcel locker occupancy, carrier breakdown, and turnaround metrics."""
    return _package_call(
        "get",
        "/packages/metrics",
        HTTP_OK,
        "Failed to fetch package metrics",
        "fetching package metrics",
    )


def list_tenant_packages_api(
    tenant_id: str, pending_only: bool = False
) -> dict[str, Any] | None:
    """Retrieve packages for a resident."""
    params: dict[str, Any] = {}
    if pending_only:
        params["pending_only"] = True
    return _package_call(
        "get",
        f"/tenants/{tenant_id}/packages",
        HTTP_OK,
        f"Failed to fetch packages for tenant '{tenant_id}'",
        "fetching resident packages",
        params=params,
    )


def session_intake_package_api(
    session_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Intake an incoming parcel directly for the resident linked to active support session."""
    return _package_call(
        "post",
        f"/sessions/{session_id}/intake-package",
        HTTP_CREATED,
        "Failed to intake package for session",
        "intaking session package",
        json=payload,
    )





# --- Community Amenity Reservations & Common Area Bookings (v0.43.0) ---


def _amenity_call(  # noqa: PLR0913
    method: str,
    path: str,
    expected_status: int,
    failure_message: str,
    error_context: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Issue an authenticated amenity reservation API request.

    Shows an error and returns None on failure.
    """
    try:
        response = getattr(requests, method)(
            f"{API_BASE_URL}{path}",
            headers=_request_headers(),
            timeout=10,
            **kwargs,
        )
        if response.status_code == expected_status:
            return cast(dict[str, Any], response.json())
        show_api_error(failure_message, response)
        return None
    except Exception as e:
        st.error(f"An error occurred while {error_context}: {str(e)}")
        return None


def create_amenity_api(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Create a new community amenity in the catalog."""
    return _amenity_call(
        "post",
        "/amenities",
        HTTP_CREATED,
        "Failed to create amenity",
        "creating amenity",
        json=payload,
    )


def list_amenities_api(
    category: str | None = None,
    is_active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any] | None:
    """List community amenities."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if category and category.strip():
        params["category"] = category.strip()
    if is_active is not None:
        params["is_active"] = is_active
    return _amenity_call(
        "get",
        "/amenities",
        HTTP_OK,
        "Failed to list amenities",
        "listing amenities",
        params=params,
    )


def get_amenity_api(amenity_id: str) -> dict[str, Any] | None:
    """Retrieve details for a specific amenity."""
    return _amenity_call(
        "get",
        f"/amenities/{amenity_id}",
        HTTP_OK,
        f"Failed to fetch amenity '{amenity_id}'",
        "fetching amenity",
    )


def update_amenity_api(amenity_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Update fields of an existing amenity."""
    return _amenity_call(
        "patch",
        f"/amenities/{amenity_id}",
        HTTP_OK,
        f"Failed to update amenity '{amenity_id}'",
        "updating amenity",
        json=payload,
    )


def create_reservation_api(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Book an amenity reservation."""
    return _amenity_call(
        "post",
        "/amenity-reservations",
        HTTP_CREATED,
        "Failed to book amenity reservation",
        "booking amenity",
        json=payload,
    )


def list_reservations_api(  # noqa: PLR0913, PLR0917
    amenity_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any] | None:
    """List and filter amenity reservations."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    for key, val in (
        ("amenity_id", amenity_id),
        ("tenant_id", tenant_id),
        ("status", status),
    ):
        if val and val.strip():
            params[key] = val.strip()
    return _amenity_call(
        "get",
        "/amenity-reservations",
        HTTP_OK,
        "Failed to list reservations",
        "listing reservations",
        params=params,
    )


def get_reservation_api(reservation_id: str) -> dict[str, Any] | None:
    """Retrieve details for an amenity reservation."""
    return _amenity_call(
        "get",
        f"/amenity-reservations/{reservation_id}",
        HTTP_OK,
        f"Failed to fetch reservation '{reservation_id}'",
        "fetching reservation",
    )


def update_reservation_api(reservation_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Update reservation status or notes."""
    return _amenity_call(
        "patch",
        f"/amenity-reservations/{reservation_id}",
        HTTP_OK,
        f"Failed to update reservation '{reservation_id}'",
        "updating reservation",
        json=payload,
    )


def delete_reservation_api(reservation_id: str) -> bool:
    """Delete an amenity reservation."""
    res = _amenity_call(
        "delete",
        f"/amenity-reservations/{reservation_id}",
        HTTP_OK,
        f"Failed to delete reservation '{reservation_id}'",
        "deleting reservation",
    )
    return res is not None


def get_amenity_metrics_api() -> dict[str, Any] | None:
    """Retrieve amenity utilization metrics and summary statistics."""
    return _amenity_call(
        "get",
        "/amenity-reservations/metrics",
        HTTP_OK,
        "Failed to fetch amenity metrics",
        "fetching amenity metrics",
    )


def list_tenant_reservations_api(tenant_id: str) -> dict[str, Any] | None:
    """Retrieve reservations for a specific resident."""
    return _amenity_call(
        "get",
        f"/tenants/{tenant_id}/amenity-reservations",
        HTTP_OK,
        f"Failed to fetch reservations for tenant '{tenant_id}'",
        "fetching tenant reservations",
    )


def session_create_reservation_api(
    session_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Book an amenity reservation grounded to the active support session resident."""
    return _amenity_call(
        "post",
        f"/sessions/{session_id}/create-reservation",
        HTTP_CREATED,
        "Failed to book amenity reservation for session",
        "booking session amenity",
        json=payload,
    )
