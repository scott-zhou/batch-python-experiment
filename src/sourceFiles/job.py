import argparse
import sys
import time

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Job main entry.')
    parser.add_argument('input', type=str,
                        help='Input job definations')
    parser.add_argument('output', type=str,
                        help='Input job definations')
    args = parser.parse_args()
    output = 0
    with open(args.input) as fd:
        for line in fd:
            values = line.split()
            if len(values) < 2:
                continue
            start, end = int(values[0]), int(values[1])
            for v in range(start, end):
                output += v
                print('.', end='')
                sys.stdout.flush()
                time.sleep(1)
    print()
    with open(args.output, "w") as fd:
        fd.write(f'The sum is {output}')
