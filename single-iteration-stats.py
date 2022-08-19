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
home     = '/home/users/u6688826'
pelikan  = home + '/pelikan' 
rpc_perf = home + '/rpc-perf'
cache_binary  = pelikan + "/target/release/pelikan_segcache_rs"
config_folder = pelikan + "/config/perf_analysis_configs"
output_folder = pelikan + "/outputs"

# Traces
trace_1 = 'benchmarks/cluster52.0.zst'
trace_2 = 'benchmarks/cluster52.1.zst'

mini_trace = 'benchmarks/cluster052_mini'

key_string = b'check here that cache data and metadata has been sourced'

# Commands
replay_command_1 = 'cargo run --release --bin rpc-replay -- --rate 10000000 --poolsize 100 --workers 4 --endpoint localhost:12321 --trace ' + trace_2
admin_command = 'telnet localhost 9999'

# print(replay_command)

# Parameters
HOST = "localhost"
PORT = 9999
stop  =  "stop".encode("ascii") + b"\r\n"
stats = "stats".encode("ascii") + b"\r\n"

# Change Path to Pelikan and Build
os.chdir(pelikan)
os.system(f"cargo build --release")

for config in os.listdir(config_folder):

    config_name          = config[:-4]
    config_path          = f"{config_folder}/{config}"
    output_file          = f"{output_folder}/output_{config_name}.txt"
    stats_output_file    = f"{output_folder}/stat_output_{config_name}.txt"
    gerneral_output_file = f"{output_folder}/general_output_{config_name}.txt"

    ### Iteration 1 ###

    # -------- Spawn Segcache as a non-blocking process ------------------------
    print("Spawning Segcache")

    cache_spawn = subprocess.Popen([cache_binary, config_path], stdout = subprocess.PIPE)
    print("Cache Spawned - Waiting for Cache to Start")

    print(cache_binary, config_path)

    cache_spawn_time = time.time()

    # Wait until Cache is Start up
    while True:
        output = cache_spawn.stdout.readline()
        if key_string in output.strip():
            break

    cache_start_up_time = time.time() - cache_spawn_time
    print(f"Cache Started - Startup Time Took {round(cache_start_up_time, 5)} seconds") 

    # Open Admin Connection (Since Cache is Active)
    admin_conn = telnetlib.Telnet(HOST, PORT)
    admin_conn.set_debuglevel(2)

    # -------- Replay the trace on the cache as a blocking process -------------
    os.chdir(rpc_perf)

    print("Starting Replay...")

    # This sends cache requests to the server port
    replay = subprocess.Popen(replay_command_1.split(), stdout = subprocess.PIPE)
    poll = replay.poll()

    output_file       = open(output_file, "a+")
    stats_output_file = open(stats_output_file, "a+")

    replay_start = time.time()

    # # Wait until Cache is Start up
    while True:
        output = replay.stdout.readline()
        if output == b'' and replay.poll() is not None:
            break

        if output:
            output_file.write(output.decode("ascii"))

        if b"-----" in output:

            # Requests Stats
            admin_conn.write(stats)

            # Get Stats, Read until "END"
            output_stats = admin_conn.read_until("write 0\r\nEND\r\n".encode("ascii"))

            # Write Stats to File
            stats_output_file.write(output_stats.decode("ascii"))

    output_file.close()
    stats_output_file.close()

    print("rpc_perf finished")
    replay_time = time.time() - replay_start

    print("Shutting Down Cache")
    
    # ------- Send stop signal to admin port -----------------------------------
    # gracefully shutsdown cache if configured to do so
    # shutdown_start = time.time() # move this down maybe

    # Tells admin to terminate
    admin_conn.write(stop)

    shut_down_start = time.time()

    # Waits for admin to terminate
    while True:

        try:
            admin_conn.read_until(b"Connection closed by")

        except EOFError as _:
            print("Admin Thread Closed")
            break

    shut_down_time = time.time() - shut_down_start

    # Write General Information into File

    gerneral_output_file = open(gerneral_output_file, "a+")

    gerneral_output_file.write(f"Start Up Time: {cache_start_up_time}\n")
    gerneral_output_file.write(f"  Replay Time: {replay_time}\n")
    gerneral_output_file.write(f"Shutdown Time: {shut_down_time}\n")

    gerneral_output_file.close()

exit()