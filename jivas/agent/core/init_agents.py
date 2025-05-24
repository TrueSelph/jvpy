from __future__ import annotations

import io
import logging
import traceback
from logging import Logger

import yaml
from jaclang import *

from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.agents import Agents
from jivas.agent.core.import_agent import import_agent
from jivas.agent.modules.agentlib.utils import jvdata_file_interface


class init_agents(agent_graph_walker, Walker):
    reporting: bool = field(False)
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False
        excluded: static[list] = ["agent_id"]

    @with_entry
    def on_agents(self, here: Agents) -> None:
        if agent_nodes := here.get_all():
            for agent_node in agent_nodes:
                try:
                    self.logger.info(f"initializing agent {agent_node.name}")
                    file_bytes = agent_node.get_file(
                        agent_node.descriptor
                    ) or jvdata_file_interface.get_file(agent_node.descriptor)
                    if not file_bytes:
                        self.logger.error(
                            f"agent descriptor not found: {agent_node.descriptor}"
                        )
                        continue
                    descriptor = ""
                    file = io.BytesIO(file_bytes)
                    descriptor = yaml.safe_load(file)
                    if descriptor:
                        here.spawn(
                            import_agent(
                                descriptor=descriptor, reporting=self.reporting
                            )
                        )
                except Exception as e:
                    self.logger.error(
                        f"an exception occurred, {traceback.format_exc()}"
                    )
