# spawns the segcache as one process and spawns the trace replay as another process
# inspiration: https://stackoverflow.com/questions/39258616/running-two-process-simultaneously
# USAGE: python3 performance_anaylysis.py

# TODO: wire up stop signal to kill admin thread? Brian
# TODO: figure out how to measure recovery/copy time

import os
import multiprocessing
import time
import signal
import subprocess
import telnetlib

pelikan = '/home/users/u6688826/pelikan' # TODO
rpc_perf = '/home/users/u6688826/rpc-perf' # TODO
cache_binary = pelikan+"/"+'target/release/pelikan_segcache_rs'
config = pelikan+"/"+'config/segcache_perf_analysis.toml'
trace = 'benchmarks/cluster052.zst'
replay_command = 'cargo run --release --bin rpc-replay -- --poolsize 100 --workers 4 --rate 10000000 --binary-trace --endpoint localhost:12321 --trace '+trace
admin_command = 'telnet localhost 9999'

# -------- Spawn Segcache as a non-blocking process ------------------------
cache_spawn = subprocess.Popen([cache_binary,config])
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
shutdown_start = time.time()
HOST = "localhost"
PORT = 9999
command = "stop"
print("about to connect")
admin_conn = telnetlib.Telnet(HOST, PORT)
admin_conn.set_debuglevel(2)
print("connected")
admin_conn.write(command.encode("ascii") + b"\r\n")
admin_conn.read_until(b"Connection closed by")
print("received ok")
admin_conn.close()

# ------ Manually terminate the cache --------------------------------------
# note - all but 1 threads are terminated. 
# So we need to manually terminate the cache.
# cache_spawn.kill()
shutdown_time = time.time() - shutdown_start
# ------ Statistics --------------------------------------------------------
print("Time to replay the cache: {}".format(replay_time))
print("Time to shutdown the cache: {}".format(shutdown_time))
