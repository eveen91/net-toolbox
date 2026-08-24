import subprocess
import socket

def ping_mtu(host: str, mtu: int, count: int = 5) -> Dict[str, Any]:
    # Linux/Gaia syntax: ping -M do -s (mtu - 28)
    payload = mtu - 28
    cmd = ["ping", "-c", str(count), "-M", "do", "-s", str(payload), host]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {"success": res.returncode == 0, "output": res.stdout}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_tcp_port(host: str, port: int, timeout: int = 2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except:
        return False
