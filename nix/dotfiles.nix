{ ... }:

{
  home.file = {
    ".zshrc".source = ../.zshrc;
    ".tmux.conf".source = ../tools/tmux/tmux.conf;
  };

  xdg.configFile = {
    "sheldon/plugins.toml".source = ../sheldon-plugins.toml;
    "starship.toml".source = ../starship.toml;
    "ghostty/config".source = ../tools/ghostty-config;
    "git/ignore".source = ../dump/gitignore-global;
  };
}
