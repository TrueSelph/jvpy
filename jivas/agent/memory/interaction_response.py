from __future__ import annotations

from enum import Enum, auto, unique
from typing import Any

from jaclang import *

from jivas.agent.modules.agentlib.utils import Utils


@unique
class MessageType(Enum):
    TEXT = "TEXT"
    MEDIA = "MEDIA"
    MULTI = "MULTI"
    SILENCE = "SILENCE"


class InteractionMessage(Obj):
    message_type: str = field(None)
    content: Any = field(None)
    meta: dict = field(gen=lambda: {})

    def load(self, data: dict) -> None:
        if data and isinstance(data, dict):
            for attr in data.keys():
                if hasattr(self, attr):
                    setattr(self, attr, data[attr])

    def get_type(self) -> str:
        return self.message_type

    def set_meta(self, key: str, value: any) -> None:
        self.meta[key] = value

    def get_meta(self, key: str) -> None:
        return self.meta.get(key, None)

    def get_content(self) -> None:
        return self.content

    def has_content(self) -> bool:
        if self.content:
            return True
        return False

    def export(self, ignore_keys: list = JacList(["__jac__"])) -> None:
        node_export = Utils.export_to_dict(self, ignore_keys)
        return node_export


class SilentInteractionMessage(InteractionMessage, Obj):
    message_type: str = field(gen=lambda: MessageType.SILENCE.value)
    content: str = field("...")


class TextInteractionMessage(InteractionMessage, Obj):
    message_type: str = field(gen=lambda: MessageType.TEXT.value)
    content: str = field("")


class MediaInteractionMessage(InteractionMessage, Obj):
    message_type: str = field(gen=lambda: MessageType.MEDIA.value)
    mime: str = field("")
    data: Any = field(None)
    content: str = field("")

    def has_content(self) -> bool:
        if self.data:
            return True
        return False


class MultiInteractionMessage(InteractionMessage, Obj):
    message_type: str = field(gen=lambda: MessageType.MULTI.value)
    content: list[dict] = field(gen=lambda: JacList([]))

    def load(self, data: dict) -> None:
        if data:
            for attr in data.keys():
                if hasattr(self, attr):
                    setattr(self, attr, data[attr])

    def add_interaction_message(self, message: InteractionMessage) -> None:
        if not isinstance(message, MultiInteractionMessage):
            self.content.append(message.export())

    def clear_interaction_messages(self) -> None:
        self.content = JacList([])

    def has_content(self) -> bool:
        if type(self.content) == list:
            if len(self.content) > 0:
                return True
        return False

    def get_content(self) -> None:
        content = ""
        for content_item in self.content:
            content = f"{content} \\n {content_item.get('content')}"
        return content

    def get_content_items(self) -> None:
        content_items = JacList([])
        if self.content:
            for content_item in self.content:
                message = SilentInteractionMessage()
                if content_item.get("message_type") == MessageType.MULTI.value:
                    message = MultiInteractionMessage()
                elif content_item.get("message_type") == MessageType.MEDIA.value:
                    message = MediaInteractionMessage()
                elif content_item.get("message_type") == MessageType.TEXT.value:
                    message = TextInteractionMessage()
                message.load(content_item)
                content_items.append(message)
        return content_items


class InteractionResponse(Obj):
    session_id: str = field("")
    message_type: str = field(gen=lambda: MessageType.TEXT.value)
    message: dict = field(gen=lambda: {})
    tokens: int = field(0)

    def load(self, data: dict) -> None:
        if data:
            for attr in data.keys():
                if hasattr(self, attr):
                    setattr(self, attr, data[attr])

    def set_message(self, message: InteractionMessage) -> None:
        if message:
            self.message = message.export()
            self.message_type = message.get_type()

    def set_tokens(self, tokens: int) -> None:
        self.tokens = tokens

    def get_type(self) -> None:
        return self.message_type

    def get_message(self) -> InteractionMessage:
        message = None
        if self.message:
            if self.message_type == MessageType.MULTI.value:
                message = MultiInteractionMessage()
            elif self.message_type == MessageType.MEDIA.value:
                message = MediaInteractionMessage()
            elif self.message_type == MessageType.TEXT.value:
                message = TextInteractionMessage()
            else:
                message = SilentInteractionMessage()
            message.load(self.message)
        return message

    def export(self, ignore_keys: list = JacList(["__jac__"])) -> None:
        node_export = Utils.export_to_dict(self, ignore_keys)
        return node_export
