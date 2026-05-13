#!/usr/bin/env python3
import sys

def main():
    line = sys.stdin.readline().strip()
    if not line:
        return
    parts = line.split()
    if len(parts) != 3:
        print("usage: <num1> <operator> <num2>", file=sys.stderr)
        sys.exit(1)
    try:
        a = float(parts[0])
        op = parts[1]
        b = float(parts[2])
    except ValueError:
        print("Invalid number", file=sys.stderr)
        sys.exit(1)

    if op == '+':
        result = a + b
    elif op == '-':
        result = a - b
    elif op == '*':
        result = a * b
    elif op == '/':
        if b == 0:
            raise ZeroDivisionError("division by zero")
        result = a / b
    else:
        print("Invalid operator", file=sys.stderr)
        sys.exit(1)

    if isinstance(result, float) and result.is_integer():
        print(int(result))
    else:
        print(result)

if __name__ == "__main__":
    main()
