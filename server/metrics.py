"""Collects system metrics from the host machine using psutil."""

import os
import socket
import time

import psutil

_last_net = None
_last_net_time = None


def _cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
    except AttributeError:
        return None
    if not temps:
        return None
    for key in ("coretemp", "cpu_thermal", "cpu-thermal", "k10temp"):
        if key in temps and temps[key]:
            return temps[key][0].current
    for entries in temps.values():
        if entries:
            return entries[0].current
    return None


def _network_rates():
    global _last_net, _last_net_time
    now = time.time()
    counters = psutil.net_io_counters()
    rates = {"sent_bps": 0.0, "recv_bps": 0.0}
    if _last_net is not None:
        elapsed = now - _last_net_time
        if elapsed > 0:
            rates["sent_bps"] = (counters.bytes_sent - _last_net.bytes_sent) / elapsed
            rates["recv_bps"] = (counters.bytes_recv - _last_net.bytes_recv) / elapsed
    _last_net = counters
    _last_net_time = now
    return rates


def _host_info():
    try:
        load_avg = list(os.getloadavg())
    except (AttributeError, OSError):
        load_avg = None
    return {
        "hostname": socket.gethostname(),
        "uptime_s": time.time() - psutil.boot_time(),
        "load_avg": load_avg,
    }


def _top_processes(limit=15):
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        procs.append(
            {
                "pid": info["pid"],
                "name": info["name"] or "",
                "cpu_percent": info["cpu_percent"] or 0.0,
                "memory_percent": info["memory_percent"] or 0.0,
            }
        )
    procs.sort(key=lambda p: p["cpu_percent"], reverse=True)
    return procs[:limit]


def collect_stats():
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disks = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype == "squashfs" or part.mountpoint.startswith("/snap/"):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append(
            {
                "mountpoint": part.mountpoint,
                "total": usage.total,
                "used": usage.used,
                "percent": usage.percent,
            }
        )

    return {
        "timestamp": time.time(),
        "cpu": {
            "percent": psutil.cpu_percent(interval=None),
            "per_cpu": psutil.cpu_percent(interval=None, percpu=True),
            "temp_c": _cpu_temp(),
        },
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "percent": vm.percent,
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "percent": swap.percent,
        },
        "disks": disks,
        "network": _network_rates(),
        "host": _host_info(),
        "processes": _top_processes(),
    }
