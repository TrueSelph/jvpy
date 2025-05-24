from __future__ import annotations
from jaclang import *
import json
import logging
from typing import Optional, Union
from logging import Logger
from jivas.agent.action.interact_action import InteractAction
from jivas.agent.action.interact_graph_walker import interact_graph_walker


class RetrievalInteractAction(InteractAction, Node):
    logger: static[Logger] = logging.getLogger(__name__)
    directive: str = field(
        "\nUse CONTEXT as your knowledge base, intelligently assess the user question, review CONTEXT for context and finally produce an informative and accurate response.\nDo not include any information outside of the CONTEXT. If relevant content is not available in CONTEXT, advise the user that you do not have the relevant information at this time.\n\nCONTEXT:\n{context}\n\n\n"
    )
    ref_directive: str = field(
        "\nUse CONTEXT as your knowledge base, intelligently assess the user question and perform the following tasks:\na. Review 'content' in CONTEXT for the appropriate context to produce an accurate answer. Do not include any information outside of the CONTEXT.\nb. For each applicable item in CONTEXT, include a formatted list of unique content references taken from REF_FIELDS under 'metadata' in CONTEXT based on REF_FORMAT.\nc. If relevant content is not available in CONTEXT, advise the user that you do not have the relevant information at this time.\n\nREF_FIELDS:\n{ref_fields}\n\nREF_FORMAT:\n{ref_format}\n\nCONTEXT:\n{context}\n\n"
    )
    null_directive: str = field(
        "No context information was retrieved based on user utterance. If the user utterance is a question which relates to your knowledge, advise them that you do not have the relevant information at this time to answer their question.\n"
    )
    query_completion_prompt: str = field(
        "\nBased on the conversation history, perform the following tasks:\n\n1. **Understand the User's Intent**:\n    - Analyze the user's message to determine their intent.\n    - If the message is a **query** (a question or request for information), proceed to step 2.\n    - If the message is **small talk**, a **greeting**, or a **statement** that does not seek additional information, proceed to step 3.\n2. **Refine the User's Query**:\n    - Rephrase and enhance the user's query by incorporating relevant details from the conversation history.\n    - Make the query more explicit and detailed to clearly convey the user's request.\n    - Focus solely on refining the query, without providing an answer or additional information.\n3. **Provide the Final Message**:\n    - Output **only** the refined query from step 2 or the original user message if no refinement was necessary.\n    - Do not include any answers, explanations, or additional commentary.\n\n**Note:**\nYour task is to **craft a refined query** when applicable, not to answer the query.\nEnsure that the final output is either the refined query or the original message, with no extra content.\n\n"
    )
    k: int = field(3)
    score_threshold: float = field(0.3)
    mmr: bool = field(False)
    metadata: bool = field(False)
    references: bool = field(False)
    metadata_ref_fields: str = field("source, filename, page")
    metadata_ref_format: str = field(
        "( [filename](source), pp. <page>; [filename](source), pp. <page>; ... )"
    )
    vector_store_action: str = field("")
    history_size: int = field(3)
    max_statement_length: int = field(400)
    model_action: str = field("LangChainModelAction")
    model_name: str = field("gpt-4o")
    model_temperature: float = field(0.2)
    model_max_tokens: int = field(10000)

    def on_register(self) -> None:
        if not self.vector_store_action:
            self.vector_store_action = self.get_agent().vector_store_action

    def touch(self, visitor: interact_graph_walker) -> bool:
        if visitor.utterance:
            return True

    def execute(self, visitor: interact_graph_walker) -> None:
        if self.references:
            if not self.metadata_ref_fields:
                self.logger.warning(
                    "References are enabled, but metadata_ref_fields is not set. Turning 'references' off."
                )
                self.references = False
            elif not self.metadata:
                self.logger.warning(
                    "References are enabled, but metadata is not. Setting metadata to True."
                )
                self.metadata = True
        if not (query := self.prepare_query(visitor)):
            query = visitor.utterance
        visitor.interaction_node.context_data["RetrievalInteractAction_query"] = query
        visitor.utterance = query
        if context_data := self.retrieve_context(query):
            context_directive = None
            visitor.interaction_node.context_data["RetrievalInteractAction_context"] = (
                context_data
            )
            context_json = json.dumps(context_data)
            if self.references and self.metadata_ref_fields and self.metadata:
                context_directive = self.ref_directive.format(
                    context=context_json,
                    ref_fields=self.metadata_ref_fields,
                    ref_format=self.metadata_ref_format,
                )
            else:
                context_directive = self.directive.format(context=context_json)
            visitor.interaction_node.add_directive(directive=context_directive)
        else:
            directives = visitor.interaction_node.get_directives()
            if not directives:
                visitor.interaction_node.add_directive(directive=self.null_directive)

    def prepare_query(self, visitor: interact_graph_walker) -> str:
        query = None
        if statements := visitor.frame_node.get_transcript_statements(
            interactions=self.history_size,
            max_statement_length=self.max_statement_length,
        ):
            prompt_messages = JacList([])
            prompt_messages.extend(statements)
            prompt_messages.extend(JacList([{"system": self.query_completion_prompt}]))
            result = None
            if model_action := self.get_agent().get_action(
                action_label=self.model_action
            ):
                if model_action_result := model_action.call_model(
                    prompt_messages=prompt_messages,
                    prompt_variables={},
                    kwargs={
                        "model_name": self.model_name,
                        "model_temperature": self.model_temperature,
                        "model_max_tokens": self.model_max_tokens,
                    },
                    interaction_node=visitor.interaction_node,
                ):
                    query = model_action_result.get_result()
        return query

    def retrieve_context(self, query: str, filter: Optional[str] = "") -> list:
        context_data = JacList([])
        if vector_store_action := self.get_agent().get_action(
            action_label=self.vector_store_action
        ):
            if self.mmr:
                if documents := vector_store_action.max_marginal_relevance_search(
                    query=query, k=self.k
                ):
                    for doc in documents:
                        context_item = {"content": doc.page_content}
                        if self.metadata:
                            context_item["metadata"] = doc.metadata
                        context_data.append(context_item)
                    if context_data:
                        return json.dumps(context_data)
            elif (
                documents_and_score := vector_store_action.similarity_search_with_score(
                    query=query, k=self.k, filter=filter
                )
            ):
                for doc, score in documents_and_score:
                    if score <= self.score_threshold:
                        context_item = {"content": doc.page_content}
                        if self.metadata:
                            context_item["metadata"] = doc.metadata
                        context_data.append(context_item)
        return context_data

    def healthcheck(self) -> Union[bool, dict]:
        vector_store_action = self.get_agent().get_action(
            action_label=self.vector_store_action
        )
        if not vector_store_action:
            return {
                "status": False,
                "message": "Unable to find a valid vector store action. Check your configuration and try again.",
                "severity": "error",
            }
        return True
