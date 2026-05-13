import sys

def calculator(a, op, b):
    if op == '+':
        return a + b
    elif op == '-':
        return a - b
    elif op == '*':
        return a * b
    elif op == '/':
        if b == 0:
            raise ValueError("除数不能为0")
        return a / b
    else:
        raise ValueError(f"不支持的运算符: {op}")

def main():
    if len(sys.argv) != 4:
        print("用法: python3 calculator.py <数字1> <运算符> <数字2>")
        sys.exit(1)
    try:
        num1 = float(sys.argv[1])
        op = sys.argv[2]
        num2 = float(sys.argv[3])
        result = calculator(num1, op, num2)
        print(f"结果: {result}")
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"未知错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
