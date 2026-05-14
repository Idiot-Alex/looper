#!/usr/bin/env python3
import sys

def fib(n: int) -> int:
    if n < 0:
        raise ValueError("N must be non-negative")
    if n == 0:
        return 0
    elif n == 1:
        return 1
    else:
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 fib.py <N>", file=sys.stderr)
        sys.exit(1)
    try:
        n = int(sys.argv[1])
        result = fib(n)
        print(result)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
