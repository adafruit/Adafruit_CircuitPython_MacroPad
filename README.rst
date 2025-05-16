Introduction
============


.. image:: https://readthedocs.org/projects/adafruit-circuitpython-macropad/badge/?version=latest
    :target: https://docs.circuitpython.org/projects/macropad/en/latest/
    :alt: Documentation Status


.. image:: https://raw.githubusercontent.com/adafruit/Adafruit_CircuitPython_Bundle/main/badges/adafruit_discord.svg
    :target: https://adafru.it/discord
    :alt: Discord


.. image:: https://github.com/adafruit/Adafruit_CircuitPython_MacroPad/workflows/Build%20CI/badge.svg
    :target: https://github.com/adafruit/Adafruit_CircuitPython_MacroPad/actions
    :alt: Build Status


.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
    :target: https://github.com/astral-sh/ruff
    :alt: Code Style: Ruff

A helper library for the Adafruit MacroPad RP2040.


Dependencies
=============
This driver depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_

* `Adafruit's CircuitPython NeoPixel library
  <https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel>`_

* `Adafruit's CircuitPython HID library
  <https://github.com/adafruit/Adafruit_CircuitPython_HID>`_

* `Adafruit's CircuitPython MIDI library
  <https://github.com/adafruit/Adafruit_CircuitPython_MIDI>`_

* `Adafruit's CircuitPython Display Text library
  <https://github.com/adafruit/Adafruit_CircuitPython_Display_Text>`_

* `Adafruit's CircuitPython Simple Text Display library
  <https://github.com/adafruit/Adafruit_CircuitPython_Simple_Text_Display>`_

* `Adafruit's CircuitPython Debouncer library
  <https://github.com/adafruit/Adafruit_CircuitPython_Debouncer>`_

* `Adafruit's CircuitPython Ticks library
  <https://github.com/adafruit/Adafruit_CircuitPython_Ticks>`_


Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_
or individual libraries can be installed using
`circup <https://github.com/adafruit/circup>`_.

This library is designed to work withe the Adafruit MacroPad RP2040. Consider
purchasing one from the Adafruit shop:

`Adafruit MacroPad RP2040 Bare Bones <http://www.adafruit.com/products/5100>`_
`Adafruit MacroPad RP2040 Starter Kit <https://www.adafruit.com/product/5128>`_

Installing to a Connected CircuitPython Device with Circup
==========================================================

Make sure that you have ``circup`` installed in your Python environment.
Install it with the following command if necessary:

.. code-block:: shell

    pip3 install circup

With ``circup`` installed and your CircuitPython device connected use the
following command to install:

.. code-block:: shell

    circup install adafruit_macropad

Or the following command to update an existing version:

.. code-block:: shell

    circup update

Usage Example
=============
This example prints out the key pressed, the relative position of the rotary encoder and the
state of the rotary encoder switch.

.. code-block:: python

    from adafruit_macropad import MacroPad
    import time

    macropad = MacroPad()

    while True:
        key_event = macropad.keys.events.get()
        if key_event and key_event.pressed:
         print("Key pressed: {}".format(key_event.key_number))
        print("Encoder: {}".format(macropad.encoder))
        print("Encoder switch: {}".format(macropad.encoder_switch))
        time.sleep(0.4)

Documentation
=============

API documentation for this library can be found on `Read the Docs <https://docs.circuitpython.org/projects/macropad/en/latest/>`_.

For information on building library documentation, please check out `this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/adafruit/Adafruit_CircuitPython_MacroPad/blob/HEAD/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.
