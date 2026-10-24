import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dsp-thread-profile.sh"


class DspThreadProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        (self.module / "logs").mkdir(parents=True)
        proc = self.root / "proc/vendor_sched"
        (proc / "groups/ta").mkdir(parents=True)
        (proc / "groups/fg").mkdir(parents=True)
        (proc / "groups/ta/set_task_group").touch()
        (proc / "groups/ta/set_proc_group").touch()
        (proc / "groups/fg/set_task_group").touch()
        (proc / "dump_task").write_text(
            "30362 James Audio DS fg 0 1024 0 1024 0x0 0 0x0 1\n"
        )
        task = self.root / "proc/30362"
        task.mkdir()
        (task / "comm").write_text("James Audio DS\n")
        (task / "status").write_text("Tgid:\t2913\n")
        (task / "stat").write_text("30362 (James Audio DS) S " + "0 " * 18 + "12345 0\n")
        host = self.root / "proc/2913"
        host.mkdir()
        (host / "maps").write_text("1000-2000 r-xp 00000000 00:01 1 /vendor/lib64/soundfx/libjamesdsp.so\n")
        profile = {
            "Profiles": [{
                "Name": "RealtimePerformance",
                "Actions": [{
                    "Name": "WriteFile",
                    "Params": {
                        "FilePath": "/proc/vendor_sched/groups/ta/set_task_group",
                        "ProcFilePath": "/proc/vendor_sched/groups/ta/set_proc_group",
                        "Value": "<pid>",
                        "LogFailures": "false",
                    },
                }],
            }]
        }
        (self.root / "vendor_task_profiles.json").write_text(json.dumps(profile, indent=2))
        self.calls = self.root / "profile-calls"
        mock_profile = self.root / "settaskprofile"
        mock_profile.write_text(
            "#!/bin/sh\n"
            f"echo \"$*\" >>'{self.calls}'\n"
            "[ \"$2\" = RealtimePerformance ] || exit 2\n"
            f"awk -v tid=\"$1\" '$1 == tid {{ $5 = \"ta\" }} {{ print }}' '{proc / 'dump_task'}' >'{proc / 'dump_task'}.new'\n"
            f"mv '{proc / 'dump_task'}.new' '{proc / 'dump_task'}'\n"
        )
        mock_profile.chmod(0o755)

    def run_once(self):
        env = {
            **os.environ,
            "JDSP_PROFILE_TEST_ROOT": str(self.root),
        }
        return subprocess.run(
            ["sh", str(SCRIPT), "--once", str(self.module)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_applies_only_the_vendor_defined_profile_and_records_restore(self):
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), "30362 RealtimePerformance\n")
        status = (self.module / "logs/dsp-thread-profile.status").read_text()
        self.assertEqual(status, "APPLIED profile=RealtimePerformance tid=30362 group=ta\n")
        self.assertEqual(
            (self.root / "proc/vendor_sched/groups/fg/set_task_group").read_text(),
            "30362\n",
        )
        self.assertIn("RESTORED tid=30362 group=fg", (self.module / "logs/dsp-thread-profile.log").read_text())

    def test_skips_generic_aosp_realtime_profile(self):
        (self.root / "vendor_task_profiles.json").write_text(json.dumps({
            "Profiles": [{
                "Name": "RealtimePerformance",
                "Actions": [{
                    "Name": "JoinCgroup",
                    "Params": {"Controller": "cpu", "Path": "rt"},
                }],
            }]
        }, indent=2))
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(
            (self.module / "logs/dsp-thread-profile.status").read_text(),
            "SKIPPED reason=vendor_realtime_profile_not_supported\n",
        )

    def test_skips_a_profile_with_additional_scheduler_actions(self):
        profile = json.loads((self.root / "vendor_task_profiles.json").read_text())
        profile["Profiles"][0]["Actions"].append({
            "Name": "JoinCgroup", "Params": {"Controller": "cpu", "Path": "rt"}
        })
        (self.root / "vendor_task_profiles.json").write_text(json.dumps(profile, indent=2))
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())

    def test_skips_duplicate_realtime_profile_names(self):
        profile = json.loads((self.root / "vendor_task_profiles.json").read_text())
        profile["Profiles"].append(profile["Profiles"][0])
        (self.root / "vendor_task_profiles.json").write_text(json.dumps(profile, indent=2))
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(
            (self.module / "logs/dsp-thread-profile.status").read_text(),
            "SKIPPED reason=vendor_realtime_profile_not_supported\n",
        )

    def test_does_not_reassign_a_thread_already_outside_foreground(self):
        dump = self.root / "proc/vendor_sched/dump_task"
        dump.write_text("30362 James Audio DS ta 0 1024 1 1024 0x0 0 0x0 1\n")
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())

    def test_same_thread_name_without_a_live_dsp_mapping_is_not_targeted(self):
        (self.root / "proc/2913/maps").write_text(
            "1000-2000 r-xp 00000000 00:01 1 /vendor/lib64/soundfx/libjamesdsp.so (deleted)\n"
        )
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())

    def test_reused_thread_id_is_not_restored_as_the_old_thread(self):
        mock = self.root / "settaskprofile"
        mock.write_text(mock.read_text() + f"echo '30362 (James Audio DS) S {'0 ' * 18}54321 0' >'{self.root / 'proc/30362/stat'}'\n")
        result = self.run_once()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), "30362 RealtimePerformance\n")
        self.assertEqual((self.root / "proc/vendor_sched/groups/fg/set_task_group").read_text(), "")


if __name__ == "__main__":
    unittest.main()
