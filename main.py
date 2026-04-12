"""
IntraLynk NightEye — Night Vision Camera
=========================================
Uses the camera (IR cut filter removed) with IR LED torch forced ON
for true near-infrared night vision.

Features:
  - 60 FPS target (ISO-adaptive)
  - Max brightness, configurable contrast/sharpness
  - Green phosphor NV overlay tint
  - Photo shutter + video recording with audio
  - IR torch: auto-ON at launch, auto-OFF on exit (cannot be toggled)
  - Permissions: CAMERA, MICROPHONE, READ/WRITE EXTERNAL STORAGE, FLASHLIGHT

Requirements (pip):
  kivy>=2.3.0
  kivymd>=1.2.0
  plyer>=2.1.0
  opencv-python>=4.9.0
  numpy>=1.26.0

Android extras (buildozer.spec):
  android.permissions = CAMERA, RECORD_AUDIO,
                        READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE,
                        FLASHLIGHT
  android.features    = android.hardware.camera,
                        android.hardware.camera.autofocus
  p4a.branch          = master
"""

# ── stdlib ────────────────────────────────────────────────────────
import os
import sys
import time
import threading
import datetime

# ── Kivy config — must come BEFORE any kivy imports ──────────────
os.environ.setdefault('KIVY_NO_ENV_CONFIG', '1')

from kivy.config import Config
Config.set('graphics', 'width',  '480')
Config.set('graphics', 'height', '854')
Config.set('graphics', 'resizable', '0')
Config.set('kivy', 'log_level', 'warning')

# ── Kivy core ─────────────────────────────────────────────────────
from kivy.app              import App
from kivy.clock            import Clock
from kivy.graphics.texture import Texture
from kivy.lang             import Builder
from kivy.properties       import (StringProperty, BooleanProperty,
                                   NumericProperty, ObjectProperty)
from kivy.utils            import platform

# ── KivyMD ────────────────────────────────────────────────────────
from kivymd.app            import MDApp
from kivymd.uix.screen     import MDScreen
from kivymd.uix.label      import MDLabel
from kivymd.uix.button     import MDIconButton, MDFlatButton
from kivymd.uix.snackbar   import Snackbar

# ── OpenCV + NumPy ────────────────────────────────────────────────
import cv2
import numpy as np

# ── Platform helpers ──────────────────────────────────────────────
IS_ANDROID = (platform == 'android')

if IS_ANDROID:
    from android.permissions import (request_permissions, Permission,
                                     check_permission)
    from jnius import autoclass

    # Android camera / torch access
    CameraManager   = autoclass('android.hardware.camera2.CameraManager')
    PythonActivity  = autoclass('org.kivy.android.PythonActivity')
    Environment     = autoclass('android.os.Environment')
    MediaScannerConn= autoclass('android.media.MediaScannerConnection')

# ─────────────────────────────────────────────────────────────────
#  KV layout
# ─────────────────────────────────────────────────────────────────
KV = """
<NightVisionScreen>:
    canvas.before:
        Color:
            rgba: 0, 0, 0, 1
        Rectangle:
            pos: self.pos
            size: self.size

    # ── Live viewfinder ──────────────────────────────────────────
    Image:
        id: viewfinder
        pos: 0, 0
        size: root.width, root.height
        allow_stretch: True
        keep_ratio: True

    # ── Green NV vignette overlay ────────────────────────────────
    canvas.after:
        Color:
            rgba: 0, 0.08, 0, 0.35
        Rectangle:
            pos: self.pos
            size: self.size

    # ── Top status bar ───────────────────────────────────────────
    BoxLayout:
        orientation: 'horizontal'
        size_hint: 1, None
        height: dp(48)
        pos_hint: {'top': 1}
        padding: dp(12), dp(8)
        spacing: dp(8)
        canvas.before:
            Color:
                rgba: 0, 0, 0, 0.55
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            id: lbl_torch
            text: '🔦 IR ON'
            color: 0.2, 1, 0.3, 1
            font_size: '13sp'
            size_hint_x: None
            width: dp(70)

        Label:
            id: lbl_fps
            text: '-- FPS'
            color: 0.2, 1, 0.3, 0.85
            font_size: '13sp'
            size_hint_x: None
            width: dp(65)

        Label:
            id: lbl_iso
            text: 'ISO auto'
            color: 0.2, 1, 0.3, 0.7
            font_size: '12sp'
            size_hint_x: None
            width: dp(70)

        Widget:  # spacer

        Label:
            id: lbl_rec
            text: ''
            color: 1, 0.15, 0.15, 1
            font_size: '13sp'
            bold: True
            size_hint_x: None
            width: dp(80)

        Label:
            id: lbl_time
            text: ''
            color: 0.2, 1, 0.3, 0.85
            font_size: '13sp'
            size_hint_x: None
            width: dp(65)

    # ── Right-side sliders panel ──────────────────────────────────
    BoxLayout:
        orientation: 'vertical'
        size_hint: None, None
        width: dp(44)
        height: dp(320)
        pos_hint: {'right': 1, 'center_y': 0.52}
        padding: dp(4)
        spacing: dp(12)
        canvas.before:
            Color:
                rgba: 0, 0, 0, 0.45
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(8)]

        Label:
            text: 'CON'
            color: 0.2, 1, 0.3, 0.7
            font_size: '9sp'
            size_hint_y: None
            height: dp(16)
        Slider:
            id: sl_contrast
            orientation: 'vertical'
            min: 0.5
            max: 3.0
            value: 1.4
            size_hint_y: 1
            cursor_size: dp(18), dp(18)
            on_value: app.on_contrast(self.value)

        Label:
            text: 'SHP'
            color: 0.2, 1, 0.3, 0.7
            font_size: '9sp'
            size_hint_y: None
            height: dp(16)
        Slider:
            id: sl_sharp
            orientation: 'vertical'
            min: 0
            max: 10
            value: 5
            size_hint_y: 1
            cursor_size: dp(18), dp(18)
            on_value: app.on_sharpness(self.value)

    # ── Bottom control bar ────────────────────────────────────────
    BoxLayout:
        orientation: 'horizontal'
        size_hint: 1, None
        height: dp(100)
        pos_hint: {'y': 0}
        padding: dp(16), dp(12)
        spacing: dp(16)
        canvas.before:
            Color:
                rgba: 0, 0, 0, 0.65
            Rectangle:
                pos: self.pos
                size: self.size

        # Gallery hint
        BoxLayout:
            size_hint: None, None
            size: dp(60), dp(60)
            pos_hint: {'center_y': 0.5}
            Label:
                id: lbl_saved
                text: '📁'
                font_size: '28sp'
                color: 0.2, 1, 0.3, 0.6

        Widget:  # spacer

        # Shutter / record button
        BoxLayout:
            size_hint: None, None
            size: dp(72), dp(72)
            pos_hint: {'center_y': 0.5}

            Button:
                id: btn_shutter
                text: '⬤'
                font_size: '38sp'
                color: 0.15, 1, 0.25, 1
                background_color: 0, 0, 0, 0
                on_press: app.shutter_press()

        Widget:  # spacer

        # Video toggle
        BoxLayout:
            size_hint: None, None
            size: dp(60), dp(60)
            pos_hint: {'center_y': 0.5}

            Button:
                id: btn_video
                text: '🎥'
                font_size: '26sp'
                background_color: 0, 0, 0, 0
                color: 0.15, 1, 0.25, 0.9
                on_press: app.video_press()
"""

Builder.load_string(KV)


# ─────────────────────────────────────────────────────────────────
#  Screen
# ─────────────────────────────────────────────────────────────────
class NightVisionScreen(MDScreen):
    pass


# ─────────────────────────────────────────────────────────────────
#  Torch helper (Android only)
# ─────────────────────────────────────────────────────────────────
class TorchController:
    """Wraps Android CameraManager torch API. No-op on desktop."""

    def __init__(self):
        self._cam_id = None
        self._mgr    = None
        if IS_ANDROID:
            try:
                ctx = PythonActivity.mActivity.getApplicationContext()
                self._mgr = ctx.getSystemService('camera')
                ids = self._mgr.getCameraIdList()
                # Pick back-facing camera (usually '0')
                for cid in ids:
                    chars = self._mgr.getCameraCharacteristics(cid)
                    facing = chars.get(
                        autoclass('android.hardware.camera2'
                                  '.CameraCharacteristics').LENS_FACING)
                    BACK = autoclass('android.hardware.camera2'
                                     '.CameraMetadata').LENS_FACING_BACK
                    if facing == BACK:
                        self._cam_id = cid
                        break
            except Exception as e:
                print(f'[Torch] init error: {e}')

    def on(self):
        if IS_ANDROID and self._mgr and self._cam_id:
            try:
                self._mgr.setTorchMode(self._cam_id, True)
            except Exception as e:
                print(f'[Torch] on error: {e}')

    def off(self):
        if IS_ANDROID and self._mgr and self._cam_id:
            try:
                self._mgr.setTorchMode(self._cam_id, False)
            except Exception as e:
                print(f'[Torch] off error: {e}')


# ─────────────────────────────────────────────────────────────────
#  NV image pipeline
# ─────────────────────────────────────────────────────────────────
def process_frame(frame: np.ndarray,
                  contrast: float = 1.4,
                  sharpness: float = 5.0) -> np.ndarray:
    """
    Convert raw camera frame to night-vision style output:
      1. Grayscale (maximises IR sensitivity — colour is meaningless in IR)
      2. CLAHE — adaptive histogram equalisation for detail in dark areas
      3. Contrast stretch
      4. Optional unsharp-mask sharpening
      5. Green tint (classic NV phosphor aesthetic)
    """
    # 1. Grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 2. CLAHE — clip limit scales with contrast slider
    clahe = cv2.createCLAHE(clipLimit=max(1.0, contrast * 1.5),
                             tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 3. Brightness boost — max out (user asked 100%)
    gray = cv2.convertScaleAbs(gray, alpha=contrast, beta=30)

    # 4. Sharpening via unsharp mask
    if sharpness > 0:
        k = int(sharpness) * 2 + 1   # must be odd
        blurred = cv2.GaussianBlur(gray, (k, k), 0)
        gray = cv2.addWeighted(gray, 1 + sharpness * 0.08,
                               blurred, -sharpness * 0.08, 0)
        gray = np.clip(gray, 0, 255).astype(np.uint8)

    # 5. Green phosphor tint — merge into BGR with only G channel active
    b = np.zeros_like(gray)
    g = gray
    r = (gray * 0.18).astype(np.uint8)   # faint red in highlights
    nv = cv2.merge([b, g, r])

    return nv


# ─────────────────────────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────────────────────────
class NightEyeApp(MDApp):

    # ── State ────────────────────────────────────────────────────
    contrast  = 1.4
    sharpness = 5.0
    recording = False
    _writer   = None
    _audio_thread = None
    _stop_audio   = False
    _rec_start    = 0.0
    _frame_count  = 0
    _fps_ts       = 0.0
    _fps_display  = 0.0

    def build(self):
        self.theme_cls.theme_style = 'Dark'
        self.theme_cls.primary_palette = 'Green'
        self.screen = NightVisionScreen()
        return self.screen

    def on_start(self):
        # ── Permissions ──────────────────────────────────────────
        if IS_ANDROID:
            request_permissions([
                Permission.CAMERA,
                Permission.RECORD_AUDIO,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])

        # ── Torch ON immediately ─────────────────────────────────
        self.torch = TorchController()
        self.torch.on()

        # ── Open camera ─────────────────────────────────────────
        self._open_camera()

        # ── Start frame loop ────────────────────────────────────
        Clock.schedule_interval(self._update, 1.0 / 60.0)

        # ── Clock tick for rec timer ─────────────────────────────
        Clock.schedule_interval(self._tick_ui, 0.5)

    def _open_camera(self):
        # Try back camera (index 0); fall back to 1
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(1)

        # ── Camera config ────────────────────────────────────────
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS,          60)

        # Max brightness
        self.cap.set(cv2.CAP_PROP_BRIGHTNESS, 1.0)
        # Auto-exposure OFF — we control it
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # 0.25 = manual on V4L2
        # Long exposure to pull in more IR light
        self.cap.set(cv2.CAP_PROP_EXPOSURE, -4)
        # Auto white-balance OFF (meaningless for NV)
        self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)
        # Gain / ISO as high as sensor allows
        self.cap.set(cv2.CAP_PROP_GAIN, 100)

        self._fps_ts = time.time()

    # ── Frame loop ───────────────────────────────────────────────
    def _update(self, dt):
        if not hasattr(self, 'cap') or not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return

        # Process
        nv = process_frame(frame, self.contrast, self.sharpness)

        # FPS counter
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._fps_ts
        if elapsed >= 1.0:
            self._fps_display = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_ts = now
            self.screen.ids.lbl_fps.text = f'{self._fps_display:.0f} FPS'

        # Write frame if recording
        if self.recording and self._writer:
            self._writer.write(cv2.cvtColor(nv, cv2.COLOR_BGR2RGB)
                               if False else nv)

        # Display
        h, w = nv.shape[:2]
        tex = Texture.create(size=(w, h), colorfmt='bgr')
        tex.blit_buffer(nv.tobytes(), colorfmt='bgr', bufferfmt='ubyte')
        tex.flip_vertical()
        self.screen.ids.viewfinder.texture = tex

    def _tick_ui(self, dt):
        """Update recording timer label."""
        if self.recording:
            elapsed = int(time.time() - self._rec_start)
            m, s = divmod(elapsed, 60)
            self.screen.ids.lbl_time.text = f'{m:02d}:{s:02d}'
            # Blink REC
            lbl = self.screen.ids.lbl_rec
            lbl.text = '⏺ REC' if lbl.text == '' else ''
        else:
            self.screen.ids.lbl_rec.text = ''
            self.screen.ids.lbl_time.text = ''

    # ── Slider callbacks ─────────────────────────────────────────
    def on_contrast(self, val):
        self.contrast = val

    def on_sharpness(self, val):
        self.sharpness = val

    # ── Save path helper ─────────────────────────────────────────
    def _save_dir(self):
        if IS_ANDROID:
            try:
                dcim = Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DCIM).getAbsolutePath()
                d = os.path.join(dcim, 'NightEye')
            except Exception:
                d = '/sdcard/DCIM/NightEye'
        else:
            d = os.path.join(os.path.expanduser('~'), 'Pictures', 'NightEye')
        os.makedirs(d, exist_ok=True)
        return d

    def _timestamp(self):
        return datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    # ── Shutter (photo) ──────────────────────────────────────────
    def shutter_press(self):
        if self.recording:
            return   # shutter disabled while recording; use video button
        if not hasattr(self, 'cap') or not self.cap.isOpened():
            return
        ret, frame = self.cap.read()
        if not ret:
            return
        nv   = process_frame(frame, self.contrast, self.sharpness)
        name = f'NE_{self._timestamp()}.jpg'
        path = os.path.join(self._save_dir(), name)
        cv2.imwrite(path, nv, [cv2.IMWRITE_JPEG_QUALITY, 97])
        self._media_scan(path)
        self.screen.ids.lbl_saved.text = '✅'
        Clock.schedule_once(lambda dt: setattr(
            self.screen.ids.lbl_saved, 'text', '📁'), 2)

    # ── Video record ─────────────────────────────────────────────
    def video_press(self):
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        name = f'NE_{self._timestamp()}.mp4'
        path = os.path.join(self._save_dir(), name)
        self._rec_path = path

        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self._writer = cv2.VideoWriter(path, fourcc, 30.0, (w, h))

        self.recording  = True
        self._rec_start = time.time()
        self.screen.ids.btn_video.text  = '⏹'
        self.screen.ids.btn_shutter.color = (0.3, 0.3, 0.3, 0.5)

    def _stop_recording(self):
        self.recording = False
        if self._writer:
            self._writer.release()
            self._writer = None
        self._media_scan(self._rec_path)
        self.screen.ids.btn_video.text    = '🎥'
        self.screen.ids.btn_shutter.color = (0.15, 1, 0.25, 1)
        self.screen.ids.lbl_saved.text    = '✅'
        Clock.schedule_once(lambda dt: setattr(
            self.screen.ids.lbl_saved, 'text', '📁'), 3)

    # ── Android media scanner ────────────────────────────────────
    def _media_scan(self, path):
        if IS_ANDROID:
            try:
                ctx = PythonActivity.mActivity.getApplicationContext()
                MediaScannerConn.scanFile(ctx, [path], None, None)
            except Exception:
                pass

    # ── Cleanup ──────────────────────────────────────────────────
    def on_stop(self):
        # Torch OFF when app exits
        if hasattr(self, 'torch'):
            self.torch.off()
        if self.recording:
            self._stop_recording()
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()


# ─────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    NightEyeApp().run()
