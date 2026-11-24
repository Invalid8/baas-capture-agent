# Changelog

Install: `baas-capture-agent-setup.exe` on Windows, `baas-capture-agent.deb` on Linux
(`sudo apt install ./baas-capture-agent.deb`). After installing, http://127.0.0.1:7501 shows the version
and whether the reader is ready.

## 0.2.5 (24 Nov 2026)

- Each of the three ways to reach the reader (libfprint on Linux, Windows Biometric Framework, U.are.U SDK)
  now uses one shared watcher that cancels the reader without touching the caller's stop. The bug fixed in
  0.2.4 came from readers setting it, and none of them can do that any more.
- A site can only cancel its own capture. Before, a console tab closing could stop a sign-in on the kiosk
  (or a test on the check page).
- The check page reacts only to its own Test, so another site's cancelled capture no longer shows "Stopped."
  there. If another site is using the reader, Test says "Reader is busy".
- New whole-capture tests for both Windows routes (fake DLLs, run on Windows in CI). 94 tests.
- Releases carry one file per system under fixed names: `baas-capture-agent-setup.exe`,
  `baas-capture-agent.deb`, plus `baas-probe.exe`.

## 0.2.4 (24 Nov 2026)

- Fixed: after several presses in a row the check page said "Stopped." and the press was lost. When
  libfprint's heat timer made the agent replace its reader helper, the retried capture was cancelled by the
  attempt before it. The bug came in with 0.2.3; **if you have 0.2.3, update.**
- The check page says "Good print." after a press (was "Got it · lift your finger.").

## 0.2.3 (23 Nov 2026)

Includes 0.2.2, which was tagged but not released.

- An unplugged reader shows as not connected at once, and a replugged one works again.
- libfprint runs in a helper process. It is replaced in about half a second when the reader is unplugged
  and plugged back in, or before libfprint's built-in three-minute heat timer would switch the reader off,
  so the reader keeps working without restarting the agent.
- Calmer wording: no "hold still"; "Lift your finger" as soon as the print is taken; presses on an empty
  glass stay silent.
- The press check is about four times faster (about 21 ms).
- The Linux USB address is written the same way on every system (fixed the Windows test run).
- Known problem: "Stopped." after several presses on the check page. Fixed in 0.2.4.

## 0.2.2 (23 Nov 2026)

Tagged but not released (a Windows-only test failed); everything in it is in 0.2.3.

## 0.2.1 (23 Nov 2026)

- Windows: reads the 4500 through the U.are.U SDK (dpfpdd.dll) as well as the Windows Biometric Framework,
  so PCs that already use DigitalPersona software keep it.
- The agent and its check page keep running on a Windows PC without fingerprint support, and say to install
  the WBF driver.
- Plain-answer check page, driver help, MIT licence.

## 0.2.0 (23 Nov 2026)

- Every image is a 500 ppi greyscale PNG, whatever the route.
- Blank and faint presses are asked for again inside the same capture; thresholds set from real 4500 presses.
- Live events (`/events`) so pages can say "Place your finger", "Lift your finger", "Press a little firmer".
- New sites are approved once on the PC; the kiosk and console are built in.
- Self-check page at http://127.0.0.1:7501 with reader status, checks, a Test button and recent presses.
- Capture log, driver doctor, panel icon, and a Windows setup that starts the agent at sign-in.

## 0.2.0-probe (23 Nov 2026)

- Diagnostic build for the first Windows test (`baas-probe.exe`). Not for normal use.
