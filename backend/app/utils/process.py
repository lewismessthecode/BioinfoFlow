from __future__ import annotations

import psutil


def terminate_process_tree(pid: int, timeout: float = 5.0) -> bool:
    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return False

    children = process.children(recursive=True)
    for child in children:
        try:
            child.terminate()
        except psutil.Error:
            continue

    try:
        process.terminate()
    except psutil.Error:
        return False

    gone, alive = psutil.wait_procs([process, *children], timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            continue
    if alive:
        psutil.wait_procs(alive, timeout=timeout)
    return True
