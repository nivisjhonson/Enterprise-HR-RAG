from __future__ import annotations

from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import Settings
from src import database
from src.citations import has_invalid_citations, retain_valid_citations
from src.prompts import GENERAL_HR_PROMPT, SYSTEM_PROMPT
from src.retriever import retrieve_with_sources

GENERAL_HR_NOTICE = "General HR guidance (not your organization's policy):"
INSUFFICIENT_EVIDENCE = (
    "I couldn't find sufficient information about this question in the available "
    "HR documents. Please contact your HR department for clarification."
)


def _generate_response(settings: Settings, prompt: str) -> str:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not configured. Add it to the local .env file to generate answers."
        )
    model = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=settings.google_api_key,
        temperature=1,
        timeout=30,
        max_retries=2,
    )
    response = model.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = "\n".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The language model returned an empty response.")
    return content.strip()


def answer_question(
    settings: Settings,
    store: Any,
    question: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    if database.document_statistics(settings)["indexed_documents"] == 0:
        prompt = GENERAL_HR_PROMPT.format(question=question.strip())
        answer = _generate_response(settings, prompt)
        if not answer.casefold().startswith(GENERAL_HR_NOTICE.casefold()):
            answer = f"{GENERAL_HR_NOTICE}\n\n{answer}"
        return {"answer": answer, "sources": []}

    documents, sources = retrieve_with_sources(settings, store, question, user)
    if not documents:
        return {"answer": INSUFFICIENT_EVIDENCE, "sources": []}

    passages = []
    for document, source in zip(documents, sources):
        page_suffix = (
            f", page {source['page_number']}" if source["page_number"] else ""
        )
        passages.append(
            f"[{source['label']}] {source['filename']}{page_suffix}\n"
            f"{document.page_content}"
        )
    context = "\n\n".join(passages)
    prompt = SYSTEM_PROMPT.format(question=question.strip(), context=context)
    content = _generate_response(settings, prompt)
    if has_invalid_citations(content, sources):
        return {"answer": INSUFFICIENT_EVIDENCE, "sources": []}
    answer, cited_sources = retain_valid_citations(content, sources)
    if not answer or not cited_sources:
        return {"answer": INSUFFICIENT_EVIDENCE, "sources": []}
    return {"answer": answer, "sources": cited_sources}
