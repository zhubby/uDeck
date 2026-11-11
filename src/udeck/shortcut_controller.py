"""Button-first settings for the registered system shortcuts."""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Slot

from .i18n import error_text, tr
from .shortcuts import (
    ACTION_BY_ID,
    ACTIONS,
    GROUPS,
    ShortcutConflict,
    ShortcutStore,
    binding_label,
    key_hint,
    label,
)


class ShortcutControls:
    def _init_shortcuts(self):
        self.shortcut_session = None
        self.shortcut_error = ''
        self.shortcut_recorder = None
        self._capture_pending = False
        self._capture_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='udeck-screenshot')
        self.screenshotFinished.connect(self._screenshot_finished)
        try:
            self.shortcut_store = ShortcutStore(self.config.path.with_name('shortcuts.json'))
        except (OSError, ValueError) as error:
            self.shortcut_store = None
            self.shortcut_error = error_text(error)

    def attachShortcutSession(self, session):
        self.shortcut_session = session
        session.changed.connect(self._refresh_shortcuts)
        session.finished.connect(self._shortcut_finished)

    def _shortcut_state(self):
        return {'available': self.mock or bool(self.shortcut_session and self.shortcut_session.available),
                'applied': self.mock or bool(self.shortcut_session and self.shortcut_session.applied),
                'pending': bool(self.shortcut_session and self.shortcut_session.busy),
                'error': self.shortcut_error or (self.shortcut_session.error if self.shortcut_session else ''),
                'bindings': self.shortcut_store.bindings() if self.shortcut_store else {},
                'backup': self.shortcut_session.backup if self.shortcut_session else ''}

    def _shortcut_body(self):
        state = self._shortcut_state()
        if state['pending']:
            return tr('Applying shortcut change…')
        if state['error']:
            return state['error']
        if not state['available']:
            return tr('Global shortcuts require the current labwc session')
        return tr('Changes apply immediately') if not self.mock else tr('Preview bindings; desktop shortcuts are unchanged')

    def _shortcut_hints(self, identifier, title):
        values = self.shortcut_store.bindings()[identifier][:1] if self.shortcut_store else []
        return [key_hint(value, title) for value in values]

    def _open_shortcuts(self):
        if not self.shortcut_store:
            self.notify(self.shortcut_error)
            return
        options = [{'id': key, 'label': name, 'action': 'shortcut-group', 'group': key,
                    'subtitle': tr('{count} system actions', count=sum(action.group == key for action in ACTIONS)),
                    'wrapSubtitle': True}
                   for key, name in GROUPS.items()]
        options.append({'id': 'reset-all', 'label': tr('Restore all defaults'), 'action': 'shortcut-reset-all'})
        self._menu(tr('Shortcut bindings'), options, source='shortcuts', body=self._shortcut_body())

    def _shortcut_status(self, action):
        values = self.shortcut_store.bindings()[action.id]
        status = tr('Unbound') if not values else tr('Default') if tuple(values) == action.defaults else tr('Custom')
        available = self.mock or (bool(shutil.which('grim')) if action.feature == 'screenshot' else
                                  self.data.get(action.feature, {}).get('available', True))
        if not self.mock and action.feature == 'audio':
            available = available and bool(self.data.get('audio', {}).get('outputs'))
        if not self.mock and action.feature == 'logout':
            available = os.environ.get('XDG_SESSION_DESKTOP') == 'udeck'
        if not available:
            status += ' · ' + tr('Feature unavailable')
        return status

    def _shortcut_group_options(self, group):
        return [{'id': action.id, 'label': action.label, 'action': 'shortcut-detail', 'actionId': action.id,
                 'subtitle': (binding_label(self.shortcut_store.bindings()[action.id]) + ' · '
                              if self.shortcut_store.bindings()[action.id] else '')
                             + self._shortcut_status(action), 'wrapSubtitle': True}
                for action in ACTIONS if action.group == group]

    def _shortcut_detail_options(self, identifier):
        disabled = (not self.mock and not self._shortcut_state()['available']) or self._shortcut_state()['pending']
        common = {'disabled': disabled, 'reason': self._shortcut_body()}
        values = self.shortcut_store.bindings()[identifier]
        result = [{'id': str(index), 'label': label(value), 'subtitle': tr('Press to change this binding'), 'wrapSubtitle': True,
                   'action': 'shortcut-record', 'actionId': identifier, 'bindingIndex': index, **common}
                  for index, value in enumerate(values)]
        result += [
            {'id': 'add', 'label': tr('Add a binding'), 'action': 'shortcut-record', 'actionId': identifier, 'bindingIndex': -1, **common},
            {'id': 'clear', 'label': tr('Clear all bindings'), 'action': 'shortcut-write', 'actionId': identifier, 'sequences': [], **common},
            {'id': 'reset', 'label': tr('Restore default'), 'action': 'shortcut-write', 'actionId': identifier, 'sequences': None, **common},
        ]
        return result

    def _refresh_shortcuts(self):
        if not self.shortcut_store:
            return
        for modal in self._modals:
            source = modal.get('source')
            if source not in ('shortcuts', 'shortcuts-group', 'shortcut-action'):
                continue
            options = modal['options']
            selected = options[min(modal['index'], len(options) - 1)]['id'] if options else ''
            modal['options'] = self._shortcut_menu_options(modal)
            modal['index'] = next((index for index, item in enumerate(modal['options']) if item['id'] == selected), 0)
        self._publish()

    def _shortcut_menu_options(self, modal):
        if modal['source'] == 'shortcut-action':
            modal['body'] = self._shortcut_status(ACTION_BY_ID[modal['actionId']])
            return self._shortcut_detail_options(modal['actionId'])
        modal['body'] = self._shortcut_body()
        return self._shortcut_group_options(modal['group']) if modal['source'] == 'shortcuts-group' else modal['options']

    def _shortcut_option(self, option):
        action = option.get('action', '')
        if not action.startswith('shortcut-'):
            return False
        if action == 'shortcut-group':
            group = option['group']
            self._menu(GROUPS[group], self._shortcut_group_options(group), source='shortcuts-group',
                       group=group, body=self._shortcut_body())
        elif action == 'shortcut-detail':
            identifier = option['actionId']
            self._menu(ACTION_BY_ID[identifier].label, self._shortcut_detail_options(identifier),
                       source='shortcut-action', actionId=identifier, body=self._shortcut_status(ACTION_BY_ID[identifier]))
        elif action == 'shortcut-record':
            if self.shortcut_recorder:
                self.shortcut_recorder.open(option['actionId'], option['bindingIndex'])
            else:
                self.notify(tr('Shortcut recording is unavailable'))
        elif action == 'shortcut-reset-all':
            self._confirm(tr('Restore all shortcut defaults?'), tr('Custom bindings will be replaced.'),
                          {'action': 'shortcut-reset-confirmed'})
        elif action == 'shortcut-reset-confirmed':
            self._save_shortcuts({})
        elif action == 'shortcut-write':
            self._write_shortcut(option['actionId'], option['sequences'], transfer=option.get('transfer', False))
        return True

    @Slot(str, str, int)
    def setShortcut(self, identifier, sequence, index):
        try:
            values = list(self.shortcut_store.bindings()[identifier])
            if index == -1:
                values.append(sequence)
            elif 0 <= index < len(values):
                values[index] = sequence
            else:
                raise ValueError(tr('Binding changed; open it again'))
            self._write_shortcut(identifier, values)
        except (OSError, ValueError, KeyError, AttributeError) as error:
            self.notify(error_text(error))

    def _write_shortcut(self, identifier, sequences, *, transfer=False):
        try:
            if self._shortcut_state()['pending']:
                raise ValueError(tr('Wait for the current shortcut change'))
            store = ShortcutStore(self.shortcut_store.path)
            proposal = store.propose(identifier, sequences, transfer=transfer)
            self._save_shortcuts(proposal)
        except ShortcutConflict as error:
            occupied = ''
            for sequence, key in error.conflicts:
                occupied = occupied + ('\n' if occupied else '') + label(sequence) + ' → ' + ACTION_BY_ID[key].label
            self._confirm(tr('Transfer this shortcut?'), occupied,
                          {'action': 'shortcut-write', 'actionId': identifier, 'sequences': sequences, 'transfer': True})
        except (OSError, ValueError) as error:
            self.notify(error_text(error))

    def _save_shortcuts(self, overrides):
        try:
            if self.mock:
                self.shortcut_store.save(overrides)
                self._refresh_shortcuts()
                self.notify(tr('Preview shortcut saved'))
            elif self.shortcut_session:
                self.shortcut_session.apply(overrides)
            else:
                raise ValueError(tr('Global shortcuts require the current labwc session'))
        except (OSError, ValueError) as error:
            self.notify(error_text(error))

    def _shortcut_finished(self, result):
        if result['success']:
            self.shortcut_store = self.shortcut_session.store
        self._refresh_shortcuts()
        if result['kind'] == 'bindings':
            self.notify(tr('Shortcut saved') if result['success'] else result['error'])

    @Slot(str, result=bool)
    def globalAction(self, action):
        state = self.data.get('sessionInput', {})
        if not self.mock and not (state.get('available') and state.get('active') and not state.get('locked')):
            return False
        if action in ('apps', 'files', 'settings'):
            self._cancel_modals()
            self.setPage(action)
            self.present.emit()
        elif action in ('blank', 'logout', 'reboot', 'poweroff'):
            if action != 'blank':
                if any(modal.get('kind') == 'confirm' for modal in self._modals):
                    self.present.emit()
                    return True
                self._cancel_modals()
                self.present.emit()
            self.activateSetting(action)
        elif action == 'screenshot':
            if self.mock:
                self.notify(tr('Screenshot preview; no desktop image was saved'))
            elif not self._capture_pending:
                from .screenshot import capture_screen
                self._capture_pending = True
                future = self._capture_executor.submit(capture_screen)
                future.add_done_callback(lambda result: self.screenshotFinished.emit(result))
        elif action in ('volume-up', 'volume-down', 'mute', 'brightness-up', 'brightness-down'):
            component = 'brightness' if action.startswith('brightness-') else 'audio'
            value = self.data.get(component, {})
            if not value.get('available') or (component == 'audio' and not value.get('outputs')):
                self.notify(tr('Feature unavailable'))
                return False
            if action == 'mute':
                self._system('mute')
            else:
                level = value.get('value' if component == 'brightness' else 'volume', 0)
                step = 0.05 if action.endswith('-up') else -0.05
                self._system('brightness' if component == 'brightness' else 'volume',
                             {'value': max(0.05 if component == 'brightness' else 0, min(1.0, level + step))})
        else:
            return False
        return True

    @Slot(object)
    def _screenshot_finished(self, future):
        self._capture_pending = False
        try:
            path = future.result()
            self.feedback('success')
            self.notify(tr('Screenshot saved: {path}', path=str(path)))
        except Exception as error:
            self.notify(tr('Could not save screenshot: {error}', error=error_text(error)))

    def _close_shortcuts(self):
        if self.shortcut_recorder:
            self.shortcut_recorder.close()
        if self.shortcut_session:
            self.shortcut_session.close()
        self._capture_executor.shutdown(wait=True, cancel_futures=True)
