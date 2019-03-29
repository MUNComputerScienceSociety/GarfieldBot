import time
import logging
import threading
from typing import Callable, Union, Optional
from pprint import pformat
from functools import lru_cache
import shlex

from slackclient import SlackClient
from jigsaw import PluginLoader

from .Plugin import GarfieldPlugin
from .DataClasses import EVENTS, SlackEvent, HelloEvent, User, MessageEvent,\
    Channel


class Bot(object):
    """
    Main bot class that handles all incoming RTM events, and the making of API calls.
    """

    def __init__(self, token: str) -> None:
        """
        Initializes a new instance of GarfieldBot.

        :param token: The token to use to authenticate with Slack.
        """

        self.logger = logging.getLogger("GarfieldBot")

        self.logger.debug("Creating Slack client...")
        self.client = SlackClient(token)

        self._handlers = {}
        self._commands = {}

        # Discover and load all plugins from the plugins directory
        self.logger.debug("Loading plugins...")
        self.loader = PluginLoader(plugin_class=GarfieldPlugin)
        self.loader.load_manifests()
        self.loader.load_plugins(self)
        self.loader.enable_all_plugins()

        self.register_handler("hello", self._handle_hello)
        self.register_handler("message", self._handle_message)

    def _parse_event(self, data: dict):
        """
        Parses an incoming event, dispatching it to all listening plugins.

        :param data: The data from the RTM client.
        """
        if data["type"] not in EVENTS:
            self.logger.warning(f"Unknown event type '{data['type']}'.\nData:\n{pformat(data)}")
            event_class = EVENTS["unknown"]
        else:
            event_class = EVENTS[data["type"]]
        if data["type"] in self._handlers:
            event_instance = event_class(data)
            for handler in self._handlers[data["type"]]:
                threading.Thread(
                    target=handler,
                    args=(event_instance, )
                ).start()

    def _handle_hello(self, event: HelloEvent) -> None:
        """
        Handles an incoming hello event, logging that the bot has successfully connected.

        :param event: The event instance.
        """
        self.logger.info("GarfieldBot successfully connected to Slack.")

    def _handle_message(self, event: MessageEvent) -> None:
        """
        Handles incoming chat messages, logging them to console and dispatching commands.
        """
        user = self.get_user(event.user)
        channel = self.get_channel(event.channel)
        self.logger.info(f"{user.name if user is not None else 'GarfieldBot'} -> {channel.name}: {event.text}")

        if event.text.startswith("!"):
            self._dispatch_command(event)

    def _dispatch_command(self, event: MessageEvent) -> None:
        """
        Processes an incoming message event into a command, and runs the command.

        :param event: The incoming message event.
        """
        command_text = event.text[1:]
        command_name = command_text.split(" ")[0]
        if command_name in self._commands:
            args = shlex.split(command_text)
            threading.Thread(
                target=self._commands[command_name],
                args=(event, *(args[1:]))
            ).start()

    def register_handler(self, type: str, handler: Callable[[SlackEvent], None]) -> None:
        """
        Registers a handler for a certain event.

        :param type: The type of event to handle.
        :param handler: The function to be used to handle the event.
        """
        if type not in self._handlers:
            self._handlers[type] = [handler]
        else:
            self._handlers[type].append(handler)

    def register_command(self, name: str, handler: Callable[..., None]) -> None:
        """
        Registers a command and command handler.

        :param name: The name of the command.
        :param handler: The function to call when the command is ran.
        """
        self._commands[name] = handler

    @lru_cache()
    def get_user(self, id: str) -> Optional[User]:
        """
        Turns a Slack user ID into a user object.
        Last 128 users retrieved are cached, meaning updated user details may not be visible immediately.

        :param id: The user ID.
        :return: The user object.
        """
        user_data = self.client.api_call(
            "users.info",
            user=id
        )

        try:
            return User(user_data["user"])
        except KeyError:
            None

    @lru_cache()
    def get_channel(self, id: str) -> Optional[Channel]:
        """
        Turns a Slack user ID into a channel object.
        Last 128 channels retrieved are cached, meaning updated channel details may not be visible immediately.

        :param id: The channel ID.
        :return: The channel object.
        """
        channel_data = self.client.api_call(
            "conversations.info",
            channel=id
        )

        try:
            return Channel(channel_data["channel"])
        except KeyError:
            return None

    def send_message(self, channel: Union[Channel, str], text: str, **kwargs) -> None:
        """
        Sends a message to a given Slack channel.

        :param channel: Either the ID of the channel to send to, or a channel object.
        :param text: The text to send.
        :param kwargs: Any additional arguments to send.
        """
        if isinstance(channel, Channel):
            channel = channel.id

        self.client.api_call(
            "chat.postMessage",
            channel=channel,
            text=text,
            **kwargs
        )

    def start(self) -> None:
        """
        Starts this instance of GarfieldBot.
        """

        if self.client.rtm_connect():
            while self.client.server.connected:
                events = self.client.rtm_read()
                if events != []:
                    for event in events:
                        self._parse_event(event)

                time.sleep(0.5)
