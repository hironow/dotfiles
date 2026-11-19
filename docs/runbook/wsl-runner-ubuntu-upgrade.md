# Runner steps when upgrading WSL Ubuntu

On machines running a self-hosted runner inside WSL, upgrading Ubuntu can silently stop the runner.
The systemd service stays `active`, so `systemctl is-active` alone misses it.

## What happens

Upgrading removes the ICU library (`libicuNN`) needed by the .NET runtime that the runner uses.
The listener crashes right after startup with `Couldn't find a valid ICU package` and restarts in a loop every 5 seconds.
On GitHub, the runner goes offline.

## Before upgrading

1. Confirm no jobs are running and stop the runner service (ADR-0035).
2. Run `wsl --shutdown`, then back up to another drive with `wsl --export`.
   In WSL 3.0.5, export asks a running distro to stop and waits up to 60 seconds, warning and exporting anyway if it does not stop.
   Stopping the runner and shutting down first produces a clean stopped backup.
   For details and pitfalls (capturing exit codes, verifying the tar), see [Moving a WSL distro to another volume](wsl-distro-move.md).
3. Keep the backup until you verify the new version runs without issues.

## After upgrading

Reinstall dependencies in the runner directory and restart the service.

```bash
sudo bash <runner-dir>/bin/installdependencies.sh
sudo systemctl restart actions.runner.<org>.<name>.service
```

Verify with all three checks below.
Do not rely on `systemctl is-active` alone.

- `journalctl -u actions.runner.<org>.<name>.service` shows `Connected to GitHub` and `Listening for Jobs`.
- The runner shows `online` in the GitHub runners list.
- The first job finishes `Succeeded`.
