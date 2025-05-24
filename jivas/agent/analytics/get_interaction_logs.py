from __future__ import annotations
from jaclang import *
import logging
import traceback
import json
from logging import Logger
from datetime import datetime, timedelta
from jivas.agent.core.agent_graph_walker import agent_graph_walker
from jivas.agent.core.agent import Agent
from jac_cloud.core.architype import NodeAnchor

class get_interaction_logs(agent_graph_walker, Walker):
    start_date: str = field("")
    end_date: str = field("")
    session_id: str = field("")
    channel: str = field("")
    timezone: str = field("UTC")
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        try:
            start = datetime.strptime(
                f"{self.start_date}T00:00:00+00:00", "%Y-%m-%dT%H:%M:%S%z"
            )
            end = datetime.strptime(
                f"{self.end_date}T00:00:00+00:00", "%Y-%m-%dT%H:%M:%S%z"
            )
            end = end + timedelta(days=1) - timedelta(milliseconds=1)
            collection = NodeAnchor.Collection.get_collection("interactions")
            match_criteria = {
                "agent_id": self.agent_id,
                "time_stamp": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            }
            if self.session_id:
                match_criteria["session_id"] = self.session_id
            if self.channel:
                match_criteria["channel"] = self.channel
            pipeline = JacList(
                [{"$match": match_criteria}, {"$sort": {"time_stamp": 1}}]
            )
            result = list(collection.aggregate(pipeline))
            Jac.report(
                {
                    "total": len(result),
                    "data": json.loads(json.dumps(result, default=str)),
                }
            )
        except Exception as e:
            self.logger.error(
                f"An error occurred while fetching interaction logs: {traceback.format_exc()}"
            )
            Jac.report({"error": str(e)})
