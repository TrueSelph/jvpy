from __future__ import annotations
from jaclang import *
import math
import json
import yaml
import logging
import traceback
from typing import Any, Tuple
from logging import Logger
from action import Action
from jivas.agent.modules.agentlib.utils import Utils
from jivas.agent.action.interact_graph_walker import interact_graph_walker
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_core.vectorstores.base import VectorStore
from langchain_core.documents.base import Document
from langchain_openai import OpenAIEmbeddings
from langchain_openai import AzureOpenAIEmbeddings
from jivas.agent.modules.embeddings.jivas_embeddings import JivasEmbeddings

class VectorStoreAction(Action, Node):
    logger: static[Logger] = logging.getLogger(__name__)
    embedding_model_endpoint: str = field("")
    embedding_model_api_key: str = field("")
    embedding_model_api_version: str = field("")
    embedding_model_name: str = field("")
    embedding_model_provider: str = field("openai")

    def get_client(self) -> None:
        pass

    def get_collection(self, collection_name: str) -> None:
        pass

    def get_vectorstore(self) -> None:
        pass

    def load_text_document(
        self, filepath: str, chunk_size: int = 400, chunk_overlap: int = 0
    ) -> None:
        try:
            loader = TextLoader(filepath)
            documents = loader.load()
            text_splitter = CharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            docs = text_splitter.split_documents(documents)
            return self.add_documents(documents=docs)
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def import_knodes(self, data: list) -> bool:
        importing_error_message = ""
        if isinstance(data, str):
            try:
                knodes = json.loads(data)
            except json.JSONDecodeError as e:
                importing_error_message = f"Failed to import knode JSON, {e}"
            try:
                knodes = yaml.safe_load(data)
            except yaml.YAMLError as e:
                importing_error_message = f"Failed to import knode YAML, {e}"
        else:
            knodes = data
        try:
            failed = JacList([])
            successful = JacList([])
            self.logger.info(f"Importing {knodes} ...")
            for knode in knodes:
                if knode.get("id"):
                    metadatas = JacList([knode["metadata"]])
                    ids = self.add_texts(
                        texts=JacList([str(knode["text"])]),
                        metadatas=metadatas,
                        ids=JacList([knode["id"]]),
                    )
                else:
                    metadatas = JacList([knode["metadata"]])
                    ids = self.add_texts(
                        texts=JacList([str(knode["text"])]), metadatas=metadatas
                    )
                if not ids:
                    self.logger.error(
                        f"Failed to add text to vectorstore - {str(knode['text'][:50])}..."
                    )
                    failed.append(knode)
                else:
                    self.logger.info(
                        f"Added to vectorstore - [{ids}] {str(knode['text'][:50])}..."
                    )
                    successful.append(knode)
            if failed:
                self.logger.error(f"Failed to import {len(failed)} knodes")
                return False
            else:
                self.logger.info(f"Successfully imported {len(successful)} knodes")
                return True
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
            self.logger.error(importing_error_message)
            return False

    def export_knodes(
        self, as_json: bool = False, embeddings: bool = False, with_ids: bool = False
    ) -> str:
        try:
            if collection := self.get_collection(self.collection_name):
                excluded_fields = ""
                if with_ids:
                    if not embeddings:
                        excluded_fields = "vec"
                else:
                    excluded_fields = "id,vec"
                    if embeddings:
                        excluded_fields = "id"
                per_page = 250
                page = 1
                results = collection.documents.search(
                    {
                        "q": "*",
                        "per_page": per_page,
                        "page": page,
                        "exclude_fields": excluded_fields,
                    }
                )
                documents = JacList([])
                hits = results.get("hits", JacList([]))
                total = results.get("found", 0)
                for item in hits:
                    documents.append(item.get("document"))
                total_pages = math.ceil(total / per_page)
                for page in range(2, total_pages + 1):
                    results = collection.documents.search(
                        {
                            "q": "*",
                            "per_page": per_page,
                            "page": page,
                            "exclude_fields": excluded_fields,
                        }
                    )
                    hits = results.get("hits", JacList([]))
                    for item in hits:
                        documents.append(item.get("document"))
                if as_json:
                    return json.dumps(documents)
                else:
                    return Utils.yaml_dumps(documents)
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        try:
            return self.get_vectorstore().add_texts(
                texts=texts, metadatas=metadatas, ids=ids, **kwargs
            )
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def add_documents(self, documents: list[Document], **kwargs: Any) -> list[str]:
        try:
            return self.get_vectorstore().add_documents(documents=documents, **kwargs)
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def get_embedding_model(self) -> None:
        if self.embedding_model_provider == "openai":
            if self.embedding_model_name:
                return OpenAIEmbeddings(
                    model=self.embedding_model_name,
                    api_key=self.embedding_model_api_key,
                )
            return OpenAIEmbeddings(api_key=self.embedding_model_api_key)
        elif self.embedding_model_provider == "azure":
            if self.embedding_model_name:
                return AzureOpenAIEmbeddings(
                    azure_endpoint=self.embedding_model_endpoint,
                    model=self.embedding_model_name,
                    api_key=self.embedding_model_api_key,
                    open_api_version=self.embedding_model_api_version,
                )
            return AzureOpenAIEmbeddings(
                azure_endpoint=self.embedding_model_endpoint,
                api_key=self.embedding_model_api_key,
                open_api_version=self.embedding_model_api_version,
            )
        elif self.embedding_model_provider == "jivas":
            if self.embedding_model_name:
                return JivasEmbeddings(
                    base_url=self.embedding_model_endpoint,
                    api_key=self.embedding_model_api_key,
                    model=self.embedding_model_name,
                )
            return JivasEmbeddings(
                base_url=self.embedding_model_endpoint,
                api_key=self.embedding_model_api_key,
            )
        else:
            self.logger.error(
                f"Provider {self.embedding_model_provider} not supported for embedding model {self.embedding_model_name}"
            )
            return None

    def similarity_search(
        self, query: str, k: int = 10, filter: str | None = "", **kwargs: Any
    ) -> List[Document]:
        try:
            return self.get_vectorstore().similarity_search(
                query=query, k=k, filter=filter, **kwargs
            )
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def similarity_search_with_score(
        self, query: str, k: int = 10, filter: str | None = "", **kwargs: Any
    ) -> List[Tuple[Document, float]]:
        try:
            return self.get_vectorstore().similarity_search_with_score(
                query=query, k=k, filter=filter, **kwargs
            )
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def max_marginal_relevance_search(
        self,
        query: str,
        k: int = 10,
        fetch_k: int = 20,
        lamda_mult: float = 0.5,
        **kwargs: Any,
    ) -> List[Document, float]:
        try:
            return self.get_vectorstore().max_marginal_relevance_search(
                query=query, k=k, fetch_k=fetch_k, lamda_mult=lamda_mult, **kwargs
            )
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def vector_similarity_search(
        self, embedding: list[float], k: int = 10, **kwargs: Any
    ) -> List[Document]:
        try:
            return self.get_vectorstore().similarity_search_by_vector(
                embedding=embedding, k=k, **kwargs
            )
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def metadata_search(
        self, metadata: dict, k: int = 10, **kwargs: Any
    ) -> List[Document]:
        pass

    def list_documents(self, page: int = 1, per_page: int = 10) -> dict:
        pass

    def get_document(self, id: str) -> bool:
        pass

    def update_document(self, id: str, data: dict) -> bool:
        pass

    def delete_document(self, id: str) -> bool:
        pass

    def delete_collection(self) -> bool:
        pass

    def healthcheck(self) -> Union[bool, dict]:
        try:
            if not self.embedding_model_provider:
                return {
                    "status": False,
                    "message": "Embedding model provider not set",
                    "severity": "error",
                }
            embedded_texts = self.get_embedding_model().embed_documents(
                JacList(["this is a test"])
            )
            if not embedded_texts:
                return {
                    "status": False,
                    "message": "Embedding model not functional. Check your configuration",
                    "severity": "error",
                }
            if not self.get_vectorstore():
                return {
                    "status": False,
                    "message": "Vectorstore not configured",
                    "severity": "error",
                }
            return True
        except Exception as e:
            return False
