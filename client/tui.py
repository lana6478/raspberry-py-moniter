"""Textual TUI that polls a remote stats server and displays it on the Pi's screen.

Run this on the Raspberry Pi:

    python -m client.tui --host 192.168.1.50 --port 8000
"""

import argparse

import requests
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, ProgressBar, Static


def _fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _fmt_rate(bps):
    return f"{_fmt_bytes(bps)}/s"


class MonitorApp(App):
    CSS = """
    Vertical > Static { margin: 1 2; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, host: str, port: int, interval: float):
        super().__init__()
        self.host = host
        self.port = port
        self.interval = interval

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Connecting...", id="status")
        with Vertical():
            yield Static("CPU", id="cpu_label")
            yield ProgressBar(total=100, id="cpu_bar", show_eta=False)
            yield Static("Memory", id="mem_label")
            yield ProgressBar(total=100, id="mem_bar", show_eta=False)
            yield Static("Swap", id="swap_label")
            yield ProgressBar(total=100, id="swap_bar", show_eta=False)
            yield Static("Network", id="net_label")
            yield DataTable(id="disk_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#disk_table", DataTable)
        table.add_columns("Mount", "Used %", "Used", "Total")
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

        cpu = data["cpu"]
        temp = f"{cpu['temp_c']:.1f}C" if cpu.get("temp_c") is not None else "N/A"
        self.query_one("#cpu_label", Static).update(f"CPU: {cpu['percent']:.1f}%  Temp: {temp}")
        self.query_one("#cpu_bar", ProgressBar).update(progress=cpu["percent"])

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

        table = self.query_one("#disk_table", DataTable)
        table.clear()
        for disk in data["disks"]:
            table.add_row(
                disk["mountpoint"],
                f"{disk['percent']:.1f}%",
                _fmt_bytes(disk["used"]),
                _fmt_bytes(disk["total"]),
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
