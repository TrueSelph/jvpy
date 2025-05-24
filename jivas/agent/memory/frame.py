from __future__ import annotations
from jaclang import *
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
from jivas.agent.modules.agentlib.utils import Utils
from jivas.agent.memory.interaction import Interaction
from jivas.agent.memory.interaction_response import InteractionResponse, TextInteractionMessage
from jivas.agent.core.graph_node import GraphNode
from jivas.agent.action.interact_action import InteractAction
from jivas.agent.memory.tail import Tail
from jivas.agent.memory.advance import Advance
from jivas.agent.memory.retrace import Retrace

class Frame(GraphNode, Node):
    agent_id: str = field("")
    session_id: str = field(gen=lambda: str(uuid4()))
    label: str = field("")
    user_name: str = field("")
    created_on: str = field(gen=lambda: str(datetime.now(timezone.utc).isoformat()))
    last_interacted_on: str = field(
        gen=lambda: str(datetime.now(timezone.utc).isoformat())
    )
    variables: dict = field(gen=lambda: {})

    def __post_init__(self) -> None:
        super().__post_init__()
        self.protected_attrs += JacList(["agent_id"])

    def variable_get(self, key: str, default: Optional[Any] = None) -> Any:
        if variable := self.variables.get(key):
            return variable
        elif default:
            return default
        else:
            return None

    def variable_set(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def variable_del(self, key: str) -> None:
        if key in self.variables.keys():
            del self.variables[key]

    def get_last_interaction(self, retraces: int = 1) -> Interaction:
        return self.spawn(
            _get_interaction_by_retraces(retraces=retraces)
        ).interaction_node

    def is_first_interaction(self) -> bool:
        last_interaction = self.get_last_interaction()
        return "new_user" in last_interaction.context_data

    def set_resume_action(self, action_label: str) -> None:
        if last_interaction := self.get_last_interaction():
            last_interaction.context_data["resume_action"] = action_label

    def get_resume_action(self, last_interaction_node: Interaction) -> InteractAction:
        action_node = None
        if last_interaction_node:
            if "resume_action" in last_interaction_node.context_data:
                agent_node = self.get_agent()
                action_label = last_interaction_node.context_data["resume_action"]
                action_node = agent_node.get_action(action_label=action_label)
        return action_node

    def set_label(self, label: str) -> None:
        self.label = label

    def add_interaction(self, utterance: str, channel: str = "default") -> Interaction:
        last_interaction_node = self.get_last_interaction()
        interaction_node = Interaction(
            agent_id=self.agent_id,
            channel=channel,
            utterance=utterance,
            response=InteractionResponse(session_id=self.session_id).export(),
        )
        return self.insert_interaction(interaction_node, last_interaction_node)

    def add_unprompted_interaction(
        self, message: str, channel: str = "default"
    ) -> Interaction:
        last_interaction_node = self.get_last_interaction()
        interaction_node = Interaction(
            agent_id=self.agent_id,
            channel=channel,
            response=InteractionResponse(
                session_id=self.session_id,
                message=TextInteractionMessage(content=message).export(),
            ).export(),
        )
        interaction_node.close()
        return self.insert_interaction(interaction_node, last_interaction_node)

    def insert_interaction(
        self, interaction_node: Interaction, last_interaction_node: Interaction = None
    ) -> Interaction:
        if not last_interaction_node and (not self.refs(Advance)):
            self.connect(interaction_node, edge=Advance)
            interaction_node.connect(self, edge=Retrace)
            self.connect(interaction_node, edge=Tail)
            interaction_node.context_data["new_user"] = True
        elif self.refs(Tail):
            self.disconnect(self.refs(Tail), edge=Tail)
            self.connect(interaction_node, edge=Tail)
            last_interaction_node.attach_interaction(interaction_node)
        self.last_interacted_on = str(datetime.now(timezone.utc).isoformat())
        return interaction_node

    def get_transcript_statements(
        self,
        interactions: int = 10,
        max_statement_length: int = 0,
        with_events: bool = False,
    ) -> list[dict]:
        return self.spawn(
            _get_transcript_statements(
                interactions, max_statement_length, with_events=with_events
            )
        ).statements

    def get_transcript(
        self,
        interactions: int = 10,
        max_statement_length: int = 0,
        with_events: bool = False,
    ) -> str:
        transcript = ""
        statements = self.get_transcript_statements(
            interactions, max_statement_length, with_events=with_events
        )
        for item in statements:
            key = next(iter(item))
            value = item[key]
            transcript += f"{key} : {value} \\n"
        return transcript

    def get_interactions(self) -> list:
        return self.spawn(_get_interactions()).interactions

    def get_agent(self) -> None:
        return jobj(id=self.agent_id)

    def prune_interactions(self, frame_size: int) -> None:
        self.spawn(_prune_interactions(frame_size=frame_size))

    def refresh_interactions(self) -> None:
        self.prune_interactions(frame_size=1)

    def get_user_name(self, full: bool = False) -> None:
        if self.user_name and full:
            return self.user_name
        elif self.user_name:
            return Utils.extract_first_name(self.user_name)
        else:
            return "user"

    def set_user_name(self, user_name: str) -> None:
        if user_name:
            self.user_name = user_name


class _get_transcript_statements(Walker):
    interactions: int = field(1)
    max_statement_length: int = field(0)
    statements: list = field(gen=lambda: JacList([]))
    last_interaction: Interaction = field(None)
    retrace_count: int = field(0)
    with_events: bool = field(False)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_frame(self, here: Frame) -> None:
        last_interaction = here.get_last_interaction()
        self.visit(last_interaction)

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        if here == self.last_interaction:
            if not self.visit(here.refs(Retrace).filter(Interaction, None)):
                return self.disengage()
        elif self.retrace_count < self.interactions:
            ai_statement = ""
            human_statement = ""
            if here.events and self.with_events:
                for event in here.events:
                    self.statements.append({"ai": f"event: {event}"})
            if here.has_response():
                content = here.get_message().get_content()
                if type(content) == list:
                    for item in content:
                        ai_statement = item["content"]
                        if ai_statement:
                            ai_statement = self.chunk_message(message=ai_statement)
                            self.statements.append({"ai": ai_statement})
                else:
                    ai_statement = self.chunk_message(message=content)
                    self.statements.append({"ai": ai_statement})
            if here.utterance:
                human_statement = Utils.escape_string(here.utterance)
                human_statement = self.chunk_message(message=human_statement)
                self.statements.append({"human": human_statement})
            self.retrace_count += 1
            self.visit(here.refs(Retrace).filter(Interaction, None))

    def chunk_message(self, message: str) -> str:
        if self.max_statement_length > 0:
            message_chunks = Utils.chunk_long_message(
                message=message,
                max_length=self.max_statement_length,
                chunk_length=self.max_statement_length,
            )
            if len(message_chunks) > 1:
                message = message_chunks[0]
        return message

    @with_exit
    def on_exit(self, here) -> None:
        self.statements.reverse()


class _get_interactions(Walker):
    interactions: list = field(gen=lambda: JacList([]))

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_frame(self, here: Frame) -> None:
        self.visit(here.refs(Advance).filter(Interaction, None))

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        self.interactions.append(here)
        self.visit(here.refs(Advance).filter(Interaction, None))


class _get_interaction_by_retraces(Walker):
    retraces: int = field(1)
    walks: int = field(0)
    interaction_node: Interaction = field(None)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_frame(self, here: Frame) -> None:
        self.visit(here.refs(Tail).filter(Interaction, None))

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        self.walks += 1
        if self.retraces == self.walks:
            self.interaction_node = here
            return self.disengage()
        self.visit(here.refs(Retrace).filter(Interaction, None))


class _prune_interactions(Walker):
    frame_size: int = field(1)
    frame_node: Frame = field(None)
    interaction_head: Interaction = field(None)
    retraces: int = field(0)

    class __specs__(Obj):
        private: static[bool] = True

    @with_entry
    def on_frame(self, here: Frame) -> None:
        self.frame_node = here
        if self.interaction_head:
            here.connect(self.interaction_head, edge=Advance)
        else:
            self.visit(here.get_last_interaction())

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        self.retraces += 1
        if self.retraces == self.frame_size and here.refs(Retrace).filter(
            Interaction, None
        ):
            self.interaction_head = here
            self.visit(here.refs(Retrace).filter(Interaction, None))
            here.disconnect(here.refs(Retrace).filter(Interaction, None))
            if not here.refs(Retrace).filter(Frame, None):
                here.connect(self.frame_node, edge=Retrace)
        elif self.retraces > self.frame_size:
            if not self.visit(here.refs(Retrace).filter(Interaction, None)):
                Jac.destroy(here)
        else:
            self.visit(here.refs(Retrace).filter(Interaction, None))
