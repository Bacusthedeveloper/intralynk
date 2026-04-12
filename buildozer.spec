[app]
title           = NightEye
package.name    = nighteye
package.domain  = org.simplex
source.dir      = .
source.include_exts = py,png,jpg,kv,atlas
version         = 1.0.0

requirements = python3,kivy==2.3.0,kivymd,plyer,opencv,numpy

# Orientation: portrait locked
orientation = portrait

# Android
android.permissions = CAMERA,RECORD_AUDIO,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,FLASHLIGHT
android.features    = android.hardware.camera,android.hardware.camera.autofocus,android.hardware.camera.flash
android.api         = 33
android.minapi      = 26
android.ndk         = 25b
android.archs       = arm64-v8a

# Allow back-camera torch
android.meta_data   = android.hardware.camera.flash.available=true

[buildozer]
log_level = 2
