Openroast
=========

|Gitter|

Openroast is an open source, cross-platform application for home coffee
roasting. Openroast is currently designed to interface with the
FreshRoast SR700 USB controlled coffee roaster, with the capability of
extending to any computer assisted home roasting device. Openroast makes
it simple to dial-in recipes in a repeatable, consistent manner allowing
a user to achieve the same results every time.

Features
--------

-  Roast Graph
-  Simplified user interface
-  Superior temperature control - ability to set specific target
   temperatures rather than just low, medium, or high heat settings
-  Create/Import/Export Recipes

Screenshots
-----------

|Roast Tab Screenshot| |Recipe Edit Tab Screenshot|

Installing Openroast
====================
Latest Release
--------------
Openroast 1.2 is currently in 'rc' or 'release candidate' phase. The alpha releases have done quite well with early testers, so the app is ready for a broader audience.

*For Windows or Mac, you do not need to install python interpreters or any other software, other than what is included in the install packages.*

- `Openroast 1.2 for Windows 10 64-bit`_ (for most Windows users)
- `Openroast 1.2 for Mac`_
- `Openroast 1.2 for Windows 10 32-bit`_ (for those running on very old hardware)

For Linux OSes (including Raspberry Pi), install with Python 3.13.

Standard desktop Linux::

    python3.13 -m venv .venv
    . .venv/bin/activate
    python -m pip install -U pip
    python -m pip install -e .[gui]

Raspberry Pi 2 (Raspbian 13/trixie) recommendation:

1. Install heavy GUI/scientific packages from apt (faster and more reliable on armv7):

   ``sudo apt install python3-pyqt5 python3-pyqtgraph``

2. Install Openroast in a venv:

   ``python -m pip install -e .``

If the venv cannot see apt-managed packages, create it with ``--system-site-packages``.

Running with backend modes
--------------------------

Openroast now uses explicit backend modes via ``--backend``:

- ``usb``: real FreshRoast SR700 USB hardware
- ``usb-mock``: simulated USB backend
- ``local``: local backend package (real local hardware path)
- ``local-mock``: simulated local backend

Examples::

    openroast --backend usb
    openroast --backend usb-mock
    openroast --backend local
    openroast --backend local-mock

If you run from source instead of the installed ``openroast`` command::

    python openroast/openroastapp.py --backend local-mock

Standalone local backend package
-------------------------------

This repository now also contains a reusable ``localroaster`` package for
non-USB roaster hardware. Openroast consumes it through a thin adapter, but the
controller package is intentionally frontend-agnostic so it can later back a
CLI, web UI, or other frontend.

Run the standalone mock demo::

    python -m localroaster.demo --seconds 10

Installation Instructions
-------------------------
- Windows - see `For Users: Installing Openroast for Windows`_
- Mac - see `For Users: Installing Openroast for Mac`_
- Ubuntu/Linux - see `For Developers: Installing and Running Openroast`_

Developer Corner
================
We have recently made this project easier to manage from a build generation perspective, facilitating future maintenance and updates. See `For Developers`_ pages in the project wiki for details.

AI co-authorship disclosure
---------------------------

This fork includes substantial AI-assisted and AI-authored changes (with very
few exceptions), primarily using GitHub Copilot with GPT-5.3-Codex.

Commit disclosure policy used in this repository:

- ``Assisted-by: TOOL (OPTIONAL: MODEL)`` when AI tooling helped with
  decisions or generated part of the change.
- ``Generated-by: TOOL (OPTIONAL: MODEL)`` when almost all of a change was
  generated through AI tooling.
- ``Co-authored-by`` is reserved for human co-authors and is not used for AI
  disclosure.

For details, see ``NOTICE_AI.rst``.

License
-------

The Openroast app code is released under GPL v3.

.. _Openroast 1.2 for Windows 10 64-bit: https://github.com/Roastero/Openroast/releases/tag/v1.2.0rc3
.. _Openroast 1.2 for Windows 10 32-bit: https://github.com/Roastero/Openroast/releases/tag/v1.2.0rc3
.. _Openroast 1.2 for Mac: https://github.com/Roastero/Openroast/releases/tag/v1.2.0rc3

.. _For Users\: Installing Openroast for Windows: https://github.com/Roastero/Openroast/wiki/For-Users:-Installing-Openroast-for-Windows
.. _For Users\: Installing Openroast for Mac: https://github.com/Roastero/Openroast/wiki/For-Users:-Installing-Openroast-for-Mac
.. _For Developers\: Installing and Running Openroast: https://github.com/Roastero/Openroast/wiki/For-Developers:-Installing-and-Running-Openroast
.. _For Developers: https://github.com/Roastero/Openroast/wiki/For-Developers

.. |Gitter| image:: https://badges.gitter.im/Join%20Chat.svg
   :target: https://gitter.im/Roastero/openroast?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge
.. |Roast Tab Screenshot| image:: docs/wiki/img/Openroast_1.2.png
.. |Recipe Edit Tab Screenshot| image:: docs/wiki/img/Openroast_1.2_recipeedit.png
