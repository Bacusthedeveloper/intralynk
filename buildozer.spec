[app]
title           = IntraLynk
package.name    = intralynk
package.domain  = ltd.bacussoftware
source.dir      = .
source.include_exts = py,png,jpg,kv,atlas
version         = 1.0

requirements    = python3,kivy

orientation     = portrait
fullscreen      = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api         = 33
android.minapi      = 21
android.ndk         = 25b
android.archs       = arm64-v8a, armeabi-v7a, x86, x86_64

[buildozer]
log_level = 2
