from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document


class TinyEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), float(sum(map(ord, text)) % 997)]


def test_chroma_persistence_and_metadata_filters(tmp_path):
    persist_directory = str(tmp_path / "chroma")
    embeddings = TinyEmbeddings()
    store = Chroma(
        collection_name="test_hr_policies",
        persist_directory=persist_directory,
        embedding_function=embeddings,
    )
    store.add_documents(
        [
            Document(
                page_content="Current employee leave policy",
                metadata={"document_id": "leave", "version": 2},
            ),
            Document(
                page_content="Administrator-only draft",
                metadata={"document_id": "draft", "version": 1},
            ),
        ],
        ids=["current-leave", "private-draft"],
    )

    reopened = Chroma(
        collection_name="test_hr_policies",
        persist_directory=persist_directory,
        embedding_function=embeddings,
    )
    results = reopened.similarity_search(
        "leave policy",
        k=4,
        filter={
            "$and": [
                {"document_id": {"$eq": "leave"}},
                {"version": {"$eq": 2}},
            ]
        },
    )
    assert [document.page_content for document in results] == [
        "Current employee leave policy"
    ]
