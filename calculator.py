import sys

def main():
    line = sys.stdin.readline().strip()
    if not line:
        return
    parts = line.split()
    if len(parts) != 3:
        print("Invalid input format")
        sys.exit(1)
    num1 = float(parts[0])
    op = parts[1]
    num2 = float(parts[2])
    if op == '+':
        result = num1 + num2
    elif op == '-':
        result = num1 - num2
    elif op == '*':
        result = num1 * num2
    elif op == '/':
        if num2 == 0:
            print("Division by zero")
            sys.exit(1)
        result = num1 / num2
    else:
        print(f"Unsupported operator: {op}")
        sys.exit(1)
    # Remove trailing zeros for integer-like results? Not required, just print
    print(result)

if __name__ == "__main__":
    main()
