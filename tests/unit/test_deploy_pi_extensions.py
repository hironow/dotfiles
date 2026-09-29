"""A fresh deploy restores Pi packages after global mise installation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")


def test_unix_deploy_uses_mise_even_before_shell_reloads() -> None:
    unix = DEPLOY.split('echo "==> Start to deploy dotfiles to home directory."', 1)[1]
    assert "mise -C / install" in unix
    assert (
        "mise -C / exec -- python ~/dotfiles/scripts/install_pi_extensions.py" in unix
    )
    assert unix.index("mise -C / install") < unix.index("mise -C / exec -- python")


def test_windows_deploy_restores_packages_after_global_mise_install() -> None:
    windows = DEPLOY.split("    exit 0", 1)[0]
    assert "MISE_NODE_COREPACK=0 mise -C / install" in windows
    assert (
        "MISE_NODE_COREPACK=0 mise -C / exec -- python ~/dotfiles/scripts/install_pi_extensions.py"
        in windows
    )
    assert windows.index("MISE_NODE_COREPACK=0 mise -C / install") < windows.index(
        "MISE_NODE_COREPACK=0 mise -C / exec -- python"
    )
