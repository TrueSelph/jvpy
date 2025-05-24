from __future__ import annotations

from datetime import datetime, timezone

from jaclang import *

from jivas.agent.core.graph_node import GraphNode
from jivas.agent.memory.advance import Advance
from jivas.agent.memory.data import Data
from jivas.agent.memory.interaction_response import (
    InteractionResponse,
    TextInteractionMessage,
)
from jivas.agent.memory.retrace import Retrace


class Interaction(GraphNode, Node):

    agent_id: str = field("")
    channel: str = field("")
    utterance: str = field("")
    tokens: int = field(0)
    time_stamp: str = field(gen=lambda: str(datetime.now(timezone.utc).isoformat()))
    trail: list = field(gen=lambda: [])
    intents: list = field(gen=lambda: [])
    functions: dict = field(gen=lambda: {})
    directives: list = field(gen=lambda: [])
    context_data: dict = field(gen=lambda: {})
    events: list = field(gen=lambda: [])
    response: dict = field(gen=lambda: {})
    data: dict = field(gen=lambda: {})
    closed: bool = field(False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.protected_attrs += ["agent_id"]

    def attach_interaction(self, interaction_node: Interaction) -> None:
        self.connect(interaction_node, edge=Advance)
        interaction_node.connect(self, edge=Retrace)

    def is_new_user(self) -> bool:
        return self.context_data.get("new_user", False)

    def set_text_message(self, message: str) -> None:
        self.set_message(TextInteractionMessage(content=message))

    def set_message(self, message: InteractionMessage) -> None:
        interaction_response = self.get_response() or InteractionResponse()
        interaction_response.set_message(message)
        self.response = interaction_response.export()

    def get_message(self) -> InteractionMessage:
        if interaction_response := self.get_response():
            return interaction_response.get_message()
        return None

    def get_response(self) -> InteractionResponse:
        interaction_response = None
        if self.response:
            interaction_response = InteractionResponse()
            interaction_response.load(self.response)
        return interaction_response

    def has_response(self) -> bool:
        if self.get_message():
            return True
        return False

    def has_intent(self, intent: str) -> None:
        return intent in self.intents

    def set_data_item(self, label: str, meta: dict, content: any) -> None:
        if data_obj := self.get_data_item(label):
            if type(meta) == dict:
                data_obj.meta = meta
            if content:
                data_obj.content = content
            self.data[label] = data_obj.export()
        else:
            data_obj = Data(label=label, meta=meta, content=content)
            self.data[label] = data_obj.export()

    def get_data_item(self, label: str) -> Data:
        if data_item := self.data.get(label):
            data_obj = Data()
            data_obj.load(data_item)
            return data_obj
        return None

    def get_data_items(self) -> list:
        return self.data

    def add_directive(self, directive: str) -> None:
        self.directives.append(directive)

    def get_directives(self) -> list:
        return self.directives

    def add_intent(self, intent: str) -> None:
        if intent not in self.intents:
            self.intents.append(intent)

    def add_event(self, event: str) -> None:
        self.events.append(event)

    def get_events(self) -> list:
        return self.events

    def add_tokens(self, tokens: int) -> None:
        self.tokens += tokens
        if response := self.get_response():
            response.set_tokens(self.tokens)
            self.response = response.export()

    def get_intents(self) -> list:
        return self.intents

    def add_function(self, action_label: str, function: dict) -> None:
        if self.functions.get(action_label, None):
            self.functions[action_label].append(function)
        else:
            self.functions[action_label] = [function]
            self.add_intent(action_label)

    def get_functions(self, action_label: str) -> list:
        return self.functions.get(action_label, [])

    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True
