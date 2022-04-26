# spawns the segcache as one process and spawns the trace replay as another process
# inspiration: https://stackoverflow.com/questions/39258616/running-two-process-simultaneously
# USAGE: python3 performance_anaylysis.py

# TODO: figure out how to measure recovery/copy time

import os
import multiprocessing
import time
import signal
import subprocess
import telnetlib


pelikan = '/home/users/u6688826/pelikan' 
rpc_perf = '/home/users/u6688826/rpc-perf'
cache_binary = pelikan+"/"+'target/release/pelikan_segcache_rs'
config_folder = pelikan + "/config/perf_analysis_configs/"

trace = 'benchmarks/cluster052.zst'
replay_command = 'cargo run --release --bin rpc-replay -- --poolsize 100 --workers 4 --speed 1.0 --binary-trace --endpoint localhost:12321 --trace '+trace
admin_command = 'telnet localhost 9999'

HOST = "localhost"
PORT = 9999
command = "stop"

for config in os.listdir(config_folder):

    config_path = config_folder + config
    print(config_path)

    # -------- Spawn Segcache as a non-blocking process ------------------------
    cache_spawn = subprocess.Popen([cache_binary,config_path])
    # One idea for measuring copying is if you have a println!() in the segcache code, we should see it somewhere.
    # Somehow monitor for it

    # -------- Replay the trace on the cache as a blocking process -------------
    os.chdir(rpc_perf)
    replay_start = time.time()

    # This sends cache requests to the server port
    replay = subprocess.Popen(replay_command.split())
    replay.wait()
    replay_time = time.time() - replay_start

    # ------- Send stop signal to admin port -----------------------------------
    # gracefully shutsdown cache if configured to do so
    shutdown_start = time.time() # move this down maybe
    admin_conn = telnetlib.Telnet(HOST, PORT)
    admin_conn.set_debuglevel(2)

    # Main Test Cases Go here



    # -----------------------

    # Tells admin to terminate
    admin_conn.write(command.encode("ascii") + b"\r\n")

    # Waits for admin to terminate
    while True:

        try:
            admin_conn.read_until(b"Connection closed by")

        except EOFError as _:
            print("Admin Thread Closed")
            break

    # ------ Manually terminate the cache --------------------------------------
    # note - all but 1 threads are terminated. 
    # So we need to manually terminate the cache.
    # cache_spawn.kill()

    shutdown_time = time.time() - shutdown_start
    # ------ Statistics --------------------------------------------------------
    print("Time to   replay the cache: {}".format(replay_time))
    print("Time to shutdown the cache: {}".format(shutdown_time))