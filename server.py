
import socket
import numpy as np
import time
from threading import Timer

NANO_TO_SEC = 1e-9
RATE_IN_SEC = 1000
VEC_LENGTH = 50
LOW_PACKET_LOSS_INTERVAL = 2000
HIGH_PACKET_LOSS_INTERVAL = 3000
RECOVERY_MODE_FRAC = 0.3


class Server:

    def __init__(self, host: str, port: int, seconds_to_run: int, lossy_mode: bool = False,
                 enable_recovery_mode: bool = False):
        self.host: str = host
        self.port: int = port
        self.lossy_mode: bool = lossy_mode
        self.data_count: int = 0    # The amount of packets sent in the current time period (this second).
        self.drop: bool = False     # Whether to drop a packet.
        self.recovery_mode: bool = False      # Whether the server is currently in recovery mode
        self.new_period_start: bool = True    # Marks start of a new second
        self.enable_recovery_mode: bool = enable_recovery_mode
        self.seconds_to_run: int = seconds_to_run
        self.sec_count: int = 0
        self.execute: bool = True   # The program executes while this field is True

    def drop_packets_(self):
        # Orders the main thread to drop a packet through self.drop.
        random_drop = np.random.randint(low=LOW_PACKET_LOSS_INTERVAL, high=HIGH_PACKET_LOSS_INTERVAL)
        timer = Timer(random_drop * (1 / RATE_IN_SEC), self.drop_packets_)
        timer.setDaemon(True)
        timer.start()
        self.drop = True

    def measure_rate_(self):
        # Measures the sending rate of the current second and marks the beginning of a new one.
        self.new_period_start = True
        self.data_count = 0
        self.sec_count += 1
        if self.sec_count == self.seconds_to_run:
            self.execute = False
            return
        rate_measurer = Timer(1, self.measure_rate_)
        rate_measurer.setDaemon(True)
        rate_measurer.start()

    def recovery_mode_(self):
        if self.data_count < RATE_IN_SEC * RECOVERY_MODE_FRAC * 0.5:
            self.recovery_mode = True
        time.sleep(1. - RECOVERY_MODE_FRAC)
        recovery_timer = Timer(RECOVERY_MODE_FRAC, self.recovery_mode_)
        recovery_timer.start()

    def send_data(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            conn, addr = s.accept()
            avg_time = 0.0      # The average time it takes to send a packet
            i = 0
            if self.lossy_mode:
                self.drop_packets_()
            self.drop = False
            avg_times = np.zeros(RATE_IN_SEC)   # Will record the sending times pf the past packets
            pause_between_sends = 1. / RATE_IN_SEC  # The amount of time that should pass before sending another packet.
            self.measure_rate_()
            init_mode = True    # Marks the period of beginning of connection for stats gathering
            try:
                with conn:
                    if self.enable_recovery_mode:
                        recovery_timer = Timer(RECOVERY_MODE_FRAC, self.recovery_mode_)
                        recovery_timer.setDaemon(True)
                        recovery_timer.start()

                    while self.execute:
                        self.new_period_start = False
                        start = time.time_ns()
                        time.sleep(pause_between_sends)

                        if self.recovery_mode:
                            # Send all the remaining packets in bulk
                            for _ in range(RATE_IN_SEC - self.data_count):
                                data = np.random.normal(size=VEC_LENGTH)
                                conn.sendall(data.tobytes())
                                _ = conn.recv(1024)
                            self.data_count = RATE_IN_SEC
                            self.recovery_mode = False
                            while not self.new_period_start:
                                pass
                            continue

                        if self.lossy_mode and self.drop:
                            # Sleep for the average time it takes to send a packet to mimic packet loss.
                            time.sleep(avg_time)
                            self.drop = False
                        else:
                            # Normal sending mode
                            data = np.random.normal(size=VEC_LENGTH)
                            conn.sendall(data.tobytes())
                            _ = conn.recv(1024)
                            self.data_count += 1

                        # Adjust the wait time between sends
                        end = time.time_ns()
                        sending_time = (end - start) * NANO_TO_SEC
                        i += 1
                        if i == len(avg_times):
                            i = 0
                            init_mode = False
                        if init_mode:
                            avg_time = (avg_time * (i - 1) + sending_time) / float(i)
                        else:
                            avg_time -= avg_times[i] / len(avg_times)
                            avg_time += sending_time / len(avg_times)
                        avg_times[i] = sending_time
                        pause_between_sends = max(0.0, 0.999 * pause_between_sends +
                                                  0.001*(pause_between_sends - (avg_time - 1. / RATE_IN_SEC)))
                    conn.close()
            except ConnectionResetError:
                print("Client unexpectedly closed connection.")
                raise SystemExit(1)


def start_server(host, port, seconds_to_run, lossy_mode,  enable_recovery_mode):
    server = Server(host, port, seconds_to_run, lossy_mode,  enable_recovery_mode)
    server.send_data()