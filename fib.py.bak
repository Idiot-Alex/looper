import sys

def fib(n: int) -> int:
    if n == 0:
        return 0
    elif n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 fib.py <N>")
        sys.exit(1)
    try:
        n = int(sys.argv[1])
    except ValueError:
        print("N must be an integer")
        sys.exit(1)
    print(fib(n))
