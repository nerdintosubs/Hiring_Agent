from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import jwt


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JWT for Hiring Agent API roles.")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--roles", required=True, help="Comma-separated roles.")
    parser.add_argument("--hours", type=int, default=12)
    parser.add_argument("--algorithm", default="HS256")
    args = parser.parse_args()

    payload = {
        "sub": args.subject,
        "roles": [item.strip() for item in args.roles.split(",") if item.strip()],
        "exp": datetime.utcnow() + timedelta(hours=args.hours),
    }
    token = jwt.encode(payload, args.secret, algorithm=args.algorithm)
    print(token)


if __name__ == "__main__":
    main()

