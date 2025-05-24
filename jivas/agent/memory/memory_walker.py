from __future__ import annotations

from jaclang import *

from jivas.agent.core.agent import Agent
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.memory.frame import Frame
from jivas.agent.memory.memory import Memory


class memory_walker(agent_graph_walker, Walker):
    session_id: str = field("")

    @with_entry
    def on_agent(self, here: Agent) -> None:
        self.visit(here.refs().filter(Memory, None))

    @with_entry
    def on_memory(self, here: Memory) -> None:
        self.visit(
            here.refs()
            .filter(Frame, None)
            .filter(None, lambda item: item.session_id == self.session_id)
        )
