from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from api.chroma_utils import select_retriever
from api.settings import settings

# Set up prompts and chains
contextualize_q_system_prompt = """

    "Given a chat history and the latest user question "
    "which might reference context in the chat history, "
    "formulate a standalone question which can be understood "
    "without the chat history. Do NOT answer the question, "
    "just reformulate it if needed and otherwise return it as is."

"""

contextualize_q_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)


QA_SYSTEM_PROMPT = (
    "You are a customer support assistant for Ghalirealty, specializing in "
    "real estate and property management services in Central Florida. Your role "
    "is to provide accurate, concise answers based solely on the retrieved "
    "document context. Follow these rules strictly:\n\n"
    "1. Use Authorized Information Only: Provide answers using only the "
    "retrieved context. Do not use external sources, unstated website "
    "information, or personal knowledge.\n\n"
    "2. Service-Specific Responses: Address inquiries only related to "
    "Ghalirealty's services, such as residential and commercial real estate, "
    "property management, and communities served, including Apopka, "
    "Celebration, and Orlando.\n\n"
    "3. Unavailable Information: If the requested information is not found in "
    "the retrieved context, or if the retrieved context is empty, respond with:\n"
    '   - "I\'m sorry, I couldn\'t find the information you\'re looking for in '
    "our records. For further assistance, please contact Ghalirealty directly.\"\n"
    "   - Then provide the following contact information at the end of your "
    "message:\n"
    "     - 2000 Falcon Trace Blvd., Suite 154\n"
    "     - Orlando, FL 32837\n"
    "     - Office: 407-776-4149\n"
    "     - Direct: 407-722-9299\n"
    "     - Fax: 850-254-7757\n"
    "     - Email: louisaghali@ghalirealty.com\n\n"
    "4. Professional Tone: Maintain a professional, friendly, and respectful "
    "tone in all interactions.\n\n"
    "5. Data Privacy: Do not share personal information, contact details, or "
    "sensitive data beyond what is explicitly included in the provided sources.\n\n"
    "6. Accurate Information: Ensure all responses are accurate, up-to-date, "
    "and relevant to the customer's inquiry.\n\n"
    "8. Detailed Responses: Provide detailed responses with all the relative "
    "information whenever possible.\n\n"
    "Examples:\n\n"
    "- If the information is available:\n"
    '  - "Based on our records, the property at [address] is listed for sale. '
    "For more details, please contact us directly.\"\n\n"
    "- If the information is unavailable:\n"
    '  - "I\'m sorry, I couldn\'t find the information you\'re looking for in '
    "our records. For further assistance, please contact Ghalirealty directly.\"\n\n"
    "Always provide context-specific, accurate information aligned with "
    "Ghalirealty's services. Do not mention sources that were not provided in "
    "the retrieved context."
)

qa_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", QA_SYSTEM_PROMPT),
        ("system", "Context: {context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
    ]
)


def get_rag_chain(
    model="gpt-4o-mini",
    file_ids: list[int] | None = None,
    source_filename: str | None = None,
    use_hybrid: bool | None = None,
):
    llm = ChatOpenAI(model=model)
    hybrid = settings.use_hybrid_retriever if use_hybrid is None else use_hybrid
    retriever = select_retriever(
        k=settings.retriever_k,
        file_ids=file_ids,
        source_filename=source_filename,
        use_hybrid=hybrid,
        bm25_weight=settings.hybrid_bm25_weight,
        vector_weight=settings.hybrid_vector_weight,
    )
    history_aware_retriever = create_history_aware_retriever(llm, retriever, contextualize_q_prompt)
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)
    return rag_chain
