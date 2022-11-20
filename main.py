from server import start_server
from client import start_client
import argparse
from multiprocessing import Process


HOST = "127.0.0.1"
PORT = 65432
DEFAULT_SECONDS_TO_RUN = 300
DEFAULT_RESULTS_FILE = "results.txt"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-seconds_to_run", required=False, help="For how many seconds to run the program", type=int,
                        default=DEFAULT_SECONDS_TO_RUN)
    parser.add_argument("-lossy_mode", help="Enable lossy mode", type=bool, default=False, required=False)
    parser.add_argument("-recovery_mode", help="Enable recovery mode. Will forcibly send data in bulk if the sending "
                                               "rate of the currect second is too low.", type=bool, default=False,
                        required=False)
    parser.add_argument("-results_file", help="The name of the file to output the results to. Will erase the file if "
                                              "already exists.", type=str, default=DEFAULT_RESULTS_FILE,
                        required=False)
    args = parser.parse_args()
    start_server_process = Process(target=start_server, args=(HOST, PORT, args.seconds_to_run, args.lossy_mode,
                                                              args.recovery_mode))
    start_client_process = Process(target=start_client, args=(HOST, PORT, args.lossy_mode, args.results_file))
    start_server_process.start()
    start_client_process.start()
