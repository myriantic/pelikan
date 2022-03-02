# spawns the segcache as one process and spawns the trace replay as another process
# inspiration: https://stackoverflow.com/questions/39258616/running-two-process-simultaneously
# USAGE: python3 performance_anaylysis.py

import os
import multiprocessing
import time

# spawn segcache
def spawn_cache():
    os.chdir('/home/users/u6632448/pelikan')
    os.system('target/release/pelikan_segcache_rs config/segcache_perf_analysis.toml')

# replays trace but sending the requests to the cache
def replay():
    os.chdir('/home/users/u6632448/rpc-perf')
    start = time.time()
    # will execute until it is finished
    os.system('cargo run --release --bin rpc-replay -- --poolsize 100 --workers 4 --speed 1.0 --binary-trace --endpoint localhost:12321 --trace benchmarks/cluster052.zst')
    replay_time = time.time() - start
    # TODO: implement actual shutdown signal in segcache and send shutdown signal to cache
    print("Time to replay the cache: {}".format(replay_time))

if __name__ == '__main__':
    p1 = multiprocessing.Process(name='p1', target=spawn_cache)
    p2 = multiprocessing.Process(name='p2', target=replay)
    p1.start()
    p2.start()