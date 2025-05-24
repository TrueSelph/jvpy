from __future__ import annotations
from jaclang import *
import os
import uuid
import base64
import logging
import traceback
from typing import Union
from logging import Logger
from jivas.agent.action.action import Action

class TTSAction(Action, Node):
    logger: static[Logger] = logging.getLogger(__name__)
    api_key: str = field("")
    model: str = field("")

    def invoke(self, text: str, as_base64: bool = False, as_url: bool = False) -> None:
        audio = None
        return self.get_audio_as(audio, as_base64, as_url)

    def get_audio_as(
        self, audio: bytes, as_base64: bool = False, as_url: bool = False
    ) -> None:
        if not audio:
            return None
        try:
            if as_base64:
                return base64.b64encode(audio).decode("utf-8")
            output_file_name = f"{str(uuid.uuid4())}.mp3"
            output_file_path = f"{os.environ.get('JIVAS_FILES_ROOT_PATH', '.files')}/tts/{output_file_name}"
            self.get_agent().save_file("tts/" + output_file_name, audio)
            if as_url:
                return self.get_agent().get_file_url("tts/" + output_file_name)
            return os.path.abspath(output_file_path)
        except Exception as e:
            self.logger.error(f"an exception occurred, {traceback.format_exc()}")
        return None

    def healthcheck(self) -> Union[bool, dict]:
        if not self.api_key:
            return {
                "status": False,
                "message": "API key is not set.",
                "severity": "error",
            }
        return True
