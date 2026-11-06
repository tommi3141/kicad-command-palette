"""Plugin action entrypoint: launches the (single-instance) palette helper detached from KiCad."""
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(DIR, "kicad_palette.py")
NO_WINDOW = 0x08000000
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
BREAKAWAY = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB


def candidates():
    """Interpreters to try. KiCad's own Python ships wxPython; the plugin venv python does not."""
    dirs = [sys.base_prefix, os.path.dirname(sys.executable)]
    for d in dirs:
        yield os.path.join(d, "pythonw.exe")
    import shutil
    yield shutil.which("pythonw")
    yield shutil.which("pyw")


def has_wx(exe):
    try:
        return subprocess.run([exe, "-c", "import wx"], capture_output=True, timeout=20,
                              creationflags=NO_WINDOW).returncode == 0
    except Exception:
        return False


def log(msg):
    try:
        with open(os.path.join(os.environ.get("TEMP", DIR), "kicad_palette.log"), "a", encoding="utf-8") as f:
            f.write("launcher: %s\n" % msg)
    except OSError:
        pass


def launch(exe):
    log("launching %s" % exe)
    args = [exe, SCRIPT, "--exit-with-kicad"]
    for flags in (DETACHED | NO_WINDOW | BREAKAWAY, DETACHED | NO_WINDOW):
        try:
            subprocess.Popen(args, creationflags=flags, cwd=DIR, close_fds=True)
            return True
        except OSError:
            continue
    return False


def main():
    if sys.platform != "win32":
        sys.exit("Command Palette only supports Windows.")
    tried = []
    for exe in candidates():
        if exe and os.path.isfile(exe) and exe not in tried:
            tried.append(exe)
            ok = has_wx(exe)
            log("%s wx=%s" % (exe, ok))
            if ok and launch(exe):
                return
    log("no usable python, tried %s" % tried)
    sys.exit("No Python with wxPython found (tried: %s). Set KiCad's own pythonw.exe "
             "as Python interpreter in the KiCad settings." % (", ".join(tried) or "none"))


if __name__ == "__main__":
    main()
