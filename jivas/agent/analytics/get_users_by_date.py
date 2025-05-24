from __future__ import annotations

import logging
import os
import traceback
from datetime import datetime, timedelta
from logging import Logger

from jac_cloud.core.architype import NodeAnchor
from jaclang import *

from jivas.agent.core.agent import Agent
from jivas.agent.core.agent_graph_walker import agent_graph_walker


class get_users_by_date(agent_graph_walker, Walker):
    start_date: str = field("")
    end_date: str = field("")
    timezone: str = field("UTC")
    logger: static[Logger] = logging.getLogger(__name__)

    class __specs__(Obj):
        private: static[bool] = False

    @with_entry
    def on_agent(self, here: Agent) -> None:
        start = datetime.strptime(
            f"{self.start_date}T00:00:00+00:00", "%Y-%m-%dT%H:%M:%S%z"
        )
        end = datetime.strptime(
            f"{self.end_date}T00:00:00+00:00", "%Y-%m-%dT%H:%M:%S%z"
        )
        end = end + timedelta(days=1) - timedelta(milliseconds=1)
        days = 1 if (end - start).days == 0 else (end - start).days
        try:
            collection = NodeAnchor.Collection.get_collection("interactions")
            pipeline = JacList(
                [
                    {
                        "$match": {
                            "agent_id": self.agent_id,
                            "time_stamp": {
                                "$gte": self.start_date,
                                "$lte": self.end_date,
                            },
                        }
                    },
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": (
                                        "%Y-%m-%dT00:00:00.000Z"
                                        if days > 1
                                        else "%Y-%m-%dT%H:00:00.000Z"
                                    ),
                                    "date": {
                                        "$dateFromString": {"dateString": "$time_stamp"}
                                    },
                                    "timezone": self.timezone,
                                }
                            },
                            "unique_users": {"$addToSet": "$response.session_id"},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "date": "$_id",
                            "count": {"$size": "$unique_users"},
                        }
                    },
                    {"$sort": {"date": 1}},
                ]
            )
            result = list(collection.aggregate(pipeline))
            total = sum([doc["count"] for doc in result])
            Jac.report({"total": total, "data": result})
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
