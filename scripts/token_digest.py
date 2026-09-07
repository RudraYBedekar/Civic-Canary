from __future__ import annotations

import getpass

from services.security import token_digest


def main() -> None:
    token = getpass.getpass("Choose a reviewer token: ")
    confirmation = getpass.getpass("Confirm the reviewer token: ")
    if token != confirmation:
        raise SystemExit("Tokens do not match.")
    if len(token) < 20:
        raise SystemExit("Use a reviewer token containing at least 20 characters.")
    print(token_digest(token))


if __name__ == "__main__":
    main()
