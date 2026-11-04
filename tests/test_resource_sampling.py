import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jarvis.resource_sampling import MemorySampler, sample_memory


class MemorySamplingTests(unittest.TestCase):
    def process(self, proc, pid, parent, rss, pss):
        root = proc / str(pid)
        root.mkdir()
        fields = ['S', str(parent)] + ['0'] * 20
        fields[21] = str(rss)
        (root / 'stat').write_text(f'{pid} (name with spaces) ' + ' '.join(fields))
        if pss is not None:
            (root / 'smaps_rollup').write_text(f'Rss: 999 kB\nPss: {pss} kB\n')

    def test_tree_counts_descendants_and_explicit_daemon_without_unrelated_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / 'meminfo').write_text('MemTotal: 8000 kB\nMemAvailable: 3000 kB\n')
            self.process(proc, 100, 1, 100, 10)
            self.process(proc, 101, 100, 200, 20)
            self.process(proc, 102, 101, 300, 30)
            self.process(proc, 200, 1, 400, 40)
            self.process(proc, 300, 1, 9000, 9000)
            value = sample_memory({100, 200, 999}, proc=proc)
            self.assertEqual(value['tree_rss_kib'], 1000 * os.sysconf('SC_PAGE_SIZE') // 1024)
            self.assertEqual(value['tree_pss_kib'], 100)
            self.assertEqual(value['system_used_kib'], 5000)
            self.assertEqual(value['process_count'], 4)
            self.assertEqual(value['missing_root_pids'], [999])

    def test_missing_pss_is_reported_instead_of_partial_total(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / 'meminfo').write_text('MemTotal: 8000 kB\nMemAvailable: 3000 kB\n')
            self.process(proc, 100, 1, 100, 10)
            self.process(proc, 101, 100, 200, None)
            self.assertIsNone(sample_memory({100}, proc=proc)['tree_pss_kib'])

    def test_sampler_releases_thread_on_failure_and_reports_coverage(self):
        with self.assertRaises(RuntimeError):
            with MemorySampler() as monitor:
                raise RuntimeError('generation failed')
        self.assertFalse(monitor.thread.is_alive())
        self.assertGreaterEqual(monitor.result['sample_count'], 2)
        self.assertGreater(monitor.result['peak_tree_rss_kib'], 0)
        self.assertNotIn('command_line', monitor.result)

    def test_sample_errors_are_visible(self):
        with patch('jarvis.resource_sampling.sample_memory', side_effect=PermissionError):
            with MemorySampler() as monitor:
                pass
        self.assertEqual(monitor.result['sample_count'], 0)
        self.assertEqual(monitor.result['errors'], 2)
