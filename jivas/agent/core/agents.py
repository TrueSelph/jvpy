from __future__ import annotations
from jaclang import *
import logging
from logging import Logger
from jivas.agent.modules.agentlib.utils import Utils
from jivas.agent.core.graph_node import GraphNode
from jivas.agent.core.purge import purge

class Agents(GraphNode, Node):
    logger: static[Logger] = logging.getLogger(__name__)

    def get_all(self) -> list:
        return self.refs()

    def get_by_name(self, name: str) -> None:
        return Utils.node_obj(self.refs().filter(None, lambda item: item.name == name))

    def get_by_id(self, id: str) -> None:
        return Utils.node_obj(self.refs().filter(None, lambda item: item.id == id))

    def delete(self, id: str) -> None:
        if agent_node := self.get_by_id(id):
            agent_node.get_actions().deregister_actions()
            agent_node.spawn(purge())
            return agent_node
        return None

    def delete_all(self) -> None:
        agent_nodes = JacList([])
        for agent_node in self.get_all():
            agent_nodes.append(self.delete(agent_node.id))
        return agent_nodes
