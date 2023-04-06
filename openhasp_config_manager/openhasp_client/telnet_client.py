from telnetlib3 import TelnetTerminalClient, open_connection, telnet_client_shell


class OpenHaspTelnetClient:

    def __init__(self, host: str, port: int = 23, baudrate: int = 115200):
        self._host = host
        self._port = port
        self._baudrate = baudrate

    async def shell(self):
        # TODO: get automatic login working
        # async def shell(reader, writer):
        #     while True:
        #         # read stream until '?' mark is found
        #         outp = await reader.read(1024)
        #         if not outp:
        #             # End of File
        #             break
        #         elif '?' in outp:
        #             # reply all questions with 'y'.
        #             writer.write('y')
        #
        #         # display all server output
        #         print(outp, flush=True)
        #
        #     # EOF
        #     print()

        # await telnetlib3.client.run_client()

        reader, writer = await open_connection(
            host=self._host, port=self._port,
            tspeed=(self._baudrate, self._baudrate),
            shell=telnet_client_shell,
            client_factory=TelnetTerminalClient
        )

        await writer.protocol.waiter_closed
