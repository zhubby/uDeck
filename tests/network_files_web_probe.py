import json
import sys

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

SCENARIOS = {
    "initial-reconnect": """
        await waitFor(() => !document.getElementById('load-error').hidden && document.getElementById('connection').classList.contains('offline'));
        await config();
        assert(document.querySelector('[data-path="hello.txt"]'), 'A recovered initial connection did not load the files');
        assert(document.getElementById('load-error').hidden, 'A recovered initial connection retained the error');
    """,
    "initial-reconnect-folder": """
        await waitFor(() => !document.getElementById('load-error').hidden && document.getElementById('connection').classList.contains('offline'));
        await config();
        assert(location.hash === '#Documents', 'Reconnection changed the requested folder link');
        assert(document.querySelector('[data-path="Documents/readme.txt"]'), 'Reconnection opened the root instead of the linked folder');
        assert(!document.querySelector('[data-path="hello.txt"]'), 'Root files leaked into the linked folder listing');
        assert(document.querySelector('#breadcrumbs button[aria-current="page"]').textContent === 'Documents', 'Breadcrumbs do not match the linked folder');
        assert(document.getElementById('load-error').hidden, 'A recovered folder connection retained the error');
    """,
    "reconnect-refresh": """
        const originalFetch = window.fetch;
        window.fetch = () => Promise.reject(new TypeError('Network unavailable'));
        await load();
        assert(document.getElementById('connection').classList.contains('offline'), 'The outage was not detected');
        window.fetch = originalFetch;
        const response = await fetch('/api/folders', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-UDeck-Request': state.token}, body: JSON.stringify({path: 'returned-online'})});
        assert(response.ok, 'Could not simulate another client creating a file while disconnected');
        await config();
        assert(document.querySelector('[data-path="returned-online"]'), 'Reconnecting to the same service left a stale file listing');
        assert(document.getElementById('load-error').hidden, 'Reconnection did not clear the file listing error');
    """,
    "failed-load": """
        document.querySelector('[data-path="hello.txt"] .choose').click();
        assert(!document.getElementById('selection').hidden, 'The source file was not selected');
        const originalFetch = window.fetch;
        window.fetch = () => Promise.reject(new TypeError('Network unavailable'));
        await load();
        assert(!document.getElementById('load-error').hidden, 'A failed listing did not show the error');
        assert(document.getElementById('files').hidden, 'A failed listing still exposes outdated file actions');
        assert(document.getElementById('selection').hidden, 'A failed listing still exposes destructive selection actions');
        window.fetch = originalFetch;
        document.getElementById('retry').click();
        await waitFor(() => !document.getElementById('files').hidden && document.getElementById('load-error').hidden);
        assert(document.querySelectorAll('.choose:checked').length === 0, 'Retry restored a stale selection');
    """,
    "missing-folder": """
        navigate('missing');
        await waitFor(() => !document.getElementById('load-error').hidden);
        assert(!document.getElementById('connection').classList.contains('offline'), 'A missing folder was reported as a lost device connection');
    """,
    "history": """
        document.querySelector('[data-path="Documents"] .open').click();
        await waitFor(() => document.querySelector('[data-path="Documents/readme.txt"]'));
        const search = document.getElementById('search');
        search.value = 'readme';
        search.dispatchEvent(new Event('input'));
        await waitFor(() => document.querySelectorAll('.file').length === 1);
        history.back();
        await waitFor(() => location.hash === '');
        await waitFor(() => document.querySelectorAll('#breadcrumbs button').length === 1);
        assert(search.value === '', 'History navigation retained the previous folder search');
        await waitFor(() => document.querySelector('[data-path="hello.txt"]'));
    """,
    "destination-loading": """
        document.querySelector('[data-path="hello.txt"] .choose').click();
        document.getElementById('copy').click();
        await waitFor(() => document.getElementById('dialog').open);
        const originalFetch = window.fetch;
        let release;
        const pending = new Promise(resolve => release = resolve);
        window.fetch = async (input, options) => {
            if (String(input).startsWith('/api/files?') && new URL(input, location.href).searchParams.get('path') === 'target') await pending;
            return originalFetch(input, options);
        };
        [...document.querySelectorAll('.folder-picker button')].find(button => button.textContent === 'target').click();
        const confirm = document.querySelector('#dialog-actions .primary');
        assert(confirm.disabled, 'Destination confirmation remained enabled during navigation');
        document.getElementById('dialog-form').dispatchEvent(new Event('submit', {cancelable: true}));
        assert(document.getElementById('dialog').open, 'Enter confirmed a folder that is still loading');
        release();
        await waitFor(() => !confirm.disabled);
        assert(document.querySelector('.picker-path').textContent.endsWith(' / target'), 'The wrong destination loaded');
        confirm.click();
        await waitFor(async () => {
            const response = await fetch('/api/files?path=target');
            return (await response.json()).entries.some(row => row.name === 'hello.txt');
        });
    """,
    "hidden-destination": """
        document.getElementById('hidden').checked = true;
        document.getElementById('hidden').dispatchEvent(new Event('change'));
        await waitFor(() => document.querySelector('[data-path=".hidden-folder"]'));
        document.querySelector('[data-path="hello.txt"] .choose').click();
        document.getElementById('copy').click();
        await waitFor(() => document.getElementById('dialog').open);
        assert([...document.querySelectorAll('.folder-picker button')].some(button => button.textContent === '.hidden-folder'),
            'Visible hidden folders cannot be chosen as destinations');
    """,
    "destination-race": """
        document.querySelector('[data-path="hello.txt"] .choose').click();
        document.getElementById('copy').click();
        await waitFor(() => document.getElementById('dialog').open);
        const originalFetch = window.fetch;
        let release, finished = false;
        const pending = new Promise(resolve => release = resolve);
        window.fetch = async (input, options) => {
            const delayed = String(input).startsWith('/api/files?') && new URL(input, location.href).searchParams.get('path') === 'target';
            if (delayed) await pending;
            const response = await originalFetch(input, options);
            if (delayed) finished = true;
            return response;
        };
        const buttons = [...document.querySelectorAll('.folder-picker button')];
        buttons.find(button => button.textContent === 'target').click();
        buttons.find(button => button.textContent === 'Documents').click();
        await waitFor(() => document.querySelector('.picker-path').textContent.endsWith(' / Documents'));
        release();
        await waitFor(() => finished);
        await new Promise(resolve => setTimeout(resolve, 100));
        assert(document.querySelector('.picker-path').textContent.endsWith(' / Documents'), 'An old directory response replaced the latest destination');
    """,
    "destination-pagination": """
        document.querySelector('[data-path="hello.txt"] .choose').click();
        document.getElementById('copy').click();
        await waitFor(() => document.getElementById('dialog').open);
        [...document.querySelectorAll('.folder-picker button')].find(button => button.textContent === 'many').click();
        await waitFor(() => document.querySelector('.picker-path').textContent.endsWith(' / many'));
        const more = document.querySelector('.folder-picker .picker-more');
        assert(more, 'Destinations beyond the first 500 folders are unreachable');
        more.click();
        await waitFor(() => [...document.querySelectorAll('.folder-picker button')].some(button => button.textContent === 'folder-500'));
        [...document.querySelectorAll('.folder-picker button')].find(button => button.textContent === 'folder-500').click();
        await waitFor(() => document.querySelector('.picker-path').textContent.endsWith(' / many / folder-500'));
        document.querySelector('#dialog-actions .primary').click();
        await waitFor(async () => (await (await fetch('/api/files?path=many/folder-500')).json()).entries.some(row => row.name === 'hello.txt'));
    """,
    "file-workflow": """
        const upload = () => {
            const transfer = new DataTransfer();
            transfer.items.add(new File(['browser upload'], 'uploaded.txt', {type: 'text/plain'}));
            const input = document.getElementById('file-input');
            input.files = transfer.files;
            input.dispatchEvent(new Event('change'));
        };
        upload();
        await waitFor(() => document.querySelector('[data-path="uploaded.txt"]'));
        assert(await (await fetch('/api/download?path=uploaded.txt')).text() === 'browser upload', 'Uploaded bytes changed');
        upload();
        await waitFor(() => document.getElementById('dialog').open);
        document.querySelector('#dialog-actions .primary').click();
        await waitFor(() => document.querySelector('[data-path="uploaded (2).txt"]'));
        document.querySelector('[data-path="uploaded.txt"] .choose').click();
        document.getElementById('rename').click();
        await waitFor(() => document.getElementById('dialog').open);
        document.querySelector('#dialog-content input').value = '已重命名.txt';
        document.querySelector('#dialog-actions .primary').click();
        await waitFor(() => document.querySelector('[data-path="已重命名.txt"]'));
        for (const [action, folder] of [['copy', 'target'], ['move', 'Documents']]) {
            document.querySelector('[data-path="已重命名.txt"] .choose').click();
            document.getElementById(action).click();
            await waitFor(() => document.getElementById('dialog').open && document.querySelector('.folder-picker'));
            [...document.querySelectorAll('.folder-picker button')].find(button => button.textContent === folder).click();
            await waitFor(() => document.querySelector('.picker-path').textContent.endsWith(' / ' + folder));
            document.querySelector('#dialog-actions .primary').click();
            await waitFor(() => !document.getElementById('dialog').open);
            await waitFor(() => [...document.querySelectorAll('#transfer-items progress')].every(item => item.value === 1));
            await waitFor(async () => (await (await fetch('/api/files?path=' + folder)).json()).entries.some(row => row.name === '已重命名.txt'));
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        await waitFor(() => !document.querySelector('[data-path="已重命名.txt"]'));
        document.querySelector('[data-path="Documents"] .open').click();
        await waitFor(() => document.querySelector('[data-path="Documents/已重命名.txt"]'));
        document.querySelector('[data-path="Documents/已重命名.txt"] .choose').click();
        document.getElementById('trash').click();
        await waitFor(() => document.getElementById('dialog').open);
        document.querySelector('#dialog-actions .primary').click();
        await waitFor(() => !document.querySelector('[data-path="Documents/已重命名.txt"]'));
    """,
    "pagination": """
        document.querySelector('[data-path="pages"] .open').click();
        await waitFor(() => document.querySelectorAll('.file').length === 200);
        assert(!document.getElementById('load-more').hidden, 'Pagination cannot be reached');
        document.getElementById('load-more').click();
        await waitFor(() => document.querySelectorAll('.file').length === 205);
        assert(document.getElementById('load-more').hidden, 'Pagination did not end');
        document.getElementById('view-toggle').click();
        await waitFor(() => document.getElementById('files').classList.contains('files-list'));
        document.getElementById('descending').checked = true;
        document.getElementById('descending').dispatchEvent(new Event('change'));
        await waitFor(() => document.querySelector('.file').dataset.path === 'pages/item-204.txt');
        const search = document.getElementById('search');
        search.value = 'item-20';
        search.dispatchEvent(new Event('input'));
        await waitFor(() => document.querySelectorAll('.file').length === 5);
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'a', ctrlKey: true, bubbles: true}));
        await waitFor(() => document.querySelectorAll('.choose:checked').length === 5);
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
        assert(document.getElementById('selection').hidden, 'Escape did not clear the selection');
    """,
}


class ProbePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        if message.startswith("UDECK_WEB_RESULT:"):
            result = json.loads(message.removeprefix("UDECK_WEB_RESULT:"))
            print(json.dumps(result), flush=True)
            application.exit(0 if result["ok"] else 1)


application = QApplication(sys.argv)
page = ProbePage()
timer = QTimer()
timer.setSingleShot(True)
timer.timeout.connect(lambda: application.exit(2))
timer.start(30000)


def loaded(ok):
    if not ok:
        print("Network Files page failed to load", flush=True)
        application.exit(1)
        return
    readiness = "" if sys.argv[2].startswith("initial-reconnect") else "await waitFor(() => document.querySelector('[data-path=\"hello.txt\"]'));"
    page.runJavaScript("""
        (async () => {
            const assert = (condition, message) => { if (!condition) throw new Error(message); };
            const waitFor = async predicate => {
                const deadline = Date.now() + 10000;
                while (!(await predicate())) {
                    if (Date.now() > deadline) throw new Error('Browser condition timed out');
                    await new Promise(resolve => setTimeout(resolve, 20));
                }
            };
            try {
    """ + readiness + SCENARIOS[sys.argv[2]] + """
                console.log('UDECK_WEB_RESULT:' + JSON.stringify({ok: true}));
            } catch (error) {
                console.log('UDECK_WEB_RESULT:' + JSON.stringify({ok: false, error: error.stack || String(error),
                    diagnostics: {path: state.path, entries: state.entries.map(row => row.path),
                        generation: state.generation, connection: document.getElementById('connection').className,
                        loadError: document.getElementById('load-error-message').textContent,
                        toast: document.getElementById('toast').textContent,
                        tasks: state.tasks.map(task => ({name: task.name, state: task.state, detail: task.detail}))}}));
            }
        })();
    """)


page.loadFinished.connect(loaded)
page.setUrl(QUrl(sys.argv[1]))
status = application.exec()
page.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
sys.exit(status)
