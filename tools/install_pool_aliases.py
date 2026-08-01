#!/usr/bin/env python3
"""Install the repository's pool-test shell functions into Bash startup."""

from pathlib import Path


SOURCE_LINE = "source /home/admin/isas/software/tools/pool_aliases.sh"


def main() -> int:
    bashrc = Path.home() / ".bashrc"
    existing = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
    if SOURCE_LINE not in existing.splitlines():
        separator = "" if not existing or existing.endswith("\n") else "\n"
        bashrc.write_text(
            existing + separator + "\n# ISAS pool-test helpers\n" + SOURCE_LINE + "\n",
            encoding="utf-8",
        )
        print(f"Installed pool-test helpers in {bashrc}")
    else:
        print(f"Pool-test helpers already installed in {bashrc}")
    print("Run: source ~/.bashrc")
    print("Then: pool-help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
