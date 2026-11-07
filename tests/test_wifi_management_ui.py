import json
from copy import deepcopy

from test_wifi_ui import choose, open_usb
from test_wifi_ui import controller as controller_fixture

controller = controller_fixture


def open_builtin(control):
    control.activateSetting("wifi")
    control.chooseModal(next(i for i, item in enumerate(control.modal["options"]) if item.get("deviceId") == "builtin"))
    choose(control, "wifi-connect")


def test_a_opens_network_menu_and_back_keeps_network_focus(controller):
    open_usb(controller)
    key = controller.modal["key"]
    choose(controller, "wifi-connect")
    assert controller.modal["source"] == "wifi-network"
    assert any(item["action"] == "wifi-join" for item in controller.modal["options"])
    controller.dispatch("back")
    assert controller.modal["key"] == key
    assert controller.modal["options"][controller.modal["index"]]["action"] == "wifi-connect"


def test_forget_requires_confirmation_then_updates_the_parent_network_menu(controller):
    open_builtin(controller)
    choose(controller, "wifi-forget")
    assert controller.modal["kind"] == "confirm" and controller.modal["index"] == 0
    controller.dispatch("accept")
    assert "wifi_forget" not in controller.backend.actions
    choose(controller, "wifi-forget")
    controller.dispatch("right")
    controller.dispatch("accept")
    assert "wifi_forget" in controller.backend.actions
    assert controller.modal["source"] == "wifi-network"
    assert not controller.data["wifi"]["devices"][0]["connected"]
    assert any(item["action"] == "wifi-join" for item in controller.modal["options"])


def test_password_validation_retains_input_and_x_toggles_visibility(controller):
    open_builtin(controller)
    choose(controller, "wifi-password")
    controller.editText("short")
    controller.dispatch("accept")
    assert controller.modal["kind"] == "text" and controller.modal["text"] == "short"
    assert controller.modal.get("error")
    controller.dispatch("context")
    assert controller.modal["reveal"] is True
    controller.editText("new-test-password")
    controller.dispatch("accept")
    assert controller.modal["source"] == "wifi-network"
    assert "wifi_update_password" in controller.backend.actions
    assert controller.data["wifi"]["devices"][0]["connected"] == "Workshop"
    assert "new-test-password" not in controller.snapshotJson


def test_saved_profiles_are_manageable_while_wifi_is_off(controller):
    controller.data["wifi"]["enabled"] = False
    open_builtin(controller)
    actions = {item["action"]: item for item in controller.modal["options"]}
    assert actions["wifi-join"]["disabled"]
    assert not actions["wifi-forget"].get("disabled")
    assert not actions["wifi-autoconnect"].get("disabled")


def test_shared_profile_changes_are_disabled_but_independent_join_is_available(controller):
    open_usb(controller)
    choose(controller, "wifi-connect")
    actions = {item["action"]: item for item in controller.modal["options"]}
    assert not actions["wifi-join"].get("disabled")
    assert actions["wifi-forget"]["disabled"]
    assert actions["wifi-password"]["disabled"]
    assert actions["wifi-autoconnect"]["disabled"]


def test_network_menu_survives_ap_replacement_and_profile_removal(controller):
    open_builtin(controller)
    key = controller.modal["key"]
    wifi = deepcopy(controller.data["wifi"])
    wifi["devices"][0]["networks"][0]["id"] = "replacement-ap"
    wifi["devices"][0]["saved"] = []
    controller.backend.updated.emit({"wifi": wifi})
    assert controller.modal["key"] == key
    assert controller.modal["source"] == "wifi-network"
    assert not any(item["action"] == "wifi-forget" for item in controller.modal["options"])


def test_multiple_saved_configurations_require_explicit_selection(controller):
    original = controller.data["wifi"]["devices"][0]["saved"][0]
    duplicate = {**original, "id": "other", "uuid": "other-config", "name": "Workshop alternate"}
    controller.data["wifi"]["devices"][0]["saved"].append(duplicate)
    open_builtin(controller)
    assert controller.modal["source"] == "wifi-profiles"
    controller.chooseModal(1)
    assert controller.modal["profileUuid"] == "other-config"


def test_network_details_use_only_selected_adapters_addresses(controller):
    controller.data["wifi"]["devices"][0]["addresses"] = {"ip": ["10.8.0.2/24"], "gateway": ["10.8.0.1"], "dns": ["10.8.0.1"]}
    controller.data["wifi"]["devices"][1]["addresses"] = {"ip": ["192.168.99.4/24"], "gateway": [], "dns": []}
    open_builtin(controller)
    choose(controller, "wifi-details")
    text = json.dumps(controller.modal, ensure_ascii=False)
    assert "10.8.0.2/24" in text
    assert "192.168.99.4" not in text


def test_networkmanager_epoch_change_dismisses_its_password_overlay(controller):
    open_builtin(controller)
    choose(controller, "wifi-password")
    wifi = deepcopy(controller.data["wifi"])
    wifi["epoch"] = "replacement-networkmanager"
    controller.backend.updated.emit({"wifi": wifi})
    assert controller.modal["source"] == "wifi"
    assert not any(item.get("kind") == "text" for item in controller._modals)


def test_active_operation_never_retargets_an_explicitly_selected_configuration(controller):
    device = controller.data["wifi"]["devices"][0]
    original = device["saved"][0]
    device["saved"].append({**original, "id": "other", "uuid": "other", "name": "Workshop alternate", "active": False})
    device["operation"] = {"id": "completed", "profileUuid": original["uuid"], "status": "connected"}
    open_builtin(controller)
    assert controller.modal["source"] == "wifi-profiles"
    controller.chooseModal(next(i for i, p in enumerate(controller.modal["options"]) if p.get("profileUuid") == "other"))
    assert controller.modal["profileUuid"] == "other"
    forget = next(p for p in controller.modal["options"] if p["action"] == "wifi-forget")
    assert forget["payload"]["profileUuid"] == "other"
    controller.backend.updated.emit({"wifi": deepcopy(controller.data["wifi"])})
    assert controller.modal["profileUuid"] == "other"


def test_external_deletion_never_selects_a_different_saved_configuration(controller):
    device = controller.data["wifi"]["devices"][0]
    original = deepcopy(device["saved"][0])
    open_builtin(controller)
    wifi = deepcopy(controller.data["wifi"])
    wifi["devices"][0]["saved"] = [{**original, "uuid": "different", "id": "different"}]
    controller.backend.updated.emit({"wifi": wifi})
    assert not any(p["action"] in ("wifi-forget", "wifi-password", "wifi-autoconnect") for p in controller.modal["options"])


def test_saved_network_details_match_its_scanned_signal(controller):
    open_usb(controller)
    choose(controller, "wifi-saved")
    choose(controller, "wifi-saved-connect")
    choose(controller, "wifi-details")
    assert "98%" in json.dumps(controller.modal)


def test_unplug_while_changing_password_discards_only_its_overlay(controller):
    open_builtin(controller)
    choose(controller, "wifi-password")
    controller.editText("temporary-password")
    wifi = deepcopy(controller.data["wifi"])
    wifi["devices"] = [d for d in wifi["devices"] if d["id"] != "builtin"]
    controller.backend.updated.emit({"wifi": wifi})
    assert controller.modal["source"] == "wifi"
    assert "temporary-password" not in controller.snapshotJson
    assert "wifi_update_password" not in controller.backend.actions


def test_mock_cancel_rejects_stale_operation_without_disconnecting(controller):
    device = controller.backend.state["wifi"]["devices"][0]
    device["operation"] = {"id": "current", "status": "connecting"}
    controller.backend.request("wifi_cancel_connect", {"deviceId": "builtin", "operationId": "older"})
    assert device["connected"] == "Workshop" and device["deviceState"] == 100
    assert device["operation"]["id"] == "current"
