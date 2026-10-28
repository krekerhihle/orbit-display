import ctypes
import logging
import os
from pathlib import Path
import sys
import threading

try: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception: pass

from PySide6.QtCore import Qt, Signal, QObject, QTimer, QRectF, QSettings, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QDesktopServices, QIcon, QFontDatabase
from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QFrame, QTabWidget, QMessageBox, QFileDialog, QScrollArea, QStackedWidget)
from display import displays, move_display, restore_display, supported_modes, set_display_mode
from server import Server
from integrations import prepare_usb, bundle_root, USB_READY

STYLE = """
QWidget { background: #101010; color: #f5f5f5; font: 10pt 'Segoe UI'; }
QLabel#muted { color: #aaaaaa; }
QLabel#eyebrow { color: #ffffff; font-size: 10pt; font-weight: 700; }
QLabel#title { font-size: 23pt; font-weight: 700; }
QLabel#pin { font: 700 30pt 'Consolas'; color: #ffffff; }
QFrame#card { background: #191919; border: 1px solid #303030; border-radius: 16px; }
QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }
QPushButton { background: #272727; padding: 9px 16px; border: 1px solid #444444; border-radius: 9px; font-weight: 600; }
QPushButton:hover { background: #383838; }
QPushButton:disabled { color: #777777; background: #202020; }
QPushButton#primary { background: #ffffff; color: #101010; border: none; }
QPushButton#primary:hover { background: #dddddd; }
QPushButton:checked { background: #484848; border: 1px solid #ffffff; }
QComboBox { background: #222222; border: 1px solid #444444; border-radius: 8px; padding: 7px; min-height: 20px; }
QComboBox QAbstractItemView { background: #222222; selection-background-color: #555555; }
QCheckBox { spacing: 9px; padding: 5px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QTabWidget::pane { border: none; }
QTabBar::tab { color: #aaaaaa; padding: 12px 24px; margin-right: 8px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #ffffff; }
QScrollArea { border: none; }
QToolTip { background: #272727; color: white; border: 1px solid #ffffff; padding: 8px; }
"""


def label(text, name=None, wrap=True):
    obj = QLabel(text)
    obj.setWordWrap(wrap)
    if name: obj.setObjectName(name)
    return obj


def button(text, action, primary=False):
    obj = QPushButton(text)
    if primary: obj.setObjectName("primary")
    obj.clicked.connect(action)
    return obj


def card():
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(8)
    return widget, layout


def scroll_page(page):
    page.setMinimumWidth(560)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    return scroll


class Events(QObject):
    message = Signal(str, str)


class Arrangement(QWidget):
    def __init__(self):
        super().__init__()
        self.side = "right"
        self.setMinimumHeight(100)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width()/2, self.height()/2
        offsets = {"right":(113,0),"left":(-113,0),"top":(0,-73),"bottom":(0,73)}
        dx,dy = offsets[self.side]
        primary = QRectF(cx-65-dx/2, cy-39-dy/2,130,78)
        phone = QRectF(cx-40+dx/2,cy-26+dy/2,80,52)
        p.setPen(QPen(QColor("#555555"),1))
        p.setBrush(QColor("#282828"))
        p.drawRoundedRect(primary,8,8)
        p.setPen(QColor("#f5f5f5"))
        p.drawText(primary,Qt.AlignCenter,"01\nНоутбук")
        p.setBrush(QColor("#383838"))
        p.setPen(QPen(QColor("#ffffff"),2))
        p.drawRoundedRect(phone,8,8)
        p.drawText(phone,Qt.AlignCenter,"02\nAndroid")


class Window(QMainWindow):
    def __init__(self, data_dir=None):
        super().__init__()
        self.setWindowTitle("Orbit Display")
        assets=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets'
        self.setWindowIcon(QIcon(str(assets/'orbit.ico')))
        self.setMinimumSize(680, 520)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(900, available.width()-60), min(700, available.height()-70))
        self.usb_ready = False
        self.usb_pending = False
        self.settings = QSettings("OrbitDisplay", "OrbitDisplay")
        self.data_dir = Path(data_dir or Path(os.environ["LOCALAPPDATA"])/"OrbitDisplay")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=self.data_dir/"orbit.log", level=logging.INFO, format="%(asctime)s %(message)s")
        self.events = Events()
        self.events.message.connect(self.on_event)
        self.server = Server(self.data_dir, self.events.message.emit)
        self.originals = {}
        self.mode_catalog = []
        self.initialized_displays = set()
        self.active = False
        self.screens = []
        root = QWidget()
        main = QVBoxLayout(root)
        main.setContentsMargins(24,18,24,18)
        main.setSpacing(10)
        header = QHBoxLayout()
        header.addWidget(label("ORBIT / DISPLAY", "eyebrow"))
        header.addStretch()
        self.state = label("Налаштуймо твій простір", "muted",False)
        header.addWidget(self.state)
        main.addLayout(header)
        self.progress = label("", "muted")
        main.addWidget(self.progress)
        self.pages = QStackedWidget()
        for page in (self.connection_page(),self.display_page(),self.quality_page(),self.launch_page()):
            self.pages.addWidget(scroll_page(page))
        main.addWidget(self.pages,1)
        self.status = label("Почнімо зі способу підключення телефона.", "muted")
        self.status.setMinimumHeight(36)
        main.addWidget(self.status)
        footer = QHBoxLayout()
        self.back_button = button("← Назад", self.previous_step)
        footer.addWidget(self.back_button)
        self.update_button=button("Оновлення · автоматично",self.install_update)
        self.update_button.setEnabled(False)
        footer.addWidget(self.update_button)
        footer.addStretch()
        self.next_button = button("Далі →", self.next_step, True)
        footer.addWidget(self.next_button)
        main.addLayout(footer)
        self.update_step()
        self.setCentralWidget(root)
        self.refresh()
        self.transport_changed()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.update_file=None;self.update_busy=False
        if len(sys.argv)==1:
            self.update_timer=QTimer(self);self.update_timer.timeout.connect(self.check_updates);self.update_timer.start(300000)
            QTimer.singleShot(3000,self.check_updates)

    def check_updates(self):
        if self.update_busy or self.update_file:return
        self.update_busy=True
        def work():
            try:
                from updater import check_and_download
                path=check_and_download(self.data_dir/'updates')
                self.events.message.emit('update_ready',str(path) if path else '')
            except Exception:self.events.message.emit('update_ready','')
        threading.Thread(target=work,daemon=True).start()

    def install_update(self):
        if not self.update_file:return
        if self.active:
            self.error('Зупини сеанс перед встановленням оновлення.');return
        import subprocess
        subprocess.Popen([self.update_file,'/SILENT','/NORESTART','/DIR='+str(bundle_root())])
        self.close()

    def page(self, title, subtitle):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0,8,0,8)
        outer.setSpacing(12)
        outer.addWidget(label(title,"title"))
        outer.addWidget(label(subtitle,"muted"))
        return page,outer

    def connection_page(self):
        page,outer = self.page("01. З'єднай пристрої.","Обери кабель або спільну мережу. Ми перевіримо USB перед наступним кроком.")
        panel,a = card()
        self.transport = QComboBox()
        self.transport.addItems(["Wi-Fi / USB-модем","USB-кабель · рекомендовано"])
        self.transport.setCurrentIndex(1)
        self.transport.currentIndexChanged.connect(self.transport_changed)
        a.addWidget(self.transport)
        self.connection_help = label("","muted")
        a.addWidget(self.connection_help)
        self.usb_button = button("Перевірити USB",self.usb,True)
        a.addWidget(self.usb_button)
        self.usb_result = label("Підключи телефон кабелем із передаванням даних.","muted")
        a.addWidget(self.usb_result)
        self.address = label("","muted")
        self.address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        a.addWidget(self.address)
        outer.addWidget(panel)
        outer.addWidget(label("Встанови APK Orbit 0.4 на телефон. Для оновлення достатньо відкрити новий APK поверх попереднього.","muted"))
        outer.addStretch()
        return page

    def display_page(self):
        page,outer = self.page("02. Додай свій екран.","Другий робочий стіл для вікон, документів і всього, що не вміщається.")
        row=QHBoxLayout()
        left,a=card()
        self.monitor=QComboBox();self.monitor.currentIndexChanged.connect(self.selected)
        a.addWidget(self.monitor)
        self.monitor_note=label("","muted");a.addWidget(self.monitor_note)
        self.driver_button=button("Додати віртуальний монітор ↗",self.open_driver)
        a.addWidget(self.driver_button)
        a.addWidget(label("У Virtual Driver Control: Install → додай один монітор. У Windows обери «Розширити ці дисплеї», тоді онови список тут.","muted"))
        a.addWidget(button("Налаштування дисплеїв Windows ↗",lambda:QDesktopServices.openUrl(QUrl("ms-settings:display"))))
        a.addWidget(button("Оновити список",self.refresh))
        a.addStretch();row.addWidget(left,1)
        right,b=card()
        b.addWidget(label("РОЗДІЛЬНІСТЬ І РОЗТАШУВАННЯ","eyebrow"))
        self.resolution=QComboBox();self.resolution.currentIndexChanged.connect(self.resolution_changed);b.addWidget(self.resolution)
        self.refresh_rate=QComboBox();b.addWidget(self.refresh_rate)
        self.arrangement=Arrangement();self.arrangement.setMinimumHeight(155);b.addWidget(self.arrangement)
        sides=QHBoxLayout();self.side_buttons=[]
        for text,side in [("←","left"),("↑","top"),("↓","bottom"),("→","right")]:
            obj=button(text,lambda checked=False,s=side:self.choose_side(s));obj.setCheckable(True);obj.setChecked(side=="right")
            obj.setToolTip({"left":"Ліворуч","right":"Праворуч","top":"Зверху","bottom":"Знизу"}[side]);sides.addWidget(obj);self.side_buttons.append((obj,side))
        b.addLayout(sides)
        self.apply=button("Застосувати екран",self.apply_side);b.addWidget(self.apply)
        row.addWidget(right,1);outer.addLayout(row);outer.addStretch()
        return page

    def quality_page(self):
        page,outer=self.page("03. Знайди свій баланс.","Плавність — для руху. Чіткість — для дрібного тексту. Почни з рекомендованого режиму.")
        panel,a=card()
        self.profile=QComboBox()
        self.profile.addItems(["Плавність · 1920 × 1080 · рекомендовано","Чіткість · 1920 × 1080","Легший потік · 1600 px","Мінімальне навантаження · 1280 px"])
        a.addWidget(self.profile)
        self.fps_limit=QComboBox();self.fps_limit.addItem("Авто · до 60 FPS, менше CPU",0)
        for rate in (30,60,90,120,144,165,240):self.fps_limit.addItem(f"До {rate} FPS",rate)
        a.addWidget(self.fps_limit)
        a.addWidget(label("H.264 + MediaCodec на Android. Intel Quick Sync на ПК, якщо доступний. Якщо рух ривками — обери 1280 px і 60 FPS. Роздільність робочого столу при цьому зберігається. 120 Гц не гарантують 120 FPS.","muted"))
        self.compatible_video=QCheckBox("JPEG · режим сумісності, якщо H.264 не працює");a.addWidget(self.compatible_video)
        self.compatible_capture=QCheckBox("Сумісне захоплення · якщо зображення чорне");a.addWidget(self.compatible_capture)
        self.touch=QCheckBox("Керування мишею та клавіатурою з телефона");self.touch.setChecked(True);self.touch.toggled.connect(self.update_permissions);a.addWidget(self.touch)
        self.clipboard=QCheckBox("Обмін текстом буфера");self.clipboard.toggled.connect(self.update_permissions);a.addWidget(self.clipboard)
        outer.addWidget(panel);outer.addStretch()
        return page

    def launch_page(self):
        page,outer=self.page("04. Твій простір готовий.","Почни сеанс, введи код на телефоні та звір відбиток ПК під час першого підключення.")
        panel,a=card()
        self.summary=label("","muted");self.summary.setMinimumHeight(110);a.addWidget(self.summary)
        self.pin=label("— — — — — —","pin");self.pin.setTextInteractionFlags(Qt.TextSelectableByMouse);a.addWidget(self.pin)
        a.addWidget(label("Код діє 10 хвилин для нового підключення.","muted"))
        self.fingerprint=label("Відбиток ПК: "+self.short_fingerprint(),"muted");self.fingerprint.setToolTip(self.server.fingerprint);a.addWidget(self.fingerprint)
        self.start_button=button("Почати сеанс →",self.toggle,True);a.addWidget(self.start_button)
        self.metrics=label("Очікуємо початку сеансу","muted");a.addWidget(self.metrics)
        outer.addWidget(panel);outer.addStretch()
        return page

    def update_step(self):
        step=self.pages.currentIndex()
        names=["З'єднання","Екран","Якість","Запуск"]
        self.progress.setText("   /   ".join(f"{'●' if i==step else '○'} {i+1:02}  {name}" for i,name in enumerate(names)))
        self.back_button.setEnabled(step>0 and not self.active)
        self.next_button.setVisible(step<3)
        self.next_button.setEnabled(not self.usb_pending)
        if step==3:
            d=self.target()
            self.summary.setText(f"{self.transport.currentText()}  ·  {self.profile.currentText()}\n{d.width if d else '—'} × {d.height if d else '—'} · {self.fps_limit.currentText()}\n"+self.address.text())

    def previous_step(self):
        if not self.active:self.pages.setCurrentIndex(max(0,self.pages.currentIndex()-1));self.update_step()

    def next_step(self):
        step=self.pages.currentIndex()
        if step==0 and self.transport.currentIndex() and not self.usb_ready:
            self.usb(advance=True);return
        if step==1:
            if not self.target():self.error("Додай дисплей і онови список.");return
            if not self.target().primary and not self.apply_side():return
        self.pages.setCurrentIndex(min(3,step+1));self.update_step()
        self.status.setText(["","Обери додатковий дисплей або залиш дублювання основного.","Налаштуй якість та доступ із телефона.","Натисни «Почати сеанс», потім продовж на Android."][self.pages.currentIndex()])

    def short_fingerprint(self):
        return " ".join(self.server.fingerprint[i:i+4] for i in range(0,16,4))

    def show_addresses(self):
        if not hasattr(self, "address"): return
        ips = []
        for interface in QNetworkInterface.allInterfaces():
            if not interface.flags() & QNetworkInterface.IsUp or interface.flags() & QNetworkInterface.IsLoopBack: continue
            for entry in interface.addressEntries():
                if entry.ip().protocol() == QAbstractSocket.IPv4Protocol: ips.append(entry.ip().toString())
        self.address.setText("Адреса: 127.0.0.1:48620" if self.transport.currentIndex() else "Адреси ПК · порт 48620\n" + ("\n".join(ips) or "Мережу не знайдено"))

    def refresh(self):
        if self.active: return
        old = self.monitor.currentData()
        self.screens = displays()
        self.monitor.blockSignals(True)
        self.monitor.clear()
        for d in self.screens:
            name = "Основний · дублювання" if d.primary else "Додатковий · розширення"
            self.monitor.addItem(f"{name} · {d.width}×{d.height} / {d.hz} Гц",d.name)
        index = self.monitor.findData(old) if old else -1
        if index < 0: index = next((i for i,d in enumerate(self.screens) if not d.primary),0)
        self.monitor.setCurrentIndex(index)
        self.monitor.blockSignals(False)
        self.selected()
        self.show_addresses()


    def target(self):
        return next((d for d in self.screens if d.name == self.monitor.currentData()),None)

    def selected(self):
        if not hasattr(self,"apply"): return
        d = self.target()
        self.apply.setEnabled(bool(d and not d.primary and not self.active))
        for control in (self.resolution,self.refresh_rate): control.setEnabled(bool(d and not d.primary and not self.active))
        if self.active: return
        self.mode_catalog = supported_modes(d.name) if d else []
        self.resolution.blockSignals(True)
        self.resolution.clear()
        dimensions = sorted({(w,h) for w,h,_ in self.mode_catalog})
        for w,h in dimensions: self.resolution.addItem(f"{w} × {h}" + (" · Full HD" if (w,h)==(1920,1080) else ""),(w,h))
        if (1920,1080) not in dimensions:
            self.resolution.addItem("1920 × 1080 · немає у драйвері",(1920,1080))
            self.resolution.model().item(self.resolution.count()-1).setEnabled(False)
        self.resolution.setCurrentIndex(next((i for i,dim in enumerate(dimensions) if d and dim==(d.width,d.height)),0))
        if d and not d.primary and d.name not in self.initialized_displays:
            self.initialized_displays.add(d.name)
            if (1920,1080) in dimensions:self.resolution.setCurrentIndex(dimensions.index((1920,1080)))
        self.resolution.blockSignals(False)
        self.resolution_changed()
        self.monitor_note.setText("Дублювання основного. Для другого робочого столу додайте віртуальний монітор." if d and d.primary else "Виберіть 1920×1080 та потрібні Гц, потім застосуйте. Режими надає драйвер.")

    def resolution_changed(self):
        if not hasattr(self,"refresh_rate"): return
        self.refresh_rate.clear()
        dim = self.resolution.currentData()
        rates = sorted({hz for w,h,hz in self.mode_catalog if (w,h)==dim})
        if rates:
            self.refresh_rate.addItem(f"Максимум драйвера · {max(rates)} Гц",0)
            for hz in rates: self.refresh_rate.addItem(f"{hz} Гц",hz)
            preferred=max((hz for hz in rates if hz<=120),default=min(rates))
            self.refresh_rate.setCurrentIndex(self.refresh_rate.findData(preferred))

    def transport_changed(self):
        self.usb_ready=False
        usb=bool(self.transport.currentIndex())
        self.usb_button.setVisible(usb);self.usb_result.setVisible(usb)
        self.connection_help.setText("1. З'єднай телефон і ноутбук USB-кабелем.\n2. На Android увімкни «Параметри розробника → Налагодження через USB».\n3. Розблокуй телефон і дозволь доступ цьому ПК." if usb else "Підключи пристрої до однієї мережі Wi-Fi або ввімкни USB-модем на Android. На телефоні введи одну з адрес ПК нижче. Для Wi-Fi дозволь Orbit у брандмауері приватної мережі.")
        self.show_addresses()

    def choose_side(self, side):
        self.arrangement.side = side
        self.arrangement.update()
        for b,s in self.side_buttons: b.setChecked(s == side)

    def apply_side(self):
        if self.active: return
        try:
            d = self.target()
            if not d or not self.resolution.currentData(): raise ValueError("Виберіть додатковий дисплей та режим.")
            p = next(s for s in self.screens if s.primary)
            width,height = self.resolution.currentData()
            hz = self.refresh_rate.currentData()
            if hz is None: raise ValueError("Драйвер не надає цей режим. Додайте його у Virtual Driver Control.")
            original = set_display_mode(d,p,width,height,hz,self.arrangement.side)
            self.originals.setdefault(d.name,original)
            self.refresh()
            actual = self.target()
            self.status.setText(f"Застосовано {actual.width}×{actual.height} / {actual.hz} Гц. Попередній режим відновиться після закриття Orbit.")
            return True
        except Exception as exc:
            self.error(str(exc))
            return False

    def update_permissions(self):
        self.server.allow_touch = self.touch.isChecked()
        if hasattr(self,"clipboard"): self.server.allow_clipboard = self.clipboard.isChecked()
        if not self.server.allow_touch and self.server.control:
            with self.server.input_lock: self.server.control.release()
        self.server.send_json({"type":"permissions","touch":self.server.allow_touch,"clipboard":self.server.allow_clipboard})

    def toggle(self):
        if self.active:
            self.server.stop()
            self.set_active(False)
            return
        try:
            if self.transport.currentIndex():
                prepare_usb()
            self.refresh()
            d = self.target()
            if not d: raise ValueError("Windows не бачить дисплеїв")
            if d.primary and QMessageBox.question(self,"Дублювання основного екрана","Віртуальний екран не вибрано. Передавати основний екран у режимі дублювання?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
            quality,width = [(65,1920),(85,1920),(65,1600),(50,1280)][self.profile.currentIndex()]
            fps = self.fps_limit.currentData()
            self.server.start(d,fps,quality,width, "127.0.0.1" if self.transport.currentIndex() else "0.0.0.0",fast_capture=not self.compatible_capture.isChecked(),video=not self.compatible_video.isChecked())
            self.set_active(True)
            self.pin.setText(self.server.pin)
            self.status.setText("На Android введіть адресу й код. При першому з'єднанні порівняйте відбиток ПК.")
        except Exception as exc: self.error(str(exc))

    def set_active(self, active):
        self.active = active
        self.start_button.setText("Зупинити сеанс" if active else "Почати сеанс")
        self.state.setText("●  Очікування Android" if active else "●  Сеанс вимкнено")
        for w in (self.monitor,self.transport,self.profile,self.fps_limit,self.compatible_capture,self.compatible_video): w.setEnabled(not active)
        for b,_ in self.side_buttons: b.setEnabled(not active)
        self.selected()
        self.update_step()
        if not active:
            self.pin.setText("— — — — — —")
            self.metrics.setText("Локальне з'єднання · TLS")

    def tick(self):
        if self.active and not self.server.authenticated and self.server.expires < __import__("time").monotonic():
            self.pin.setText("Код сплив")

    def on_event(self, kind, text):
        if kind=='update_ready':
            self.update_busy=False
            if text:
                self.update_file=text;self.update_button.setText('Встановити оновлення');self.update_button.setEnabled(True)
        elif kind == "connected":
            self.state.setText("●  " + text)
            self.status.setText("Екран передається. Щоб негайно від'єднати телефон, зупиніть сеанс.")
        elif kind == "metrics": self.metrics.setText(text)
        elif kind == "disconnected":
            self.state.setText("●  Очікування Android" if self.active else "●  Сеанс вимкнено")
            self.metrics.setText("Android від'єднано")
        elif kind == "stopped": self.set_active(False)
        elif kind == "clipboard_get" and self.server.allow_clipboard:
            self.server.send_json({"type":"clipboard","text":QApplication.clipboard().text()[:4096]})
        elif kind == "clipboard_set" and self.server.allow_clipboard:
            QApplication.clipboard().setText(text)
        elif kind in ("usb","usb_error"):
            self.usb_pending=False
            self.usb_button.setEnabled(True)
            self.usb_ready=kind=="usb"
            self.usb_result.setText(text)
            self.status.setText(text)
            self.update_step()
            if self.usb_ready and self.usb_advance:self.next_step()
        else: self.status.setText(text)

    def usb(self, checked=False, advance=False):
        if self.usb_pending:return
        self.usb_pending=True;self.usb_advance=advance
        self.usb_button.setEnabled(False);self.next_button.setEnabled(False)
        self.usb_result.setText("Перевіряємо телефон та створюємо USB-з'єднання…")
        def work():
            try:self.events.message.emit("usb",prepare_usb())
            except Exception as exc:self.events.message.emit("usb_error",str(exc))
        threading.Thread(target=work,daemon=True).start()

    def open_driver(self):
        path = bundle_root()/"tools"/"Virtual-Driver-Control"
        if path.is_dir(): QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else: QDesktopServices.openUrl(QUrl("https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.7.23"))

    def error(self, text): QMessageBox.warning(self,"Orbit Display",text)

    def closeEvent(self, event):
        self.server.stop()
        errors = []
        for name,original in self.originals.items():
            try: restore_display(name,original)
            except Exception as exc: errors.append(str(exc))
        if errors: self.error("\n".join(errors)+"\nВідновіть розташування в налаштуваннях Windows.")
        event.accept()


def main():
    smoke = len(sys.argv) == 3 and sys.argv[1] in ("--smoke-test","--stream-smoke")
    if smoke: os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv)
    if smoke:
        # Qt's offscreen backend does not discover Windows system fonts itself.
        fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf','consolab.ttf'):
            QFontDatabase.addApplicationFont(str(fonts/name))
        app.setFont(QFont('Segoe UI',10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    if smoke:
        import json, tempfile
        with tempfile.TemporaryDirectory() as temp:
            window = None
            try:
                window = Window(temp)
                window.show()
                app.processEvents()
                result={"ok":True,"version":"0.4.0","displays":len(window.screens),"tls":len(window.server.fingerprint)==64,"steps":window.pages.count(),"maximized":window.isMaximized()}
                if sys.argv[1]=="--smoke-test":
                    window.usb_advance=False
                    window.on_event('usb',USB_READY)
                    app.processEvents()
                    result['usb_message']=window.usb_result.text()
                    window.grab().save(str(Path(sys.argv[2]).with_suffix('.png')))
                if sys.argv[1]=="--stream-smoke":
                    from diagnostics import stream_check
                    result['stream']=stream_check(Path(temp)/'stream',window.screens[0])
                    result['video']=stream_check(Path(temp)/'video',window.screens[0],video=True)
            except Exception:
                import traceback
                result={"ok":False,"error":traceback.format_exc()}
            finally:
                if window:window.close()
                logging.shutdown()
            Path(sys.argv[2]).write_text(json.dumps(result),encoding="utf-8")
        return
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__": main()
