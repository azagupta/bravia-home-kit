import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import tvkit


class SafetyTests(unittest.TestCase):
    def test_endpoint_rejects_shell_payloads_and_bad_ports(self):
        for value in ('example;touch /tmp/no:5555', 'host:0', 'host:65536', 'missingport', '-host:5555'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tvkit.validate_endpoint(value)
        self.assertEqual(tvkit.validate_endpoint('tv.example:5555'), 'tv.example:5555')

    def test_unknown_package_state_is_not_guessed(self):
        with self.assertRaises(RuntimeError):
            tvkit.enabled_state('User 0: installed=true')
        self.assertEqual(tvkit.enabled_state('User 0: installed=true enabled=0'), 0)

    def test_journal_is_saved_before_failed_disable(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'state.json'
            state={'packages': {'tv.samba.ssm': 0}, 'changed': []}
            def fail(*args):
                self.assertEqual(json.loads(path.read_text())['changed'], ['tv.samba.ssm'])
                raise RuntimeError('connection lost')
            with patch.object(tvkit, 'adb', side_effect=fail), self.assertRaises(RuntimeError):
                tvkit.change_package(path,state,'tv.samba.ssm')

    def test_restore_replays_exact_original_states(self):
        state={'changed':['tv.samba.ssm','com.sony.dtv.promos'],
               'packages':{'tv.samba.ssm':0,'com.sony.dtv.promos':1}}
        with patch.object(tvkit,'adb',return_value='ok') as adb:
            tvkit.restore_packages(state)
        self.assertEqual(adb.call_args_list[0].args,('shell','pm','enable','--user','0','com.sony.dtv.promos'))
        self.assertEqual(adb.call_args_list[1].args,('shell','pm','default-state','--user','0','tv.samba.ssm'))

    def test_cannot_overwrite_an_active_restore_point(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);state=folder/'state.json'
            state.write_text(json.dumps({'changed':['tv.samba.ssm']}))
            (folder/'latest-backup.txt').write_text(str(state))
            with patch.object(tvkit,'LOCAL',folder), self.assertRaises(RuntimeError):
                tvkit.backup()

    def test_standby_command_does_not_toggle_power(self):
        with patch.object(tvkit,'adb',return_value='ok') as adb:
            tvkit.key('off')
        adb.assert_called_once_with('shell','input','keyevent','KEYCODE_SLEEP')

    def test_restore_rejects_wrong_device_before_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); (folder/'backups').mkdir()
            path=folder/'backups'/'state.json'
            path.write_text(json.dumps({'device':{'serial':'different','model':'TV'}}))
            (folder/'latest-backup.txt').write_text(str(path))
            with patch.object(tvkit,'LOCAL',folder), patch.object(tvkit,'identity',return_value={'serial':'original','model':'TV'}), self.assertRaises(RuntimeError):
                tvkit.restore_journal()

    def test_restore_refuses_unmanaged_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'backups').mkdir();path=folder/'backups'/'state.json'
            identity={'serial':'TEST','model':'TV'}
            path.write_text(json.dumps({'device':identity,'packages':{'android':0},'changed':['android'],'home':'android/.Home'}))
            (folder/'latest-backup.txt').write_text(str(path))
            with patch.object(tvkit,'LOCAL',folder), patch.object(tvkit,'identity',return_value=identity), self.assertRaises(RuntimeError):
                tvkit.restore_journal()


if __name__=='__main__':
    unittest.main()
