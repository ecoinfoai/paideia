{
  description = "paideia — 한 교과목의 학기 전 주기 데이터 시스템";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python311
            uv
            ruff
            pyright
            git
          ];

          shellHook = ''
            echo "paideia devShell"
            echo "  python : $(python3 --version)"
            echo "  uv     : $(uv --version)"
            echo ""
            echo "first run:  uv sync"
          '';
        };
      });
}
