{
  description = "hironow dotfiles";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, home-manager, ... }:
    let
      supportedSystems = [ "aarch64-darwin" "x86_64-linux" "aarch64-linux" ];
    in {
      homeConfigurations = builtins.listToAttrs (map (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          isDarwin = pkgs.stdenv.isDarwin;
          username = if isDarwin then "nino" else "root";
          homeDir = if isDarwin then "/Users/nino" else "/root";
        in {
          name = "${username}@${system}";
          value = home-manager.lib.homeManagerConfiguration {
            inherit pkgs;
            modules = [ ./home.nix ];
            extraSpecialArgs = { inherit username homeDir isDarwin; };
          };
        }
      ) supportedSystems);
    };
}
