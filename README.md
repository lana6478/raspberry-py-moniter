# raspberry-py-moniter

A text-based system monitor for a Raspberry Pi: a small HTTP server runs on
your computer and reports CPU, memory, disk, and network stats; a Textual TUI
running on the Pi polls that server and displays them on the Pi's screen.

```
[ your computer ]  --HTTP-->  [ raspberry pi ]
  server/server.py                client/tui.py
  (psutil stats)                  (textual display)
```

## 1. Run the server on your computer

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-server.txt
python -m server.server --port 8000
```

This serves JSON stats at `http://<your-computer-ip>:8000/stats`. Find your
computer's LAN IP with `ip addr` (Linux), `ipconfig` (Windows), or
`ifconfig` (macOS). Make sure your firewall allows inbound connections on
the chosen port from your Pi.

CPU temperature is read via `psutil.sensors_temperatures()`, which only
works on Linux; on Windows/macOS the temperature will show as `N/A`.

## 2. Clone the repo onto the Pi

On the Raspberry Pi:

```bash
git clone https://github.com/lana6478/raspberry-py-moniter.git
cd raspberry-py-moniter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-client.txt
```

## 3. Run the TUI on the Pi

```bash
python -m client.tui --host <your-computer-ip> --port 8000
```

Press `q` to quit. Use `--interval` to change the refresh rate in seconds
(default: 2).

## Optional: run the server automatically with systemd

Instead of starting the server by hand every time, install it as a systemd
service so it starts on boot and restarts if it crashes:

```bash
cp deploy/raspi-monitor-server.service ~/raspi-monitor-server.service
# Edit ~/raspi-monitor-server.service first if your username or the repo
# path differ from what's in deploy/raspi-monitor-server.service.
sudo cp ~/raspi-monitor-server.service /etc/systemd/system/raspi-monitor-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now raspi-monitor-server.service
systemctl status raspi-monitor-server.service --no-pager
```

Manage it afterwards with `sudo systemctl stop/start/restart
raspi-monitor-server.service` and view logs with `journalctl -u
raspi-monitor-server.service -f`.

## Notes

- Traffic between the server and client is plain HTTP with no
  authentication — intended for use on a trusted home LAN only.
- Disk stats are shown for every mounted, readable partition on the
  monitored computer.
