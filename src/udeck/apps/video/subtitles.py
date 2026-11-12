"""Read a selected embedded text track without blocking video playback."""

import html
import re

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from udeck.i18n import Msg, tr

MAX_BYTES = 4 * 1024 * 1024
LOAD_TIMEOUT_MS = 30000


def parse_srt(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pattern = (r"(?m)^(\d{2,6}):([0-5]\d):([0-5]\d)[,.](\d\d\d)[ \t]*-->[ \t]*"
               r"(\d{2,6}):([0-5]\d):([0-5]\d)[,.](\d\d\d)[^\n]*\n"
               r"([\s\S]*?)(?=\n\s*\n|\Z)")
    cues = []
    for match in re.finditer(pattern, text):
        values = [int(value) for value in match.groups()[:8]]
        start, end = (values[i] * 3600 + values[i + 1] * 60 + values[i + 2]
                      + values[i + 3] / 1000 for i in (0, 4))
        caption = html.unescape(re.sub(r"<[^>]+>", "", match.group(9))).strip()
        if end > start and caption:
            cues.append((start, end, caption))
    return cues


class EmbeddedSubtitles(QObject):
    ready = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.index = -1
        self.cues = None
        self.data = bytearray()
        self.errors = bytearray()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._fail(tr(Msg.SUBTITLE_LOADING_TIMED_OUT)))

    def load(self, path, index):
        self.clear()
        self.index = index
        process = QProcess(self)
        self.process = process
        process.readyReadStandardOutput.connect(lambda: self._read(process))
        process.readyReadStandardError.connect(lambda: self._read(process))
        process.finished.connect(lambda code, status: self._finished(process, code, status))
        process.finished.connect(process.deleteLater)
        process.errorOccurred.connect(lambda error: self._fail(process.errorString())
                                      if process is self.process else None)
        # Only demux/decode the selected subtitle stream. Audio and video are
        # neither decoded nor transcoded, and no sidecar file is written.
        self.timer.start(LOAD_TIMEOUT_MS)
        process.start("ffmpeg", ["-nostdin", "-hide_banner", "-loglevel", "error",
                                "-protocol_whitelist", "file,pipe", "-i", str(path),
                                "-map", f"0:s:{index}", "-vn", "-an", "-threads", "1",
                                "-c:s", "srt", "-f", "srt", "pipe:1"])

    def _read(self, process):
        if process is not self.process:
            return
        chunk = bytes(process.readAllStandardOutput())
        if len(self.data) + len(chunk) > MAX_BYTES:
            self._fail(tr(Msg.SUBTITLE_FILE_EXCEEDS_4_MIB))
            return
        self.data.extend(chunk)
        self.errors.extend(bytes(process.readAllStandardError()))
        del self.errors[:-8192]

    def _finished(self, process, code, status):
        self._read(process)
        if process is not self.process:
            return
        if code or status != QProcess.ExitStatus.NormalExit:
            error = self.errors.decode("utf-8", errors="replace").strip() or process.errorString()
            self._fail(error)
            return
        try:
            cues = parse_srt(self.data.decode("utf-8-sig"))
        except UnicodeError as error:
            self._fail(str(error))
            return
        self.timer.stop()
        self.process = None
        self.data.clear()
        self.errors.clear()
        self.cues = cues
        self.ready.emit()

    def _fail(self, error):
        self.clear()
        self.failed.emit(error)

    def clear(self):
        self.timer.stop()
        process, self.process = self.process, None
        if process:
            if process.state() == QProcess.ProcessState.NotRunning:
                process.deleteLater()
            else:
                process.kill()
        self.index = -1
        self.cues = None
        self.data.clear()
        self.errors.clear()

    def close(self):
        self.clear()
        # Include processes cancelled by a preceding selection/off action whose
        # finished signal has not yet been dispatched.
        for process in self.findChildren(QProcess):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
