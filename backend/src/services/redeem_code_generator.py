"""Random redeem code generator.

Format: 4 groups of 4 chars separated by dashes (16 chars + 3 separators).
Alphabet excludes confusable characters (I/1/O/0/l), giving 32 safe chars.
Entropy: 32^16 = 2^80 -> collisions practically impossible.

Persistence layer enforces UNIQUE constraint; rare collisions are retried by callers.
"""

from __future__ import annotations

import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code() -> str:
    chunks = ["".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4)]
    return "-".join(chunks)
