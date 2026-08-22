import time

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException


class DeviceSession:
    def __init__(self, device_type, host, username, password, device_name=None):
        self.device_type = device_type
        self.host = host
        self.username = username
        self.password = password
        self.device_name = device_name
        self.connection = None

    def __enter__(self):
        attempts = 0
        last_error = None
        while attempts < 2:
            try:
                self.connection = ConnectHandler(
                    device_type=self.device_type,
                    host=self.host,
                    username=self.username,
                    password=self.password,
                    timeout=10,
                )
                return self
            except NetmikoAuthenticationException:
                raise
            except NetmikoTimeoutException as e:
                last_error = e
                attempts += 1
                if attempts < 2:
                    time.sleep(3)
        raise last_error

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection is not None:
            self.connection.disconnect()

    def send_command(self, command):
        import troubleshoot_audit

        try:
            output = self.connection.send_command(command)
            troubleshoot_audit.log_command(self.device_name, command, self.username, True, None)
            return output
        except Exception as e:
            troubleshoot_audit.log_command(self.device_name, command, self.username, False, str(e))
            raise
