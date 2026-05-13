import sys

def main():
    line = sys.stdin.readline()
    if line:
        line = line.rstrip('\n')
    print(line[::-1])

if __name__ == '__main__':
    main()
