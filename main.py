import socket
import threading
import time
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.network.urlrequest import UrlRequest

TARGET_PORT = 4776
BROADCAST_TIMEOUT = 10  # seconds to scan before giving up


def scan_gateway(port, callback):
    """Scan LAN subnet for a host listening on the target port."""
    def _scan():
        # Get this device's local IP to determine subnet
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            Clock.schedule_once(lambda dt: callback(None), 0)
            return

        subnet = ".".join(local_ip.split(".")[:3])  # e.g. 192.168.1
        found = None

        # Check .1 and .254 first (common gateway IPs)
        priority = [f"{subnet}.1", f"{subnet}.254", f"{subnet}.100"]
        targets = priority + [f"{subnet}.{i}" for i in range(2, 254)
                              if f"{subnet}.{i}" not in priority]

        for ip in targets:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.4)
                result = sock.connect_ex((ip, port))
                sock.close()
                if result == 0:
                    found = ip
                    break
            except Exception:
                continue

        Clock.schedule_once(lambda dt: callback(found), 0)

    thread = threading.Thread(target=_scan, daemon=True)
    thread.start()


# ── Screens ──────────────────────────────────────────────────────────────────

class ScanScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=40, spacing=20)

        self.status = Label(
            text='[b]IntraLynk[/b]\nScanning LAN for server...',
            markup=True,
            font_size='18sp',
            halign='center'
        )

        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=20)

        layout.add_widget(self.status)
        layout.add_widget(self.progress)
        self.add_widget(layout)

    def start_scan(self):
        Clock.schedule_interval(self._tick_progress, 0.1)
        scan_gateway(TARGET_PORT, self._on_scan_result)

    def _tick_progress(self, dt):
        if self.progress.value < 90:
            self.progress.value += 1

    def _on_scan_result(self, ip):
        Clock.unschedule(self._tick_progress)
        self.progress.value = 100
        if ip:
            self.status.text = f'[b]Found![/b]\nConnecting to {ip}:{TARGET_PORT}...'
            app = App.get_running_app()
            app.server_ip = ip
            Clock.schedule_once(lambda dt: app.load_webview(), 0.5)
        else:
            self.status.text = (
                '[b]IntraLynk[/b]\n'
                '[color=ff4444]No server found on this network.[/color]\n'
                'Make sure the IntraLynk server is running.'
            )
            # Retry after 5 seconds
            Clock.schedule_once(lambda dt: self.retry(), 5)

    def retry(self):
        self.progress.value = 0
        self.status.text = '[b]IntraLynk[/b]\nRetrying scan...'
        self.start_scan()


class WebScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # WebView is loaded dynamically after IP is found


# ── App ───────────────────────────────────────────────────────────────────────

class IntraLynkApp(App):
    server_ip = None

    def build(self):
        self.sm = ScreenManager()
        self.scan_screen = ScanScreen(name='scan')
        self.sm.add_widget(self.scan_screen)
        return self.sm

    def on_start(self):
        self.scan_screen.start_scan()

    def load_webview(self):
        from kivy.uix.screenmanager import NoTransition
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass

            # Use Android WebView for full Flask UI
            WebView = autoclass('android.webkit.WebView')
            WebViewClient = autoclass('android.webkit.WebViewClient')
            activity = autoclass('org.kivy.android.PythonActivity').mActivity

            @run_on_ui_thread
            def _load():
                wv = WebView(activity)
                wv.getSettings().setJavaScriptEnabled(True)
                wv.getSettings().setDomStorageEnabled(True)
                wv.setWebViewClient(WebViewClient())
                url = f"http://{self.server_ip}:{TARGET_PORT}"
                wv.loadUrl(url)
                activity.setContentView(wv)

            _load()

        except Exception as e:
            # Fallback: show the URL if WebView fails
            web = WebScreen(name='web')
            label = Label(
                text=f'Open in browser:\nhttp://{self.server_ip}:{TARGET_PORT}',
                halign='center',
                markup=True
            )
            web.add_widget(label)
            self.sm.add_widget(web)
            self.sm.transition = NoTransition()
            self.sm.current = 'web'


if __name__ == '__main__':
    IntraLynkApp().run()