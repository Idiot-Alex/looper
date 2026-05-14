import sys

def fib(n: int) -> int:
    if n < 0:
        raise ValueError("N must be non-negative")
    if n == 0:
        return 0
    a, b = 0, 1
    for _ in range(1, n):
        a, b = b, a + b
    return b

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 fib.py <N>")
        sys.exit(1)
    try:
        n = int(sys.argv[1])
    except ValueError:
        print("Error: N must be an integer")
        sys.exit(1)
    if n < 0:
        print("Error: N must be non-negative")
        sys.exit(1)
    result = fib(n)
    print(result)
