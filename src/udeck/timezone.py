"""System time-zone labels and region navigation shared by real and preview UIs."""

from PySide6.QtCore import QDateTime, QTimeZone

from .i18n import Msg, tr

TIMEDATE = "org.freedesktop.timedate1"
TIMEDATE_PATH = "/org/freedesktop/timedate1"
REGIONS = {
    "Africa": tr(Msg.AFRICA), "America": tr(Msg.AMERICAS), "Antarctica": tr(Msg.ANTARCTICA),
    "Arctic": tr(Msg.ARCTIC), "Asia": tr(Msg.ASIA), "Atlantic": tr(Msg.ATLANTIC),
    "Australia": tr(Msg.AUSTRALIA), "Europe": tr(Msg.EUROPE), "Indian": tr(Msg.INDIAN_OCEAN),
    "Pacific": tr(Msg.PACIFIC), "Other": tr(Msg.UTC_AND_OTHER_ZONES),
}


def region(zone):
    first, separator, _ = zone.partition("/")
    return first if separator and first in REGIONS and first != "Other" else "Other"


def zone_label(zone):
    return zone.replace("_", " ")


def zone_summary(state):
    return state.get("current") or tr(Msg.NOT_AVAILABLE)


def local_clock(zone):
    now = QDateTime.currentDateTimeUtc()
    target = QTimeZone(zone.encode()) if zone else QTimeZone.systemTimeZone()
    return now.toTimeZone(target if target.isValid() else QTimeZone.systemTimeZone()).toString("HH:mm")
