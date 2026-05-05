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
        pkgs = import nixpkgs { inherit system; config.allowUnfree = true; };
        python = pkgs.python313;

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
            python-multipart
            uvicorn
            sqlalchemy
            alembic
            jinja2
            pydantic-settings
            psycopg
            boto3
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
                python-multipart
                uvicorn
                sqlalchemy
                alembic
                jinja2
                pydantic-settings
                psycopg
                boto3
                # dev tools
                black
                isort
                pip
                pylint
                pytest
                ipython
              ]
            ))
            pkgs.nodejs_24
            pkgs.gh
            pkgs.github-copilot-cli
            pkgs.postgresql # for psql CLI
          ];

          shellHook = ''
            export PYTHONPATH=$PWD:$PYTHONPATH

            echo "skoleintra dev shell ready"
            echo "Python: $(python --version)"
            echo "Initialize albemic by upgrading head: alembic upgrade head"
            echo "Run the CLI: nix run . -- <command>"
            echo "Format code: nix develop -c black . && nix develop -c isort ."
            echo "Lint code: nix develop -c pylint skoleintra"
          '';
        };
      }
    );
}
