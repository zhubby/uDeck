"""System time-zone labels and region navigation shared by real and preview UIs."""

from PySide6.QtCore import QDateTime, QTimeZone

from .i18n import tr

TIMEDATE = "org.freedesktop.timedate1"
TIMEDATE_PATH = "/org/freedesktop/timedate1"
REGIONS = {
    "Africa": tr("Africa"), "America": tr("Americas"), "Antarctica": tr("Antarctica"),
    "Arctic": tr("Arctic"), "Asia": tr("Asia"), "Atlantic": tr("Atlantic"),
    "Australia": tr("Australia"), "Europe": tr("Europe"), "Indian": tr("Indian Ocean"),
    "Pacific": tr("Pacific"), "Other": tr("UTC and other zones"),
}


def region(zone):
    first, separator, _ = zone.partition("/")
    return first if separator and first in REGIONS and first != "Other" else "Other"


def zone_label(zone):
    return zone.replace("_", " ")


def zone_summary(state):
    return state.get("current") or tr("Not available")


def local_clock(zone):
    now = QDateTime.currentDateTimeUtc()
    target = QTimeZone(zone.encode()) if zone else QTimeZone.systemTimeZone()
    return now.toTimeZone(target if target.isValid() else QTimeZone.systemTimeZone()).toString("HH:mm")
