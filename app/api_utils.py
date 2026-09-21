import requests
import streamlit as st
from api.settings import settings

API_BASE_URL = settings.api_base_url

HTTP_OK = 200


def _request_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Headers shared by every API call; forwards the API key when configured."""
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    if settings.api_key:
        headers["X-API-Key"] = settings.api_key
    if extra:
        headers.update(extra)
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
            headers=_request_headers(),
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
            headers=_request_headers(),
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


def list_sessions():
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions", headers=_request_headers(), timeout=30
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


def rename_session(session_id, label):
    try:
        response = requests.patch(
            f"{API_BASE_URL}/sessions/{session_id}",
            json={"label": label},
            headers=_request_headers(),
            timeout=30,
        )
        if response.status_code == HTTP_OK:
            return response.json()
        else:
            show_api_error("Failed to rename session", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while renaming the session: {str(e)}")
        return None


def export_session(session_id):
    try:
        response = requests.get(
            f"{API_BASE_URL}/sessions/{session_id}/export",
            headers=_request_headers({"accept": "text/markdown"}),
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


def submit_feedback(session_id, rating):
    try:
        response = requests.post(
            f"{API_BASE_URL}/feedback",
            json={"session_id": session_id, "rating": rating},
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

