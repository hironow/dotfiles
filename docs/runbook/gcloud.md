# Recovering gcloud Python virtualenv permissions

Applies to Cloud SDK installed under the user's home directory via Google's installer.
Do not use this procedure for system- or package-manager-managed SDKs, shared configs, or native Windows.

## Verify target and ownership

Run in a regular user shell.
If `CLOUDSDK_CONFIG` is set, inspect that config directory.

```sh
config_dir="${CLOUDSDK_CONFIG:-"$HOME/.config/gcloud"}"
venv="$config_dir/virtenv"
gcloud info --format='value(installation.sdk_root,config.paths.global_config_dir)'
printf 'config: %s\nvenv: %s\n' "$config_dir" "$venv"
ls -ld "$config_dir" "$venv" "$venv/update_module.log"
```

Verify that the displayed SDK is your own managed install and that the config directory matches `config_dir`.
Also check the parent directories of `config_dir` and `venv`, and abort if they point to unexpected locations such as a shared directory or symlink.
Also abort if `venv` itself is a symlink.

If `virtenv` or `update_module.log` inside it is owned by root and unwritable, updating gcloud Python dependencies fails with `PermissionError`.
Python starting or `pip check` passing does not prove write permission on the update target.

## Repair only the verified virtualenv

Confirm no gcloud or pip process is using that virtualenv, then use `sudo` only to repair ownership (run `gcloud` itself as a regular user):

```sh
# Targets only the venv verified above; does not touch the linked Python installation.
test -d "$venv" && test ! -L "$venv" &&
  sudo chown -h -R -P "$(id -u):$(id -g)" "$venv"
```

`-P` does not follow directory symlinks, and `-h` changes ownership of the link itself rather than its target.
Do not widen the scope to all of home, all gcloud config, or the SDK itself.
Files outside this virtualenv, such as past root-owned logs in the config directory, are left unchanged.

## Verify updates as a regular user

```sh
ls -ld "$venv" "$venv/update_module.log"
"$venv/bin/python3" -m pip check
just update-gcloud
```

If errors remain, inspect the error message reported at that point.
This procedure fixes virtualenv permission mismatches, not network failures or other dependency issues.

Run `just add-gcloud` and `just update-gcloud` without `sudo`.
`just update-all` runs `gcloud` then Homebrew, and stops before Homebrew if `gcloud` fails.
To isolate Homebrew on its own, run `brew update --verbose` (updates tap info without upgrading or cleaning up packages).
