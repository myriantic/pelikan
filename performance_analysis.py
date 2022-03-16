# spawns the segcache as one process and spawns the trace replay as another process
# inspiration: https://stackoverflow.com/questions/39258616/running-two-process-simultaneously
# USAGE: python3 performance_anaylysis.py

# TODO: wire up stop signal to kill admin thread?
# TODO: figure out how to measure recovery/copy time

import os
import multiprocessing
import time
import signal
import subprocess

pelikan = '/home/users/u6632448/pelikan'
rpc_perf = '/home/users/u6632448/rpc-perf'

# spawn segcache
def spawn_cache():
    cache_binary = 'target/release/pelikan_segcache_rs'
    config = 'config/segcache_perf_analysis.toml'
    
    os.chdir(pelikan)
    os.system(cache_binary+' '+config)


# replays trace but sending the requests to the cache
def replay():
    trace = 'benchmarks/cluster052.zst'

    os.chdir(rpc_perf)
    replay_start = time.time()
    # will execute until it is finished
    os.system('cargo run --release --bin rpc-replay -- --poolsize 100 --workers 4 --speed 1.0 --binary-trace --endpoint localhost:12321 --trace '+trace)
    replay_end = time.time()
    replay_time = replay_end - replay_start
    # send stop signal to admin port (gracefully shutsdown cache if configured to do so)
    os.system('{ echo "stop"; sleep 1; exit; } | telnet localhost 9999')
    # note - all but 1 threads are terminated. 
    # So we need to manually terminate the cache.

    #os.system("kill -9 {}".format(cache_pid))
    p1.terminate()

    print("Time to replay the cache: {}".format(replay_time))


cache_binary = pelikan+"/"+'target/release/pelikan_segcache_rs'
config = pelikan+"/"+'config/segcache_perf_analysis.toml'
trace = 'benchmarks/cluster052.zst'
replay_command = 'cargo run --release --bin rpc-replay -- --poolsize 100 --workers 4 --speed 1.0 --binary-trace --endpoint localhost:12321 --trace '+trace
# spawn segcache
cache_spawn = subprocess.Popen([cache_binary,config])
# replay the trace
os.chdir(rpc_perf)
replay_start = time.time()
replay = subprocess.Popen(replay_command.split())
replay_time = time.time() - replay_start
# send stop signal to admin port (gracefully shutsdown cache if configured to do so)
os.system('{ echo "stop"; sleep 1; exit; } | telnet localhost 9999')
# note - all but 1 threads are terminated. 
# So we need to manually terminate the cache.
cache_spawn.kill()
print("Time to replay the cache: {}".format(replay_time))

# if __name__ == '__main__':
#     p1 = subprocess.run([''])
#     p1.start()
#     p2 = multiprocessing.Process(name='p2', target=replay)
#     p2.start()