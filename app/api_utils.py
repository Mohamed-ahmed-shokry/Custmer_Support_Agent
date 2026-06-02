import requests
import streamlit as st
from api.settings import settings


API_BASE_URL = settings.api_base_url


def extract_error_detail(response):
    try:
        payload = response.json()
    except ValueError:
        return response.text

    if not isinstance(payload, dict):
        return response.text

    detail = payload.get("detail")
    if isinstance(detail, list):
        return "; ".join(item.get("msg", str(item)) if isinstance(item, dict) else str(item) for item in detail)
    if detail:
        return str(detail)
    return response.text


def show_api_error(action, response):
    st.error(f"{action}. Status {response.status_code}: {extract_error_detail(response)}")


def get_api_response(question, session_id, model):
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    data = {
        "question": question,
        "model": model
    }
    if session_id:
        data["session_id"] = session_id

    try:
        response = requests.post(f"{API_BASE_URL}/chat", headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            show_api_error("API request failed", response)
            return None
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None

def upload_document(file):
    try:
        files = {"file": (file.name, file, file.type)}
        response = requests.post(f"{API_BASE_URL}/upload-doc", files=files, timeout=120)
        if response.status_code == 200:
            return response.json()
        else:
            show_api_error("Failed to upload file", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while uploading the file: {str(e)}")
        return None

def list_documents():
    try:
        response = requests.get(f"{API_BASE_URL}/list-docs", timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            show_api_error("Failed to fetch document list", response)
            return []
    except Exception as e:
        st.error(f"An error occurred while fetching the document list: {str(e)}")
        return []

def delete_document(file_id):
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    data = {"file_id": file_id}

    try:
        response = requests.post(f"{API_BASE_URL}/delete-doc", headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            show_api_error("Failed to delete document", response)
            return None
    except Exception as e:
        st.error(f"An error occurred while deleting the document: {str(e)}")
        return None

def get_health():
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        return None
    return None
