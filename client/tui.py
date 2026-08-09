"""Textual TUI that polls a remote stats server and displays it on the Pi's screen.

Run this on the Raspberry Pi:

    python -m client.tui --host 192.168.1.50 --port 8000
"""

import argparse
from collections import deque

import requests
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, ProgressBar, Sparkline, Static

_CPU_BLOCKS = "▁▂▃▄▅▆▇█"


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _fmt_rate(bps):
    return f"{_fmt_bytes(bps)}/s"


def _fmt_uptime(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def _cpu_core_bars(per_cpu):
    return "".join(_CPU_BLOCKS[min(7, int(p / 100 * 8))] for p in per_cpu)


class MonitorApp(App):
    CSS = """
    #status, #host_info, #cpu_label, #cpu_cores, #cpu_history_label,
    #mem_label, #swap_label, #net_label, #disk_label, #proc_label {
        width: 100%;
        margin: 0 1;
    }

    ProgressBar {
        width: 100%;
        content-align: center middle;
        margin: 0 1;
    }

    ProgressBar > Bar {
        width: 1fr;
    }

    #cpu_history {
        width: 100%;
        margin: 0 1;
    }

    #disk_table, #proc_table {
        width: 100%;
        margin: 0 1;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, host: str, port: int, interval: float):
        super().__init__()
        self.host = host
        self.port = port
        self.interval = interval
        self._cpu_history = deque(maxlen=50)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Connecting...", id="status")
        yield Static("", id="host_info")
        yield Static("CPU", id="cpu_label")
        yield ProgressBar(total=100, id="cpu_bar", show_eta=False)
        yield Static("", id="cpu_cores")
        yield Static("CPU history", id="cpu_history_label")
        yield Sparkline([], id="cpu_history", summary_function=max)
        yield Static("Memory", id="mem_label")
        yield ProgressBar(total=100, id="mem_bar", show_eta=False)
        yield Static("Swap", id="swap_label")
        yield ProgressBar(total=100, id="swap_bar", show_eta=False)
        yield Static("Network", id="net_label")
        yield Static("Disks", id="disk_label")
        yield DataTable(id="disk_table")
        yield Static("Top Processes", id="proc_label")
        yield DataTable(id="proc_table")
        yield Footer()

    def on_mount(self) -> None:
        disk_table = self.query_one("#disk_table", DataTable)
        disk_table.add_columns("Mount", "Used %", "Used", "Total")

        proc_table = self.query_one("#proc_table", DataTable)
        proc_table.add_columns("PID", "Name", "CPU%", "Mem%")
        proc_table.styles.height = "1fr"

        self.set_interval(self.interval, self.refresh_stats)
        self.refresh_stats()

    def refresh_stats(self) -> None:
        url = f"http://{self.host}:{self.port}/stats"
        try:
            resp = requests.get(url, timeout=3)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.query_one("#status", Static).update(f"[red]Connection error: {exc}[/red]")
            return

        self.query_one("#status", Static).update(f"[green]Connected to {self.host}:{self.port}[/green]")

        host = data.get("host")
        if host:
            load = host.get("load_avg")
            load_str = " ".join(f"{x:.2f}" for x in load) if load else "N/A"
            self.query_one("#host_info", Static).update(
                f"{host['hostname'][:20]} • up {_fmt_uptime(host['uptime_s'])} • load {load_str}"
            )

        cpu = data["cpu"]
        temp = f"{cpu['temp_c']:.1f}C" if cpu.get("temp_c") is not None else "N/A"
        self.query_one("#cpu_label", Static).update(f"CPU: {cpu['percent']:.1f}%  Temp: {temp}")
        self.query_one("#cpu_bar", ProgressBar).update(progress=cpu["percent"])

        per_cpu = cpu.get("per_cpu") or []
        self.query_one("#cpu_cores", Static).update("Cores: " + _cpu_core_bars(per_cpu))

        self._cpu_history.append(cpu["percent"])
        self.query_one("#cpu_history", Sparkline).data = list(self._cpu_history)

        mem = data["memory"]
        self.query_one("#mem_label", Static).update(
            f"Memory: {_fmt_bytes(mem['used'])} / {_fmt_bytes(mem['total'])} ({mem['percent']:.1f}%)"
        )
        self.query_one("#mem_bar", ProgressBar).update(progress=mem["percent"])

        swap = data["swap"]
        self.query_one("#swap_label", Static).update(
            f"Swap: {_fmt_bytes(swap['used'])} / {_fmt_bytes(swap['total'])} ({swap['percent']:.1f}%)"
        )
        self.query_one("#swap_bar", ProgressBar).update(progress=swap["percent"])

        net = data["network"]
        self.query_one("#net_label", Static).update(
            f"Network: up {_fmt_rate(net['sent_bps'])}  down {_fmt_rate(net['recv_bps'])}"
        )

        disk_table = self.query_one("#disk_table", DataTable)
        disk_table.clear()
        for disk in data["disks"]:
            disk_table.add_row(
                disk["mountpoint"],
                f"{disk['percent']:.1f}%",
                _fmt_bytes(disk["used"]),
                _fmt_bytes(disk["total"]),
            )

        proc_table = self.query_one("#proc_table", DataTable)
        proc_table.clear()
        for proc in data.get("processes", []):
            proc_table.add_row(
                str(proc["pid"]),
                proc["name"][:20],
                f"{proc['cpu_percent']:.1f}",
                f"{proc['memory_percent']:.1f}",
            )


def main():
    parser = argparse.ArgumentParser(description="Display a remote computer's system stats on the Pi's screen.")
    parser.add_argument("--host", required=True, help="IP address or hostname of the monitored computer")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds")
    args = parser.parse_args()

    MonitorApp(args.host, args.port, args.interval).run()


if __name__ == "__main__":
    main()
