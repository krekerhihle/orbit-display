"""Exercise the real USB helper's user-visible success and failure paths."""
from types import SimpleNamespace
import pytest
import integrations


@pytest.fixture
def usb(tmp_path, monkeypatch):
    adb=tmp_path/'tools/platform-tools/adb.exe'
    adb.parent.mkdir(parents=True)
    adb.touch()
    monkeypatch.setattr(integrations,'bundle_root',lambda:tmp_path)
    calls=[]
    responses=[SimpleNamespace(returncode=0,stdout='List of devices attached\nphone\tdevice\n',stderr=''),
               SimpleNamespace(returncode=0,stdout='',stderr='')]
    def run(command,**options):
        calls.append((command,options))
        return responses.pop(0)
    monkeypatch.setattr(integrations.subprocess,'run',run)
    return adb,calls,responses


def test_ready_message_and_utf8_subprocess(usb):
    adb,calls,_=usb
    assert integrations.prepare_usb()=="USB готовий. На Android оберіть USB (127.0.0.1)."
    assert calls[1][0]==[str(adb),'-s','phone','reverse','tcp:48620','tcp:48620']
    assert all(options['encoding']=='utf-8' for _,options in calls)


def test_missing_adb_message(usb):
    adb,_,_=usb;adb.unlink()
    with pytest.raises(OSError,match='^Не знайдено tools/platform-tools/adb.exe'):
        integrations.prepare_usb()


def test_no_device_message(usb):
    _,_,responses=usb;responses[0].stdout='List of devices attached\n'
    with pytest.raises(OSError,match="^Під'єднайте USB, увімкніть налагодження через USB"):
        integrations.prepare_usb()


def test_multiple_devices_message(usb):
    _,_,responses=usb;responses[0].stdout+='other\tdevice\n'
    with pytest.raises(OSError,match='^Залиште підключеним один Android-пристрій.$'):
        integrations.prepare_usb()


def test_failed_reverse_is_not_reported_as_ready(usb):
    _,_,responses=usb;responses[1]=SimpleNamespace(returncode=1,stdout='',stderr='Помилка ADB')
    with pytest.raises(OSError,match='^Помилка ADB$'):integrations.prepare_usb()
