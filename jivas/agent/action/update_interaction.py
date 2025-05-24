from __future__ import annotations

import logging
from logging import Logger

from jac_cloud.core.architype import NodeAnchor
from jaclang import *

from jivas.agent.core.graph_walker import graph_walker
from jivas.agent.memory.interaction import Interaction


class update_interaction(graph_walker, Walker):
    logger: static[Logger] = logging.getLogger(__name__)
    interaction_data: dict = field(gen=lambda: {})

    class __specs__(Obj):
        auth: static[bool] = True
        private: static[bool] = False

    @with_entry
    def on_interaction(self, here: Interaction) -> None:
        if not self.interaction_data:
            self.logger.error("no interaction data")
            return
        here.update(data=self.interaction_data)
        here.close()
