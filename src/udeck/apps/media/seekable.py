"""
[INPUT]: 依赖 Qt 子进程、FFmpeg、常规 TS 文件与临时空间。
[OUTPUT]: 异步提供带关键帧索引的临时播放源及失败原因。
[POS]: 媒体引擎的 TS 定位适配层；只重封装，不改写原文件。
[PROTOCOL]: Update this header on change, then check AGENTS.md
"""

import shutil
import stat
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from udeck.i18n import Msg, tr

PREPARE_TIMEOUT_MS = 180000
PREPARE_POLL_MS = 200
SPACE_RESERVE = 64 * 1024 * 1024
OUTPUT_ALLOWANCE = 1024 * 1024
STDERR_LIMIT = 8192
PROCESS_EXIT_TIMEOUT_MS = 1000


class SeekableSource(QObject):
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None, directory=None):
        super().__init__(parent)
        self.directory = directory
        self.process = None
        self.temporary = None
        self.prepared = None
        self.source = None
        self.stamp = None
        self.errors = bytearray()
        self.timer = QTimer(self)
        self.timer.setInterval(PREPARE_POLL_MS)
        self.timer.timeout.connect(self._poll)
        self.started = 0
        self.maximum = 0

    @staticmethod
    def _stamp(path):
        information = path.lstat()
        if not stat.S_ISREG(information.st_mode):
            raise OSError(tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT))
        return (information.st_dev, information.st_ino, information.st_size,
                information.st_mtime_ns, information.st_ctime_ns)

    def prepare(self, path):
        path = Path(path).absolute()
        try:
            if path.suffix.lower() != ".ts":
                self.clear()
                self.ready.emit(str(path))
                return
            stamp = self._stamp(path)
            if (self.process is None and path == self.source and stamp == self.stamp and self.prepared
                    and self.prepared.is_file()):
                self.ready.emit(str(self.prepared))
                return
            self.clear()
            executable = shutil.which("ffmpeg")
            if not executable:
                self.failed.emit(tr(Msg.MEDIA_PREPARATION_UNAVAILABLE))
                return
            directory = self.directory or tempfile.gettempdir()
            if shutil.disk_usage(directory).free < stamp[2] + SPACE_RESERVE:
                self.failed.emit(tr(Msg.MEDIA_PREPARATION_SPACE))
                return
            self.temporary = tempfile.TemporaryDirectory(prefix="udeck-media-seek-", dir=directory)
            self.source, self.stamp = path, stamp
            self.prepared = Path(self.temporary.name) / "playback.mkv"
            self.maximum = stamp[2] + max(OUTPUT_ALLOWANCE, stamp[2] // 10)
            self.errors.clear()
            process = QProcess(self)
            self.process = process
            process.setStandardOutputFile(QProcess.nullDevice())
            process.readyReadStandardError.connect(lambda: self._read(process))
            process.finished.connect(lambda code, status: self._finished(process, code, status))
            process.errorOccurred.connect(lambda error: self._error(process, error))
            self.started = time.monotonic()
            self.timer.start()
            process.start(executable, [
                "-nostdin", "-hide_banner", "-loglevel", "error",
                "-protocol_whitelist", "file,pipe", "-f", "mpegts", "-i", str(path),
                "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
                "-map_metadata", "0", "-map_chapters", "0",
                "-c", "copy", "-f", "matroska", str(self.prepared),
            ])
        except OSError as error:
            self._fail(str(error))

    def _read(self, process):
        if process is self.process:
            self.errors.extend(bytes(process.readAllStandardError()))
            del self.errors[:-STDERR_LIMIT]

    def _poll(self):
        if not self.process:
            return
        try:
            if (time.monotonic() - self.started) * 1000 >= PREPARE_TIMEOUT_MS:
                self._fail(tr(Msg.MEDIA_PREPARATION_TIMED_OUT))
            elif self.prepared.exists() and self.prepared.stat().st_size > self.maximum:
                self._fail(tr(Msg.MEDIA_PREPARATION_SPACE))
        except OSError as error:
            self._fail(str(error))

    def _finished(self, process, code, status):
        self._read(process)
        if process is not self.process:
            return
        if code or status != QProcess.ExitStatus.NormalExit:
            self._fail(self.errors.decode("utf-8", errors="replace").strip() or process.errorString())
            return
        try:
            if self._stamp(self.source) != self.stamp:
                raise OSError(tr(Msg.THE_FILE_HAS_CHANGED_REFRESH_THE_LIBRARY_BEFORE_OPENING_IT))
            information = self.prepared.lstat()
            if not stat.S_ISREG(information.st_mode) or not information.st_size:
                raise OSError(tr(Msg.MEDIA_PREPARATION_UNAVAILABLE))
            if information.st_size > self.maximum:
                raise OSError(tr(Msg.MEDIA_PREPARATION_SPACE))
        except OSError as error:
            self._fail(str(error))
            return
        self.timer.stop()
        self.process = None
        process.deleteLater()
        self.ready.emit(str(self.prepared))

    def _error(self, process, error):
        if process is self.process:
            self._fail(process.errorString())

    def _fail(self, error):
        self.clear()
        self.failed.emit(error)

    def clear(self):
        self.timer.stop()
        process, self.process = self.process, None
        temporary, self.temporary = self.temporary, None
        self.source = self.stamp = self.prepared = None
        self.errors.clear()
        if process:
            def dispose(*_arguments):
                if process.state() == QProcess.ProcessState.NotRunning:
                    if temporary:
                        temporary.cleanup()
                    process.deleteLater()

            process.finished.connect(dispose)
            process.errorOccurred.connect(dispose)
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
            dispose()
        elif temporary:
            temporary.cleanup()

    def close(self):
        self.clear()
        for process in self.findChildren(QProcess):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(PROCESS_EXIT_TIMEOUT_MS)
