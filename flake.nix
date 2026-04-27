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
            noto-fonts-cjk-sans
            nanum
          ];

          shellHook = ''
            echo "paideia devShell"
            echo "  python : $(python3 --version)"
            echo "  uv     : $(uv --version)"
            echo ""
            echo "first run:  uv sync"
            echo ""
            echo "Korean fonts: NanumGothic Regular + Bold (pkgs.nanum) +"
            echo "              CJK fallback (noto-fonts-cjk-sans)."
            echo "needs-map v0.1.1 fail-fast checks NanumGothic via fc-match."
            echo ""
            echo "Optional RoBERTa sentiment runtime (US6, ~3 GB venv):"
            echo "  uv sync --extra roberta --package needs-map"
            echo "Use a separate shell — torch CPU build pulls cuda/transformers"
            echo "stack and bloats the base devShell. Override model cache via"
            echo "PAIDEIA_ROBERTA_CACHE_DIR. Skip with --no-roberta to keep the"
            echo "pipeline free of torch."
          '';
        };

        devShells.roberta = pkgs.mkShell {
          # Optional CPU-only RoBERTa runtime shell. Activate explicitly:
          #   nix develop .#roberta
          # Keeps the base devShell lean (no torch/transformers in default).
          # torch is installed via uv extras inside the shell rather than nix
          # (python311Packages.torch currently fails to evaluate on this
          # nixpkgs revision due to a sphinx interpreter mismatch).
          buildInputs = with pkgs; [
            python311
            uv
            ruff
            pyright
            git
            noto-fonts-cjk-sans
            nanum
          ];

          shellHook = ''
            echo "paideia devShell — RoBERTa optional (CPU torch via uv)"
            echo "  python : $(python3 --version)"
            echo "  uv     : $(uv --version)"
            echo ""
            echo "Install torch + transformers + tokenizers (CPU build):"
            echo "  uv sync --extra roberta --package needs-map"
            echo ""
            echo "torch wheel pulls ~3 GB of cuda libs even on CPU; isolate"
            echo "via PAIDEIA_ROBERTA_CACHE_DIR for the kote model cache."
          '';
        };
      });
}
