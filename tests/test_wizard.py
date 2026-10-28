import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import pytest
from PySide6.QtWidgets import QApplication
import app as module


@pytest.fixture
def wizard(tmp_path):
    application=QApplication.instance() or QApplication([])
    window=module.Window(tmp_path)
    yield window
    window.close()


def test_usb_failure_does_not_advance(wizard,monkeypatch):
    calls=[]
    monkeypatch.setattr(wizard,'usb',lambda **kwargs:calls.append(kwargs))
    wizard.next_step()
    assert calls==[{'advance':True}] and wizard.pages.currentIndex()==0
    wizard.usb_advance=True
    wizard.on_event('usb_error','Allow debugging')
    assert not wizard.usb_ready and wizard.pages.currentIndex()==0


def test_usb_success_advances_and_active_session_locks_navigation(wizard):
    wizard.usb_advance=True
    wizard.on_event('usb','USB ready')
    assert wizard.usb_ready and wizard.pages.currentIndex()==1
    wizard.pages.setCurrentIndex(3);wizard.update_step();wizard.set_active(True)
    assert not wizard.back_button.isEnabled()
    wizard.previous_step();assert wizard.pages.currentIndex()==3
    wizard.set_active(False);assert wizard.back_button.isEnabled()


def test_display_apply_failure_blocks_next(wizard,monkeypatch):
    from types import SimpleNamespace
    wizard.pages.setCurrentIndex(1)
    monkeypatch.setattr(wizard,'target',lambda:SimpleNamespace(primary=False))
    monkeypatch.setattr(wizard,'apply_side',lambda:False)
    wizard.next_step();assert wizard.pages.currentIndex()==1


def test_window_and_four_steps(wizard):
    assert wizard.pages.count()==4 and not wizard.isMaximized()
    assert wizard.width()<=900 and wizard.height()<=700
    assert not hasattr(wizard,'beamer_status')


def test_launch_address_is_visible(wizard):
    wizard.pages.setCurrentIndex(3);wizard.update_step();wizard.show()
    QApplication.processEvents()
    assert '127.0.0.1' in wizard.summary.text()
    assert wizard.summary.height()>=wizard.summary.heightForWidth(wizard.summary.width())
