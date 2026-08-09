"""Textual TUI that polls a remote stats server and displays it on the Pi's screen.

Run this on the Raspberry Pi:

    python -m client.tui --host 192.168.1.50 --port 8000
"""

import argparse
from collections import deque

import requests
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Sparkline, Static

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


def _threshold_color(percent):
    if percent >= 85:
        return "bold bright_green"
    if percent >= 60:
        return "bright_green"
    return "green"


def _ascii_bar(percent, width=18):
    filled = max(0, min(width, int(round(percent / 100 * width))))
    return "█" * filled + "░" * (width - filled)


class MonitorApp(App):
    CSS = """
    Screen {
        background: ansi_black;
        color: ansi_bright_green;
    }

    Header {
        background: ansi_black;
        color: ansi_bright_green;
        text-style: bold;
    }

    Footer {
        background: ansi_black;
        color: ansi_green;
    }

    FooterKey {
        background: ansi_black;
    }

    FooterKey .footer-key--key {
        color: ansi_bright_green;
        background: ansi_black;
        text-style: bold;
    }

    FooterKey .footer-key--description {
        color: ansi_green;
        background: ansi_black;
    }

    #status_line, #cpu_line, #cores_line, #history_label, #mem_line,
    #net_line, #disk_line, #proc_label {
        width: 100%;
        margin: 0 1;
    }

    #cpu_history {
        width: 100%;
        margin: 0 1;
        color: ansi_bright_green;
    }

    Sparkline > .sparkline--max-color {
        color: ansi_bright_green;
    }

    Sparkline > .sparkline--min-color {
        color: ansi_green;
    }

    #proc_table {
        width: 100%;
        margin: 0 1;
        background: ansi_black;
        color: ansi_bright_green;
    }

    #proc_table > .datatable--header {
        background: ansi_black;
        color: ansi_bright_green;
        text-style: bold;
    }

    #proc_table > .datatable--cursor {
        background: ansi_green;
        color: ansi_black;
    }

    #proc_table > .datatable--even-row {
        background: ansi_black;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, host: str, port: int, interval: float):
        super().__init__()
        self.host = host
        self.port = port
        self.interval = interval
        self._cpu_history = deque(maxlen=40)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status_line")
        yield Static("", id="cpu_line")
        yield Static("", id="cores_line")
        yield Sparkline([], id="cpu_history", summary_function=max)
        yield Static("", id="mem_line")
        yield Static("", id="net_line")
        yield Static("", id="disk_line")
        yield Static(r"[bold bright_green]══\[ PROCESSES ]══[/]", id="proc_label")
        yield DataTable(id="proc_table")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "root@monitor"

        proc_table = self.query_one("#proc_table", DataTable)
        proc_table.add_columns("PID", "NAME", "CPU%")

        self.set_interval(self.interval, self.refresh_stats)
        self.refresh_stats()

    def refresh_stats(self) -> None:
        url = f"http://{self.host}:{self.port}/stats"
        try:
            resp = requests.get(url, timeout=3)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.query_one("#status_line", Static).update(
                f"[bold bright_green]░░ OFFLINE ░░[/]  {exc}"
            )
            return

        host = data.get("host") or {}
        load = host.get("load_avg")
        load_str = "/".join(f"{x:.1f}" for x in load) if load else "N/A"
        hostname = (host.get("hostname") or self.host)[:14]
        uptime = _fmt_uptime(host["uptime_s"]) if host.get("uptime_s") is not None else "?"
        self.query_one("#status_line", Static).update(
            f"[bold bright_green]●[/] root@{hostname} up {uptime} load {load_str}"
        )

        cpu = data["cpu"]
        temp = f"{cpu['temp_c']:.1f}C" if cpu.get("temp_c") is not None else "N/A"
        cpu_color = _threshold_color(cpu["percent"])
        self.query_one("#cpu_line", Static).update(
            f"[bold bright_green]CPU[/] [{cpu_color}]{_ascii_bar(cpu['percent'])}[/] "
            f"[{cpu_color}]{cpu['percent']:5.1f}%[/]  {temp}"
        )

        per_cpu = cpu.get("per_cpu") or []
        self.query_one("#cores_line", Static).update(
            "[bold bright_green]CORES[/] [bright_green]" + _cpu_core_bars(per_cpu) + "[/]"
        )

        self._cpu_history.append(cpu["percent"])
        self.query_one("#cpu_history", Sparkline).data = list(self._cpu_history)

        mem = data["memory"]
        swap = data["swap"]
        mem_color = _threshold_color(mem["percent"])
        self.query_one("#mem_line", Static).update(
            f"[bold bright_green]MEM[/] [{mem_color}]{_ascii_bar(mem['percent'], 10)}[/] "
            f"{mem['percent']:4.1f}%  {_fmt_bytes(mem['used'])}/{_fmt_bytes(mem['total'])}  "
            f"SWAP {swap['percent']:.0f}%"
        )

        net = data["network"]
        self.query_one("#net_line", Static).update(
            f"[bold bright_green]NET[/] [bright_green]↑{_fmt_rate(net['sent_bps'])}"
            f"  ↓{_fmt_rate(net['recv_bps'])}[/]"
        )

        disks = data.get("disks", [])
        disk_str = "  ".join(
            f"{d['mountpoint']} [{_threshold_color(d['percent'])}]{d['percent']:.0f}%[/]" for d in disks
        )
        self.query_one("#disk_line", Static).update(f"[bold bright_green]DISK[/] {disk_str}")

        proc_table = self.query_one("#proc_table", DataTable)
        proc_table.clear()
        for proc in data.get("processes", [])[:6]:
            proc_table.add_row(
                str(proc["pid"]),
                proc["name"][:24],
                f"{proc['cpu_percent']:.1f}",
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
