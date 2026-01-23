You have two main options, depending on your Windows/WSL setup.
## 1. If you have WSLg (Windows 11 or recent Windows 10 Insider)
WSLg lets Linux GUI apps run “natively” from WSL without extra setup.
### Check if WSLg is available
In PowerShell or CMD:``` bash
wsl --version
```

If you see something like WSLg (x.x.x) in the output, you’re good.
If not, update WSL:``` bash
wsl --update
wsl --shutdown
```
Then reopen your WSL distro.
### Install Firefox in your WSL distro
For Ubuntu/Debian:``` bash
sudo apt update
sudo apt install firefox
```
2. If you don’t have WSLg (older Windows 10)
You need a Windows X server and then point WSL’s display to it.
Step 1: Install a Windows X server
Install VcXsrv or Xming on Windows (download and install in the usual way).
Start it, typically with:
Display: :0
Disable access control (or configure access control properly).
Step 2: Set DISPLAY in WSL
In your WSL shell, set DISPLAY to point to your Windows host IP.
A simple approach (for most home setups):``` bash
echo 'export DISPLAY=$(ip route | awk "/^default/ {print \$3}"):0' >> ~/.bashrc
echo 'export LIBGL_ALWAYS_INDIRECT=1' >> ~/.bashrc
source ~/.bashrc
```

Explanation:
ip route … grabs the Windows host IP as seen from WSL.
:0 is the display used by your X server.
Step 3: Install Firefox in WSL
For Ubuntu/Debian:``` bash
sudo apt update
sudo apt install firefox
```
