from __future__ import annotations
from jaclang import *
import logging
from typing import Union
from logging import Logger
from jivas.agent.action.action import Action

class STTAction(Action, Node):
    logger: static[Logger] = logging.getLogger(__name__)
    api_key: str = field("")
    model: str = field("")

    def invoke(self, audio_url: str) -> None:
        pass

    def invoke_base64(self, audio_base64: str, audio_type: str = "audio/mp3") -> None:
        pass

    def healthcheck(self) -> Union[bool, dict]:
        if not self.api_key:
            return {
                "status": False,
                "message": "API key is not set.",
                "severity": "error",
            }
        return True
