from telnetlib3 import TelnetTerminalClient, open_connection, telnet_client_shell


class OpenHaspTelnetClient:

    def __init__(self, host: str, port: int = 23, baudrate: int = 115200, user: str = 'admin', password: str = 'admin'):
        self._host = host
        self._port = port
        self._baudrate = baudrate
        self._username = user
        self._password = password

    async def shell(self):
        async def shell(reader, writer):
            while True:
                # read stream until '?' mark is found
                outp = await reader.read(1024)

                if not outp:
                    # End of File
                    break

                # display all server output
                print(outp, flush=True)

                if 'Username:' in outp:
                    # reply all questions with 'y'.
                    writer.write(f"{self._username}\n")
                elif 'Password:' in outp:
                    writer.write(f"{self._password}\n")
                    break

            await telnet_client_shell(reader, writer)

        # await telnetlib3.client.run_client()

        reader, writer = await open_connection(
            host=self._host, port=self._port,
            tspeed=(self._baudrate, self._baudrate),
            shell=shell,
            client_factory=TelnetTerminalClient
        )

        await writer.protocol.waiter_closed
