import logging
import time

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

logger = logging.getLogger("net_toolbox.device_drivers.base")


class DeviceSession:
    def __init__(self, device_type, host, username, password, device_name=None):
        self.device_type = device_type
        self.host = host
        self.username = username
        self.password = password
        self.device_name = device_name
        self.connection = None

    @property
    def label(self):
        # Human-readable device reference for log messages: the inventory
        # name when the caller supplied one (base.py callers don't yet, so
        # it's usually None), otherwise the host.
        return self.device_name or self.host

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
                logger.info(
                    "Connected to %s (%s, type=%s, user=%s)",
                    self.label, self.host, self.device_type, self.username,
                )
                return self
            except NetmikoAuthenticationException:
                logger.error(
                    "Authentication failed for %s (%s, user=%s)",
                    self.label, self.host, self.username,
                )
                raise
            except NetmikoTimeoutException as e:
                last_error = e
                attempts += 1
                logger.warning(
                    "Connection timeout for %s (%s) attempt %d/2%s",
                    self.label, self.host, attempts,
                    " — retrying in 3s" if attempts < 2 else " — giving up",
                )
                if attempts < 2:
                    time.sleep(3)
        logger.error("Connection to %s (%s) failed: %s", self.label, self.host, last_error)
        raise last_error

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection is not None:
            try:
                self.connection.disconnect()
            except Exception as e:
                logger.warning("Disconnect from %s failed: %s", self.label, e)

    def send_command(self, command):
        import troubleshoot_audit

        try:
            output = self.connection.send_command(command)
            troubleshoot_audit.log_command(self.device_name, command, self.username, True, None)
            logger.debug("Command OK on %s: %s", self.label, command)
            return output
        except Exception as e:
            troubleshoot_audit.log_command(self.device_name, command, self.username, False, str(e))
            logger.error(
                "Command failed on %s (%s): %s -> %s", self.label, self.host, command, e
            )
            raise
