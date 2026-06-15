import math
import socket
import struct
import time


STANDARD_GRAVITY_MPS2 = 9.80665
TARGET = ("127.0.0.1", 1024)


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.time()
    print("Sending test Data Out packets to 127.0.0.1:1024. Press Ctrl+C to stop.")
    try:
        while True:
            t = time.time() - start
            packet = bytearray(324)
            struct.pack_into("<i", packet, 0, 1)
            struct.pack_into("<I", packet, 4, int(t * 1000))
            struct.pack_into("<f", packet, 20, math.sin(t * 1.8) * 1.1 * STANDARD_GRAVITY_MPS2)
            struct.pack_into("<f", packet, 24, 0.0)
            struct.pack_into("<f", packet, 28, math.cos(t * 1.2) * 0.8 * STANDARD_GRAVITY_MPS2)
            struct.pack_into("<f", packet, 260, 30.0 + math.sin(t) * 10.0)
            sock.sendto(packet, TARGET)
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
