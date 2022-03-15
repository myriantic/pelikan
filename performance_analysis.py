# spawns the segcache as one process and spawns the trace replay as another process
# inspiration: https://stackoverflow.com/questions/39258616/running-two-process-simultaneously
# USAGE: python3 performance_anaylysis.py

import os
import multiprocessing
import time
import signal

pelikan = '/home/users/u6632448/pelikan'
rpc_perf = '/home/users/u6632448/rpc-perf'

# spawn segcache
def spawn_cache():
    cache_binary = 'target/release/pelikan_segcache_rs'
    config = 'config/segcache_perf_analysis.toml'
    
    os.chdir(pelikan)
    os.system(cache_binary+' '+config)

# replays trace but sending the requests to the cache
def replay(cache_pid):
    print("Cache pid = {}".format(cache_pid))
    trace = 'benchmarks/cluster052_mini.zst'

    os.chdir(rpc_perf)
    start = time.time()
    # will execute until it is finished
    os.system('cargo run --release --bin rpc-replay -- --poolsize 100 --workers 4 --speed 1.0 --binary-trace --endpoint localhost:12321 --trace '+trace)
    replay_time = time.time() - start
    # connect to admin port
    os.system('telnet localhost 9999')
    # TODO: send stop (gracefully shutsdown cache if configured to do so)
    # TODO: trigger p1() to stop (which will stop our admin connection)
    os.kill(cache_pid, signal.SIGINT)

    print("Time to replay the cache: {}".format(replay_time))

if __name__ == '__main__':
    p1 = multiprocessing.Process(name='p1', target=spawn_cache)
    p1.start()
    p2 = multiprocessing.Process(name='p2', target=replay, args=(p1.pid,))
    p2.start()
    print("helo!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    # pid = p1.pid
    # os.kill(pid, signal.SIGINT)