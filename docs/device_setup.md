# 📱 Device Setup Guide

This guide helps you connect your Android or HarmonyOS device to ZhiXing.

##  Android Setup

### Prerequisites 

* A physical Android phone or Emulator (AVD/Genymotion). 
* A USB cable.

### Step 1: Enable Developer Options 

1. Go to **Settings** -> **About Phone**. 
2. Tap **Build Number** 7 times until you see "You are now a developer!".
3. Go to **Settings** -> **System** -> **Developer Options**. 

### Step 2: Install ADB Keyboard (Important!) 

ZhiXing uses `ADBKeyboard` to input text reliably. 

1. Download [ADBKeyboard.apk](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk). 
2. Install it on your phone: `adb install ADBKeyboard.apk`. 
3. Set it as the default input method in Settings.

### Step 3: Verify Connection 

Run the following command in your terminal: 

```bash 
adb devices
```

If you see your device ID (e.g., 12345678 device), you are ready!

## HarmonyOS Setup

### Prerequisites

- A Huawei phone running HarmonyOS NEXT.
- **HDC Toolchain** installed on your PC.

### Step 1: Install HDC

Download the command-line tools for HarmonyOS:

- [HDC Download Link](https://developer.huawei.com/consumer/cn/download/command-line-tools-for-hmos)
- Add the hdc executable to your system PATH.

### Step 2: Enable Debugging

1. Go to **Settings** -> **About Phone**.
2. Tap **Build Number** to enable Developer Mode.
3. Enable **USB Debugging**.

### Step 3: Verify Connection

```bash
hdc list targets
```

You should see your device ID.