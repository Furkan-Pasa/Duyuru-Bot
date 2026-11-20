"""DuyuruScheduler.start() zamanlama testleri."""

import unittest

from tests.support import SchedulerTestCase, make_site


def start_paused(scheduler):
    """Görevleri ekler ama zamanlayıcıyı duraklatılmış başlatır (görevler çalışmaz)."""
    real_start = scheduler.scheduler.start
    scheduler.scheduler.start = lambda: real_start(paused=True)
    scheduler.start()
    try:
        return {job.id: job for job in scheduler.scheduler.get_jobs()}
    finally:
        scheduler.scheduler.shutdown(wait=False)


class TestSchedulerJobs(SchedulerTestCase):
    def test_start_adds_single_job_per_site(self):
        scheduler = self.make_scheduler(make_site('site_a', 'Site A'), make_site('site_b', 'Site B'))

        jobs = start_paused(scheduler)

        self.assertEqual(set(jobs), {'check_site_a', 'check_site_b'})

    def test_jobs_cannot_overlap(self):
        jobs = start_paused(self.make_scheduler(make_site('site_a', 'Site A')))

        job = jobs['check_site_a']
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)

    def test_first_runs_are_staggered(self):
        jobs = start_paused(self.make_scheduler(make_site('site_a', 'Site A'), make_site('site_b', 'Site B')))

        first_a = jobs['check_site_a'].next_run_time
        first_b = jobs['check_site_b'].next_run_time
        self.assertIsNotNone(first_a)
        self.assertIsNotNone(first_b)
        self.assertGreater(first_b, first_a)

    def test_start_without_scrapers_adds_no_jobs(self):
        scheduler = self.make_scheduler(make_site(enabled=False))

        scheduler.start()

        self.assertEqual(scheduler.scheduler.get_jobs(), [])
        self.assertFalse(scheduler.scheduler.running)


if __name__ == '__main__':
    unittest.main()
