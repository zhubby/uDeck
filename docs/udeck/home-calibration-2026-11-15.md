# Home calibration status removal

uDeck **0.2.24** hides the button calibration status on Home and lets the
description use the available header width. Calibration remains available in
Settings; status on other pages is unchanged.

Application revision: `05d382ee9dec25bc5d0f750cb9a4ad4d8161d2b0`.
The arm64 package SHA-256 is
`c7322ec3dbeb922a11d671c6ae1ca0bef8bc31f00fa5112b537783155951e3ff`.

## Verification

- Existing Home unit and Qt regressions: **38 passed**. Qt scenarios cover
  English/Classic, Chinese/Classic and Chinese/Dark at 1280×720, 960×600 and
  1920×1080, including navigation and restored focus.
- Ruff, release version validation and `git diff --check` passed.
- All **508** tracked application files match both the binary package and
  source archive, and match the installed files on uConsole `192.168.11.59`.
- Installed mock smoke and preflight passed; `dpkg --verify udeck` was clean.
- The existing session restarted the desktop shell. The compositor, session,
  native game and other applications kept their original processes (**11**
  total). **121** protected
  files were unchanged, and cloud configuration matched the previous verified
  installation after excluding the service's `lastSync` field. Active bisync
  work files were excluded from byte comparison.
- The running game returned to Home through the existing compositor shortcut
  using a temporary virtual keyboard. This does not establish physical-key
  acceptance of the separately reported Ctrl+Alt+Esc issue.
- A real `grim` screenshot confirms that the Home calibration label is absent.

Local evidence is retained under ignored
`artifacts/home-calibration-0.2.24-20261115/`, including
`device-evidence/home-after.png`. Uploaded installers and diagnostic staging
are removed after verification; the cleanup receipt is kept under
`~/.local/state/udeck/device-tests/` on the device.
