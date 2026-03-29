{ pkgs, lib, ... }:

{
  home.activation = {
    sheldonLock = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run ${pkgs.sheldon}/bin/sheldon lock 2>/dev/null || true
    '';
    fzfTab = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if [ ! -d "$HOME/.local/share/fzf-tab" ]; then
        run ${pkgs.git}/bin/git clone --depth 1 \
          https://github.com/Aloxaf/fzf-tab "$HOME/.local/share/fzf-tab"
      fi
    '';
  };
}
