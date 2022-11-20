import socket
from threading import Timer, Lock
import numpy as np
import time
from scipy.stats import norm
import os


NANO_TO_SEC = 1e-9
RATE_SERIES_LEN = 20
DATA_MATRIX_LEN = 100
INPUT_VECTOR_LEN = 50


class Client:

    def __init__(self, host: str, port: int, lossy_mode: bool, results_file_name: str):
        self.host: str = host
        self.port: int = port
        self.lossy_mode: bool = lossy_mode
        self.data_count: int = 0    # The amount of packets received in the current time period (this second)
        # Aggregates series of rates in Hz, the results mean and std of rates are calculated on this array.
        self.rate_series = np.zeros(RATE_SERIES_LEN)
        self.rate_series_idx: int = 0

        # The matrix to aggregate the incoming vectors
        self.data_matrix = np.zeros((DATA_MATRIX_LEN, INPUT_VECTOR_LEN))
        self.data_matrix_empty_idx: int = 0
        # The mean of the data matrix across the temporal dimension.
        # This value is stored for recovery in lossy mode.
        self.matrix_mean = np.zeros(INPUT_VECTOR_LEN)
        # The var of the data matrix across the temporal dimension.
        # This value is stored for recovery in lossy mode.
        self.matrix_std = np.ones(INPUT_VECTOR_LEN)

        self.results_file_name: str = results_file_name
        if os.path.isfile(self.results_file_name):
            os.remove(self.results_file_name)
        self.output_file_lock = Lock()
        # The amount of packets lost during the current time period in lossy mode
        self.lost_this_sec: int = 0

    def print_rate_(self):
        rate_measure = Timer(1, self.print_rate_)
        rate_measure.setDaemon(True)
        rate_measure.start()
        # Recover during lossy mode.
        if self.lossy_mode:
            self.data_count += self.lost_this_sec
            self.lost_this_sec = 0

        self.rate_series[self.rate_series_idx] = self.data_count
        self.rate_series_idx += 1
        print("Data is acquired at the rate of", self.data_count, "Hz")

        # Output the rate stats to the results file
        if self.rate_series_idx == RATE_SERIES_LEN:
            self.output_file_lock.acquire()
            with open(self.results_file_name, 'a') as f:
                f.write("Data acquisition rate series: \n" + str(self.rate_series) + '\n')
                f.write('Rate mean: ' + str(np.mean(self.rate_series)) + ', rate std: ' +
                        str(np.std(self.rate_series)) + '\n\n')
            self.output_file_lock.release()
            self.rate_series_idx = 0
        self.data_count = 0

    def maybe_output_data_stats_(self):
        if self.data_matrix_empty_idx == DATA_MATRIX_LEN:
            self.matrix_mean = np.mean(self.data_matrix, axis=0)
            self.matrix_std = np.std(self.data_matrix, axis=0)
            self.output_file_lock.acquire()
            with open(self.results_file_name, 'a') as f:
                f.write("Data matrix mean:\n" + str(self.matrix_mean) + "\n\nData matrix std:\n" +
                        str(self.matrix_std) + '\n\n')
            self.output_file_lock.release()
            self.data_matrix_empty_idx = 0

    def gather_data_(self, data_vec, is_loss=False):
        # is_loss: Indicates whether the last packet was lost
        if is_loss:
            # Generate a random vector according to mean and std of previous vectors
            self.data_matrix[self.data_matrix_empty_idx] = np.random.normal(self.matrix_mean, self.matrix_std)
            self.data_matrix_empty_idx += 1
            self.maybe_output_data_stats_()
        self.data_matrix[self.data_matrix_empty_idx] = data_vec
        self.data_matrix_empty_idx += 1
        self.maybe_output_data_stats_()

    def receive_data(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.host, self.port))
            prev_recv_time = time.time()
            # Stores non zero values of transmission times. Only used during lossy mode.
            recv_deltas = np.zeros(1000)
            recv_deltas_idx = 0
            rate_measure = Timer(1, self.print_rate_)
            rate_measure.setDaemon(True)
            rate_measure.start()
            init_mode = True    # Indicates that not enough data was gathered for accurate stats.
            try:
                while True:
                    data = s.recv(1024)
                    # The server finished sending.
                    if not data:
                        return
                    s.sendall(str.encode("ACK"))
                    lossy = False
                    if self.lossy_mode:
                        recv_time = time.time()
                        recv_delta = time.time() - prev_recv_time
                        if recv_delta > 0:
                            recv_deltas[recv_deltas_idx] = recv_delta
                            recv_deltas_idx += 1
                            if recv_deltas_idx == recv_deltas.size:
                                recv_deltas_idx = 0
                                init_mode = False
                        prev_recv_time = recv_time
                        lossy_cond = False
                        if not init_mode:
                            lossy_cond = norm.cdf(recv_delta, np.mean(recv_deltas), np.std(recv_deltas)) > 0.996
                        elif recv_deltas_idx > 1:
                            lossy_cond = norm.cdf(recv_delta, np.mean(recv_deltas[:recv_deltas_idx]),
                                                  np.std(recv_deltas[:recv_deltas_idx])) > 0.9995
                        if lossy_cond:
                            lossy = True
                            self.lost_this_sec += 1
                            print("WARNING: PACKET LOSS!")
                    self.gather_data_(np.frombuffer(data), lossy)
                    self.data_count += 1
            except ConnectionResetError:
                print("Server unexpectedly closed connection.")
                raise SystemExit(1)


def start_client(host, port, lossy_mode, results_file):
    client = Client(host, port, lossy_mode, results_file)
    client.receive_data()