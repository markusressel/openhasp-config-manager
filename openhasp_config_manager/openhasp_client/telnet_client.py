import asyncio
import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator

from telnetlib3 import TelnetTerminalClient, open_connection, telnet_client_shell, TelnetWriterUnicode

_CONNECT_TIMEOUT = 5
_LOGIN_TIMEOUT = 10


class OpenHaspTelnetClient:
    def __init__(self, host: str, port: int = 23, baudrate: int = 115200, user: str = "admin", password: str = "admin"):
        self._host = host
        self._port = port
        self._baudrate = baudrate
        self._username = user
        self._password = password

    async def shell(self):
        async def _shell(reader, writer):
            while True:
                outp = await reader.read(1024)

                if not outp:
                    # End of File
                    break

                if "Username:" in outp:
                    # reply all questions with 'y'.
                    writer.write(f"{self._username}\n")
                elif "Password:" in outp:
                    writer.write(f"{self._password}\n")
                    break

            # switch over to interactive shell after automatic login
            await telnet_client_shell(reader, writer)

        reader, writer = await open_connection(
            host=self._host,
            port=self._port,
            tspeed=(self._baudrate, self._baudrate),
            shell=_shell,
            client_factory=TelnetTerminalClient,
        )

        await writer.protocol.waiter_closed

    @asynccontextmanager
    async def log_connection(self) -> AsyncIterator[AsyncIterator[str]]:
        """
        Connects to the telnet server of the plate and logs in.

        Usage: `async with client.log_connection() as chunks: async for chunk in chunks: ...`, where the chunks are what the plate
        sends, see `openhasp_client.logs` for what to do with them. The connection is closed when the block ends.
        :raises PermissionError: if the plate doesn't accept the user and password
        :raises ConnectionError: if the connection is closed while logging in
        """
        reader, writer = await asyncio.wait_for(
            open_connection(host=self._host, port=self._port, encoding="utf8"), _CONNECT_TIMEOUT
        )
        try:
            self._enable_keepalive(writer)
            rest = await asyncio.wait_for(self._login(reader, writer), _LOGIN_TIMEOUT)
            yield self._read_chunks(reader, rest)
        finally:
            writer.close()

    async def _login(self, reader, writer) -> str:
        """:return: what the plate sent after the login, which is already part of the log"""
        buffer = ""
        user_sent = password_sent = False
        while True:
            chunk = await reader.read(2048)
            if not chunk:
                raise ConnectionError(
                    "The plate closed the connection while logging in (it only allows one telnet connection at a time)"
                )
            buffer += chunk
            if "Prompt >" in buffer:
                # the banner is followed by the prompt, and then the log
                return buffer.split("Prompt >", 1)[1]
            if "Username:" in buffer:
                if user_sent:
                    raise PermissionError("The plate didn't accept the user and password of the config (http: user, password)")
                user_sent = True
                buffer = buffer.split("Username:", 1)[1]
                writer.write(f"{self._username}\r\n")
            elif "Password:" in buffer and not password_sent:
                password_sent = True
                buffer = buffer.split("Password:", 1)[1]
                writer.write(f"{self._password}\r\n")

    @staticmethod
    async def _read_chunks(reader, first: str) -> AsyncIterator[str]:
        if first:
            yield first
        while True:
            chunk = await reader.read(2048)
            if not chunk:
                return
            yield chunk

    @staticmethod
    def _enable_keepalive(writer):
        """Makes a plate that disappeared without closing the connection (power loss) show up as a lost connection."""
        sock = writer.get_extra_info("socket")
        if sock is None:
            return
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for option, value in (("TCP_KEEPIDLE", 15), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 3)):
            if hasattr(socket, option):  # not on every platform
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)


class SilentTelnetWriterUnicode(TelnetWriterUnicode):
    def __init__(self, writer, **kwargs):
        super().__init__(
            writer.transport,
            writer.protocol,
            writer.fn_encoding,
            encoding_errors=writer.encoding_errors,
            **kwargs,
        )

    def _handle_do_forwardmask(self, buf):
        pass

    def write(self, string, errors=None):
        pass

    def writelines(self, lines, errors=None):
        pass

    def echo(self, string, errors=None):
        pass
