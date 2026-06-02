import streamlit as st
from api.pydantic_models import ModelName, model_from_value
from api.settings import settings
from api_utils import API_BASE_URL, delete_document, get_health, list_documents, upload_document

MODEL_OPTIONS = [model.value for model in ModelName]


def get_default_model_index():
    default_model = model_from_value(settings.default_model).value
    return MODEL_OPTIONS.index(default_model)


def display_sidebar():
    st.sidebar.caption(f"API: {API_BASE_URL}")
    health = get_health()
    if health:
        st.sidebar.success(f"Backend: {health['status']} ({health['version']})")
    else:
        st.sidebar.error("Backend unavailable")

    if st.sidebar.button("Reset Chat"):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    st.sidebar.selectbox("Select Model", options=MODEL_OPTIONS, index=get_default_model_index(), key="model")

    st.sidebar.header("Upload Document")
    uploaded_file = st.sidebar.file_uploader("Choose a file", type=["pdf", "docx", "html"])
    if uploaded_file is not None:
        if st.sidebar.button("Upload"):
            with st.spinner("Uploading..."):
                upload_response = upload_document(uploaded_file)
                if upload_response:
                    st.sidebar.success(f"File '{uploaded_file.name}' uploaded successfully with ID {upload_response['file_id']}.")
                    st.session_state.documents = list_documents()  # Refresh the list after upload

    st.sidebar.header("Uploaded Documents")
    if st.sidebar.button("Refresh Document List"):
        with st.spinner("Refreshing..."):
            st.session_state.documents = list_documents()

    if "documents" not in st.session_state:
        st.session_state.documents = list_documents()

    documents = st.session_state.documents
    if documents:
        for doc in documents:
            st.sidebar.markdown(f"**{doc['filename']}**  \nID: `{doc['id']}`  \nUploaded: `{doc['upload_timestamp']}`")
        
        selected_file_id = st.sidebar.selectbox("Select a document to delete", options=[doc['id'] for doc in documents], format_func=lambda x: next(doc['filename'] for doc in documents if doc['id'] == x))
        if st.sidebar.button("Delete Selected Document"):
            with st.spinner("Deleting..."):
                delete_response = delete_document(selected_file_id)
                if delete_response:
                    st.sidebar.success(f"Document with ID {selected_file_id} deleted successfully.")
                    st.session_state.documents = list_documents()  # Refresh the list after deletion
                else:
                    st.sidebar.error(f"Failed to delete document with ID {selected_file_id}.")
