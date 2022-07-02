# spawns the segcache as one process and spawns the trace replay as another process
# inspiration: https://stackoverflow.com/questions/39258616/running-two-process-simultaneously
# USAGE: python3 performance_anaylysis.py

import os
import multiprocessing
import time
import signal
import subprocess
import telnetlib

# Ignore Warnings
import warnings
warnings.filterwarnings("ignore")

# Directories
home = '/home/users/u6688826'
pelikan = home + '/pelikan' 
rpc_perf = home + '/rpc-perf'
cache_binary  = pelikan + "/target/release/pelikan_segcache_rs"
config_folder = pelikan + "/config/perf_analysis_configs"
output_folder = pelikan + "/outputs"

# Traces
trace_1 = 'benchmarks/cluster052.zst'
trace_2 = 'benchmarks/cluster052.zst'

# Commands
replay_command_1 = 'cargo run --release --bin rpc-replay -- --speed 1.0 --poolsize 100 --workers 4 --binary-trace --endpoint localhost:12321 --trace ' + trace_1
replay_command_2 = 'cargo run --release --bin rpc-replay -- --speed 1.0 --poolsize 100 --workers 4 --binary-trace --endpoint localhost:12321 --trace ' + trace_2

admin_command = 'telnet localhost 9999'

# print(replay_command)

# Parameters
HOST = "localhost"
PORT = 9999
stop  =  "stop".encode("ascii") + b"\r\n"
stats = "stats".encode("ascii") + b"\r\n"

for config in os.listdir(config_folder):

    config_path = config_folder + "/" + config

    output_file = f"{output_folder}/{config}_output.txt"

    ### Iteration 1 ###

    # -------- Spawn Segcache as a non-blocking process ------------------------
    print("Running Iteration 1:")

    cache_spawn = subprocess.Popen([cache_binary,config_path])

    # -------- Replay the trace on the cache as a blocking process -------------
    os.chdir(rpc_perf)
    # replay_start = time.time()

    # This sends cache requests to the server port
    replay = subprocess.Popen(replay_command_1.split())
    replay.wait()
    # replay_time = time.time() - replay_start

    # Open Admin Connection
    admin_conn = telnetlib.Telnet(HOST, PORT)
    admin_conn.set_debuglevel(2)

    # ------- Send stop signal to admin port -----------------------------------
    # gracefully shutsdown cache if configured to do so
    # shutdown_start = time.time() # move this down maybe

    # Tells admin to terminate
    admin_conn.write(stop)

    # Waits for admin to terminate
    while True:

        try:
            admin_conn.read_until(b"Connection closed by")

        except EOFError as _:
            print("Admin Thread Closed")
            break

    # shutdown_time = time.time() - shutdown_start

    ### Iteration 2 ###

    print("Running Iteration 2:")

    os.chdir(home)

    # -------- Spawn Segcache as a non-blocking process ------------------------

    cache_spawn = subprocess.Popen([cache_binary,config_path])
    # One idea for measuring copying is if you have a println!() in the segcache code, we should see it somewhere.
    # Somehow monitor for it

    # -------- Replay the trace on the cache as a blocking process -------------
    os.chdir(rpc_perf)
    replay_start = time.time()

    # This sends cache requests to the server port
    replay = subprocess.Popen(replay_command_2.split())
    replay.wait()
    replay_time = time.time() - replay_start

    # Open Admin 
    admin_conn = telnetlib.Telnet(HOST, PORT)
    admin_conn.set_debuglevel(2)

    # --- TESTS GOES HERE --- 

    # Requests Stats
    admin_conn.write(stats)

    # Get Stats, Read until "END"
    output = admin_conn.read_until("write 0\r\nEND\r\n".encode("ascii"))

    # Write Stats to File
    output_file = open(output_file, "w")
    output_file.write(output.decode("ascii"))
    output_file.close()

    # -----------------------

    # ------- Send stop signal to admin port -----------------------------------
    # gracefully shutsdown cache if configured to do so
    # shutdown_start = time.time() # move this down maybe

    # Tells admin to terminate
    admin_conn.write(stop)

    # Waits for admin to terminate
    while True:

        try:
            admin_conn.read_until(b"Connection closed by")

        except EOFError as _:
            print("Admin Thread Closed")
            break

    # shutdown_time = time.time() - shutdown_start

    # ------ Manually terminate the cache --------------------------------------
    # note - all but 1 threads are terminated. 
    # So we need to manually terminate the cache.
    # cache_spawn.kill()

    # ------ Statistics --------------------------------------------------------
    print("Time to   replay the cache: {}".format(replay_time))
    # print("Time to shutdown the cache: {}".format(shutdown_time))

    # ------ Write to File Here -------