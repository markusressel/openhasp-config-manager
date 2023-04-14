import asyncio
import os
import re
import sys

from telnetlib3 import TelnetTerminalClient, open_connection, telnet_client_shell, TelnetWriterUnicode


class OpenHaspTelnetClient:

    def __init__(self, host: str, port: int = 23, baudrate: int = 115200, user: str = 'admin', password: str = 'admin'):
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

                if 'Username:' in outp:
                    # reply all questions with 'y'.
                    writer.write(f"{self._username}\n")
                elif 'Password:' in outp:
                    writer.write(f"{self._password}\n")
                    break

            # switch over to interactive shell after automatic login
            await telnet_client_shell(reader, writer)

        reader, writer = await open_connection(
            host=self._host, port=self._port,
            tspeed=(self._baudrate, self._baudrate),
            shell=_shell,
            client_factory=TelnetTerminalClient
        )

        await writer.protocol.waiter_closed

    async def logs(self):
        async def _shell(reader, writer):
            login_done = False
            stdin, stdout = await self._make_stdio()
            buffer = ""
            while True:
                buffer = buffer + await reader.read(2048)

                if not buffer:
                    raise EOFError("Connection closed by remote host")

                if login_done:
                    buffer = buffer.replace('Prompt >', '')
                    buffer = re.sub(r"\x1b\[\d+\w+\s*", '', buffer, flags=re.IGNORECASE | re.S)
                    if not buffer.endswith("\r\n"):
                        # wait for the end of the line before processing
                        continue

                    lines = buffer.splitlines(keepends=True)
                    for line in lines:
                        line = line.lstrip(" ")
                        if not line.startswith("["):
                            continue
                        stdout.write(line.encode() or b":?!?:")

                    buffer = ""
                    continue

                if 'Username:' in buffer:
                    # reply all questions with 'y'.
                    writer.write(f"{self._username}\n")
                elif 'Password:' in buffer:
                    writer.write(f"{self._password}\n")
                    login_done = True

                buffer = ""
            # switch over to interactive shell after automatic login
            # await telnet_client_shell(reader, SilentTelnetWriterUnicode(writer, client=True))

        reader, writer = await open_connection(
            host=self._host, port=self._port,
            tspeed=(self._baudrate, self._baudrate),
            shell=_shell,
            client_factory=TelnetTerminalClient
        )

        await writer.protocol.waiter_closed

    async def _make_stdio(self):
        """
        Return (reader, writer) pair for sys.stdin, sys.stdout.

        This method is a coroutine.
        """
        reader = asyncio.StreamReader()
        reader_protocol = asyncio.StreamReaderProtocol(reader)

        # Thanks:
        #
        #   https://gist.github.com/nathan-hoad/8966377
        #
        # After some experimentation, this 'sameopenfile' conditional seems
        # allow us to handle stdin as a pipe or a keyboard.  In the case of
        # a tty, 0 and 1 are the same open file, we use:
        #
        #    https://github.com/orochimarufan/.files/blob/master/bin/mpr
        write_fobj = sys.stdout
        if os.path.sameopenfile(0, 1):
            write_fobj = sys.stdin
        loop = asyncio.get_event_loop_policy().get_event_loop()
        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, write_fobj
        )

        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

        await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

        return reader, writer


class SilentTelnetWriterUnicode(TelnetWriterUnicode):

    def __init__(self, writer, **kwargs):
        super().__init__(
            writer.transport, writer.protocol, writer.fn_encoding, encoding_errors=writer.encoding_errors,
            **kwargs
        )

    def _handle_do_forwardmask(self, buf):
        pass

    def write(self, string, errors=None):
        pass

    def writelines(self, lines, errors=None):
        pass

    def echo(self, string, errors=None):
        pass
