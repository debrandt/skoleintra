{
  description = "Skoleintra scraper and web UI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # The installable package
        skoleintra = python.pkgs.buildPythonApplication {
          pname = "skoleintra";
          version = "0.1.0";
          pyproject = true;

          src = ./.;

          build-system = [ python.pkgs.hatchling ];

          dependencies = with python.pkgs; [
            requests
            beautifulsoup4
            lxml
            fastapi
            uvicorn
            sqlalchemy
            alembic
            jinja2
            pydantic-settings
            psycopg # psycopg in nixpkgs
          ];
        };
      in
      {
        packages.default = skoleintra;

        # Dev shell: same deps + dev tools
        devShells.default = pkgs.mkShell {
          packages = [
            (python.withPackages (
              ps: with ps; [
                requests
                beautifulsoup4
                lxml
                fastapi
                uvicorn
                sqlalchemy
                alembic
                jinja2
                pydantic-settings
                psycopg
                # dev tools
                pip
                pytest
                ipython
              ]
            ))
            pkgs.postgresql # for psql CLI
          ];

          shellHook = ''
            export PYTHONPATH=$PWD:$PYTHONPATH

            echo "skoleintra dev shell ready"
            echo "Python: $(python --version)"
            echo "Run the CLI: nix run . -- <command>"
          '';
        };
      }
    );
}
