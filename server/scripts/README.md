# IPAM scan-all systemd timer

This directory contains two **template** files for scheduling
`scan_all_subnets.py` to run automatically on a Linux machine via systemd:

- `ipam-scan-all.service` — a oneshot unit that runs the script once.
- `ipam-scan-all.timer` — a timer that triggers that service on a schedule
  (daily, by default).

These are not wired into the app and nothing installs them automatically.
They're reference files you edit and install by hand on whatever machine
will run the periodic scan (typically the same machine running the
backend, or one with network access to it).

## Before installing

Edit `ipam-scan-all.service` and replace the placeholder path
`/path/to/net-toolbox` (in both `ExecStart` and `WorkingDirectory`) with
the actual location of this project on the target machine. Also adjust
`IPAM_BASE_URL` if the backend isn't running on `http://localhost:8000`.

## Changing the schedule

`OnCalendar=daily` in `ipam-scan-all.timer` can be replaced with any
systemd calendar expression, for example:

- `hourly`
- `weekly`
- `*-*-* 03:00:00` (every day at 3:00 AM)

Run `systemd-analyze calendar "<expression>"` to preview when a given
expression will next fire.

## Installing

```
sudo cp ipam-scan-all.service ipam-scan-all.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ipam-scan-all.timer
```
