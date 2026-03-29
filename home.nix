{ pkgs, username, homeDir, isDarwin, ... }:

{
  imports = [
    ./nix/packages.nix
    ./nix/dotfiles.nix
    ./nix/shell.nix
  ];

  home.username = username;
  home.homeDirectory = homeDir;
  home.stateVersion = "24.11";

  programs.home-manager.enable = true;
}
