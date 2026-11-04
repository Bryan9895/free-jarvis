"""Linux process-tree RAM samples, without command lines or private content."""
import os
from pathlib import Path
from threading import Event, Thread


def sample_memory(roots, *, proc=Path('/proc')):
    processes = {}
    page_kib = os.sysconf('SC_PAGE_SIZE') // 1024
    for directory in proc.iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            fields = (directory / 'stat').read_text().rsplit(') ', 1)[1].split()
            processes[int(directory.name)] = (int(fields[1]), int(fields[21]) * page_kib)
        except (OSError, ValueError, IndexError):
            continue
    selected = set(roots) & processes.keys()
    while True:
        children = {pid for pid, (parent, _) in processes.items() if parent in selected}
        expanded = selected | children
        if expanded == selected:
            break
        selected = expanded
    pss = 0
    pss_complete = bool(selected)
    for pid in selected:
        try:
            fields = (proc / str(pid) / 'smaps_rollup').read_text().splitlines()
            pss += next(int(line.split()[1]) for line in fields if line.startswith('Pss:'))
        except (OSError, ValueError, StopIteration):
            pss_complete = False
    memory = {}
    for line in (proc / 'meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable'):
            memory[key] = int(value.split()[0])
    return {'tree_rss_kib': sum(processes[pid][1] for pid in selected),
            'tree_pss_kib': pss if pss_complete else None, 'process_count': len(selected),
            'mem_available_kib': memory.get('MemAvailable'),
            'system_used_kib': memory['MemTotal'] - memory['MemAvailable']
                if {'MemTotal', 'MemAvailable'} <= memory.keys() else None,
            'missing_root_pids': sorted(set(roots) - processes.keys())}


class MemorySampler:
    def __init__(self, extra_pids=(), *, interval=.05):
        self.roots = {os.getpid(), *extra_pids}
        self.interval = interval
        self.done = Event()
        self.thread = None
        self.result = {'sample_count': 0, 'errors': 0, 'interval_s': interval,
            'peak_tree_rss_kib': None, 'peak_tree_pss_kib': None, 'peak_process_count': 0,
            'min_mem_available_kib': None, 'peak_system_used_kib': None,
            'missing_root_pids': [], 'pss_complete': True,
            'scope': 'Current process and descendants, plus explicitly supplied daemon PIDs. External daemons excluded unless supplied.',
            'limits': 'Sampled peaks; short-lived allocations can be missed. Summed RSS can double-count shared pages; PSS is preferred when available. No physical audio measured.'}

    def _sample(self):
        try:
            value = sample_memory(self.roots)
        except (OSError, ValueError):
            self.result['errors'] += 1
            self.result['pss_complete'] = False
            return
        self.result['sample_count'] += 1
        for source, target in (('tree_rss_kib', 'peak_tree_rss_kib'),
                ('tree_pss_kib', 'peak_tree_pss_kib'), ('process_count', 'peak_process_count'),
                ('system_used_kib', 'peak_system_used_kib')):
            if value[source] is not None:
                self.result[target] = max(self.result[target] or 0, value[source])
        if value['mem_available_kib'] is not None:
            previous = self.result['min_mem_available_kib']
            self.result['min_mem_available_kib'] = min(value['mem_available_kib'], previous) if previous is not None else value['mem_available_kib']
        if value['tree_pss_kib'] is None:
            self.result['pss_complete'] = False
        self.result['missing_root_pids'] = sorted(set(self.result['missing_root_pids']) | set(value['missing_root_pids']))

    def __enter__(self):
        self._sample()
        def watch():
            while not self.done.wait(self.interval):
                self._sample()
        self.thread = Thread(target=watch, name='jarvis-ram-sampler', daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        self.thread.join()
        self._sample()
        if not self.result['pss_complete']:
            self.result['peak_tree_pss_kib'] = None
