# SPDX-FileCopyrightText: Copyright (c) 2021 Kattni Rembor for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_macropad`
================================================================================

A helper library for the Adafruit MacroPad RP2040.


* Author(s): Kattni Rembor

Implementation Notes
--------------------

**Hardware:**

* `Adafruit MacroPad RP2040 Bare Bones <https://www.adafruit.com/product/5100>`_
* `Adafruit MacroPad RP2040 Starter Kit <https://www.adafruit.com/product/5128>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* Adafruit's CircuitPython NeoPixel library:
  https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel

* Adafruit's CircuitPython HID library:
  https://github.com/adafruit/Adafruit_CircuitPython_HID

* Adafruit's CircuitPython MIDI library:
  https://github.com/adafruit/Adafruit_CircuitPython_MIDI

* Adafruit's CircuitPython Display Text library:
  https://github.com/adafruit/Adafruit_CircuitPython_Display_Text

* Adafruit's CircuitPython Simple Text Display library:
  https://github.com/adafruit/Adafruit_CircuitPython_Simple_Text_Display

* Adafruit's CircuitPython Debouncer library:
  https://github.com/adafruit/Adafruit_CircuitPython_Debouncer

* Adafruit's CircuitPython Ticks library
  https://github.com/adafruit/Adafruit_CircuitPython_Ticks

"""

import array
import math
import time
import board
import digitalio
import rotaryio
import keypad
import neopixel
import displayio
import audiopwmio
import audiocore
import audiomp3
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_base import KeyboardLayoutBase
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.mouse import Mouse
import usb_midi
import adafruit_midi
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from adafruit_midi.pitch_bend import PitchBend
from adafruit_midi.control_change import ControlChange
from adafruit_midi.program_change import ProgramChange
from adafruit_simple_text_display import SimpleTextDisplay
from adafruit_debouncer import Debouncer

try:
    # Only used for typing
    from typing import Tuple, Optional, Union, Iterator
    from neopixel import NeoPixel
    from keypad import Keys
    import adafruit_hid  # pylint:disable=ungrouped-imports
except ImportError:
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_MacroPad.git"

ROTATED_KEYMAP_0 = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
ROTATED_KEYMAP_90 = (2, 5, 8, 11, 1, 4, 7, 10, 0, 3, 6, 9)
ROTATED_KEYMAP_180 = (11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0)
ROTATED_KEYMAP_270 = (9, 6, 3, 0, 10, 7, 4, 1, 11, 8, 5, 2)

# See https://cdn-shop.adafruit.com/product-files/5228/5223-ds.pdf#page=13
_DISPLAY_SLEEP_COMMAND = 0xAE
_DISPLAY_WAKE_COMMAND = 0xAF

keycodes = Keycode
"""Module level Keycode class, to be changed when initing Macropad with a different language"""


class _PixelMapLite:
    """Generate a pixel map based on a specified order. Designed to work with a set of 12 pixels,
    e.g. the MacroPad keypad LEDs.

    :param pixels: The pixel object.
    :param tuple order: The specified order of the pixels. Pixels are numbered 0-11. Defaults to
                        numerical order, ``0`` to ``11``.
    """

    def __init__(
        self,
        pixels: NeoPixel,
        order: Tuple[
            int, int, int, int, int, int, int, int, int, int, int, int
        ] = ROTATED_KEYMAP_0,
    ):
        self._pixels = pixels
        self._order = order
        self._num_pixels = len(pixels)
        self.fill = pixels.fill
        self.show = pixels.show
        self.n = self._num_pixels

    def __setitem__(self, index: int, val: int) -> None:
        if isinstance(index, slice):
            for val_i, in_i in enumerate(range(*index.indices(self._num_pixels))):
                self._pixels[self._order[in_i]] = val[val_i]
        else:
            self._pixels[self._order[index]] = val

    def __getitem__(self, index: int) -> int:
        if isinstance(index, slice):
            return [
                self._pixels[self._order[idx]]
                for idx in range(*index.indices(self._num_pixels))
            ]
        if index < 0:
            index += self._num_pixels
        if index >= self._num_pixels or index < 0:
            raise IndexError
        return self._pixels[self._order[index]]

    def __repr__(self) -> str:
        return self._pixels.__repr__()

    def __len__(self) -> int:
        return len(self._pixels)

    @property
    def auto_write(self) -> bool:
        """
        True if the neopixels should immediately change when set. If False, ``show`` must be
        called explicitly.
        """
        return self._pixels.auto_write

    @auto_write.setter
    def auto_write(self, value: bool) -> None:
        self._pixels.auto_write = value

    @property
    def brightness(self) -> float:
        """Overall brightness of the pixel (0 to 1.0)."""
        return self._pixels.brightness

    @brightness.setter
    def brightness(self, value: float) -> None:
        self._pixels.brightness = value


# pylint: disable=too-many-lines, disable=invalid-name, too-many-instance-attributes, too-many-public-methods, too-many-arguments
class MacroPad:
    """
    Class representing a single MacroPad.

    :param int rotation: The rotational position of the MacroPad. Allows for rotating the MacroPad
                         in 90 degree increments to four different positions and rotates the keypad
                         layout and display orientation to match. Keypad layout is always left to
                         right, top to bottom, beginning with key number 0 in the top left, and
                         ending with key number 11 in the bottom right. Supports ``0``, ``90``,
                         ``180``, and ``270`` degree rotations. ``0`` is when the USB port is at
                         the top, ``90`` is when the USB port is to the left, ``180`` is when the
                         USB port is at the bottom, and ``270`` is when the USB port is to the
                         right. Defaults to ``0``.
    :param int or tuple midi_in_channel: The MIDI input channel. This can either be an integer for
                                         one channel, or a tuple of integers to listen on multiple
                                         channels. Defaults to 1.
    :param int midi_out_channel: The MIDI output channel. Defaults to 1.

    :param type[KeyboardLayoutBase] layout_class: Class for the keyboard layout, to setup an
                                                  international or alternative keyboard. Defaults
                                                  to KeyboardLayoutUS from adafruit_hid.
    :param type[Keycode] keycode_class: Class used for the keycode names provided by
                                        adafruit_macropad.Keycode. Defaults to the standard Keycode
                                        from adafruit_hid.


    The following shows how to initialise the MacroPad library with the board rotated 90 degrees,
    and the MIDI channels both set to 1.

    .. code-block:: python

        from adafruit_macropad import MacroPad

        macropad = MacroPad(rotation=90, midi_in_channel=1, midi_out_channel=1)
    """

    Keycode = Keycode
    """
    The contents of the Keycode module are available as a property of MacroPad. This includes all
    keycode constants available within the Keycode module, which includes all the keys on a
    regular PC or Mac keyboard.

    Remember that keycodes are the names for key _positions_ on a US keyboard, and may not
    correspond to the character that you mean to send if you want to emulate non-US keyboard.

    For usage example, see the ``keyboard`` documentation in this library.
    """

    ConsumerControlCode = ConsumerControlCode
    """
    The contents of the ConsumerControlCode module are available as a property of MacroPad.
    This includes the available USB HID Consumer Control Device constants. This list is not
    exhaustive.

    For usage example, see the ``consumer_control`` documentation in this library.
    """

    Mouse = Mouse
    """
    The contents of the Mouse module are available as a property of MacroPad. This includes the
    ``LEFT_BUTTON``, ``MIDDLE_BUTTON``, and ``RIGHT_BUTTON`` constants. The rest of the
    functionality of the ``Mouse`` module should be used through ``macropad.mouse``.

    For usage example, see the ``mouse`` documentation in this library.
    """

    def __init__(
        self,
        rotation: int = 0,
        midi_in_channel: int = 1,
        midi_out_channel: int = 1,
        layout_class: type[KeyboardLayoutBase] = KeyboardLayoutUS,
        keycode_class: type[Keycode] = Keycode,
    ):
        # Define LEDs:
        self._pixels = neopixel.NeoPixel(board.NEOPIXEL, 12)
        self._led = digitalio.DigitalInOut(board.LED)
        self._led.switch_to_output()

        # Define rotary encoder and encoder switch:
        self._encoder = rotaryio.IncrementalEncoder(board.ROTA, board.ROTB)
        self._encoder_switch = digitalio.DigitalInOut(board.BUTTON)
        self._encoder_switch.switch_to_input(pull=digitalio.Pull.UP)
        self._debounced_switch = Debouncer(self._encoder_switch)

        # Define display:
        if not isinstance(board.DISPLAY, type(None)):
            self.display = board.DISPLAY
            self.display.bus.send(_DISPLAY_WAKE_COMMAND, b"")
        self._display_sleep = False

        # Define key and pixel maps based on rotation:
        self._rotated_pixels = None
        self._key_pins = None
        self._keys = None
        self.rotate(rotation)

        # Define audio:
        self._speaker_enable = digitalio.DigitalInOut(board.SPEAKER_ENABLE)
        self._speaker_enable.switch_to_output(value=False)
        self._sample = None
        self._sine_wave = None
        self._sine_wave_sample = None

        # Define HID:
        self._keyboard = None
        self._keyboard_layout = None
        self._consumer_control = None
        self._mouse = None
        self._layout_class = layout_class
        self.Keycode = keycode_class
        # pylint:disable=global-statement
        global keycodes
        keycodes = keycode_class
        # pylint:enable=global-statement

        # Define MIDI:
        try:
            self._midi = adafruit_midi.MIDI(
                midi_in=usb_midi.ports[0],
                # MIDI uses channels 1-16. CircuitPython uses 0-15. Ergo -1.
                in_channel=midi_in_channel - 1,
                midi_out=usb_midi.ports[1],
                out_channel=midi_out_channel - 1,
            )
        except IndexError:
            # No MIDI ports available.
            self._midi = None

    def rotate(self, rotation):
        """
        Set the display rotation

        :param int rotation: The rotational position of the MacroPad. Allows for rotating the
                            MacroPad in 90 degree increments to four different positions and
                            rotates the keypad layout and display orientation to match. Keypad
                            layout is always left to right, top to bottom, beginning with key
                            number 0 in the top left, and ending with key number 11 in the bottom
                            right. Supports ``0``, ``90``, ``180``, and ``270`` degree rotations.
                            ``0`` is when the USB port is at the top, ``90`` is when the USB port
                            is to the left, ``180`` is when the USB port is at the bottom, and
                            ``270`` is when the USB port is to the right. Defaults to ``0``.
        """
        if rotation not in (0, 90, 180, 270):
            raise ValueError("Only 90 degree rotations are supported.")

        self._rotation = rotation

        def _keys_and_pixels(
            order: Tuple[int, int, int, int, int, int, int, int, int, int, int, int]
        ) -> None:
            """
            Generate key and pixel maps based on a specified order.
            :param order: Tuple containing the order of the keys and pixels.
            """
            self._key_pins = [getattr(board, "KEY%d" % (num + 1)) for num in order]
            self._rotated_pixels = _PixelMapLite(self._pixels, order=order)

        if rotation == 0:
            _keys_and_pixels(order=ROTATED_KEYMAP_0)

        if rotation == 90:
            _keys_and_pixels(order=ROTATED_KEYMAP_90)

        if rotation == 180:
            _keys_and_pixels(order=ROTATED_KEYMAP_180)

        if rotation == 270:
            _keys_and_pixels(order=ROTATED_KEYMAP_270)

        # Define keys:
        if self._keys is not None:
            self._keys.deinit()
        self._keys = keypad.Keys(self._key_pins, value_when_pressed=False, pull=True)

        self.display.rotation = rotation

    @property
    def rotation(self) -> int:
        """
        The current rotation
        """
        return self._rotation

    @rotation.setter
    def rotation(self, new_rotation) -> None:
        self.rotate(new_rotation)

    @property
    def display_sleep(self) -> bool:
        """The power saver mode of the display. Set it to put the display to
        sleep or wake it up again.

        If the display is put to sleep, it stops the OLED drive and greatly
        reduces its power usage. The display mode and current content of the
        display are still kept in the memory of the displays microprocessor and
        can be updated nevertheless.
        """
        return self._display_sleep

    @display_sleep.setter
    def display_sleep(self, sleep: bool) -> None:
        if self._display_sleep == sleep:
            return
        if sleep:
            command = _DISPLAY_SLEEP_COMMAND
        else:
            command = _DISPLAY_WAKE_COMMAND
        self.display.bus.send(command, b"")
        self._display_sleep = sleep

    @property
    def pixels(self) -> Optional[_PixelMapLite]:
        """Sequence-like object representing the twelve NeoPixel LEDs in a 3 x 4 grid on the
        MacroPad. Each pixel is at a certain index in the sequence, numbered 0-11. Colors can be an
        RGB tuple like (255, 0, 0) where (R, G, B), or an RGB hex value like 0xFF0000 for red where
        each two digits are a color (0xRRGGBB). Set the global brightness using any number from 0
        to 1 to represent a percentage, i.e. 0.3 sets global brightness to 30%. Brightness defaults
        to 1.

        See ``neopixel.NeoPixel`` for more info.

        The following example turns all the pixels green at 50% brightness.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            macropad.pixels.brightness = 0.5

            while True:
                macropad.pixels.fill((0, 255, 0))

        The following example sets the first pixel red and the twelfth pixel blue.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                macropad.pixels[0] = (255, 0, 0)
                macropad.pixels[11] = (0, 0, 255)
        """
        return self._rotated_pixels

    @property
    def red_led(self) -> bool:
        """The red led next to the USB port.

        The following example blinks the red LED every 0.5 seconds.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
              macropad.red_led = True
              time.sleep(0.5)
              macropad.red_led = False
              time.sleep(0.5)
        """
        return self._led.value

    @red_led.setter
    def red_led(self, value: bool) -> None:
        self._led.value = value

    @property
    def keys(self) -> Keys:
        """
        The keys on the MacroPad. Uses events to track key number and state, e.g. pressed or
        released. You must fetch the events using ``keys.events.get()`` and then the events are
        available for usage in your code. Each event has three properties:

        * ``key_number``: the number of the key that changed. Keys are numbered starting at 0.
        * ``pressed``: ``True`` if the event is a transition from released to pressed.
        * ``released``: ``True`` if the event is a transition from pressed to released.

        ``released`` is always the opposite of ``pressed``; it's provided for convenience
        and clarity, in case you want to test for key-release events explicitly.

        The following example prints the key press and release events to the serial console.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                key_event = macropad.keys.events.get()
                if key_event:
                    print(key_event)
        """
        return self._keys

    @property
    def encoder(self) -> int:
        """
        The rotary encoder relative rotation position. Always begins at 0 when the code is run, so
        the value returned is relative to the initial location.

        The following example prints the relative position to the serial console.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                print(macropad.encoder)
        """
        return self._encoder.position * -1

    @property
    def encoder_switch(self) -> bool:
        """
        The rotary encoder switch. Returns ``True`` when pressed.

        The following example prints the status of the rotary encoder switch to the serial console.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                print(macropad.encoder_switch)
        """
        return not self._encoder_switch.value

    @property
    def encoder_switch_debounced(self) -> Debouncer:
        """
        The rotary encoder switch debounced. Allows for ``encoder_switch_debounced.pressed`` and
        ``encoder_switch_debounced.released``. Requires you to include
        ``encoder_switch_debounced.update()`` inside your loop.

        The following example prints to the serial console when the rotary encoder switch is
        pressed and released.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                macropad.encoder_switch_debounced.update()
                if macropad.encoder_switch_debounced.pressed:
                    print("Pressed!")
                if macropad.encoder_switch_debounced.released:
                    print("Released!")
        """
        self._debounced_switch.pressed = self._debounced_switch.fell
        self._debounced_switch.released = self._debounced_switch.rose
        return self._debounced_switch

    @property
    def keyboard(self) -> adafruit_hid.keyboard.Keyboard:
        """
        A keyboard object used to send HID reports. For details, see the ``Keyboard`` documentation
        in CircuitPython HID: https://circuitpython.readthedocs.io/projects/hid/en/latest/index.html

        The following example types out the letter "a" when the rotary encoder switch is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.keyboard.send(macropad.Keycode.A)
        """
        if self._keyboard is None:
            self._keyboard = Keyboard(usb_hid.devices)
        return self._keyboard

    @property
    def keyboard_layout(self) -> adafruit_hid.keyboard_layout_base.KeyboardLayoutBase:
        """
        Map ASCII characters to the appropriate key presses on a standard US PC keyboard.
        Non-ASCII characters and most control characters will raise an exception. Required to send
        a string of characters.

        The following example sends the string ``"Hello World"`` when the rotary encoder switch is
        pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.keyboard_layout.write("Hello World")
        """
        if self._keyboard_layout is None:
            # This will need to be updated if we add more layouts. Currently there is only US.
            self._keyboard_layout = self._layout_class(self.keyboard)
        return self._keyboard_layout

    @property
    def consumer_control(self) -> adafruit_hid.consumer_control.ConsumerControl:
        """
        Send ConsumerControl code reports, used by multimedia keyboards, remote controls, etc.

        The following example decreases the volume when the rotary encoder switch is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.consumer_control.send(macropad.ConsumerControlCode.VOLUME_DECREMENT)
        """
        if self._consumer_control is None:
            self._consumer_control = ConsumerControl(usb_hid.devices)
        return self._consumer_control

    @property
    def mouse(self) -> adafruit_hid.mouse.Mouse:
        """
        Send USB HID mouse reports.

        The following example sends a left mouse button click when the rotary encoder switch is
        pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.mouse.click(macropad.Mouse.LEFT_BUTTON)
        """
        if self._mouse is None:
            self._mouse = Mouse(usb_hid.devices)
        return self._mouse

    @property
    def midi(self) -> adafruit_midi.MIDI:
        """
        The MIDI object. Used to send and receive MIDI messages. For more details, see the
        ``adafruit_midi`` documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        The following example plays a single note by MIDI number, at full velocity.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("NoteOn/NoteOff MIDI using note number")
            macropad.midi.send(macropad.NoteOn(44, 127))
            time.sleep(0.5)
            macropad.midi.send(macropad.NoteOff(44, 0))
            time.sleep(1)

        The following example reads incoming MIDI messages.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Read incoming MIDI messages")
            msg_in = macropad.midi.receive()
            if msg_in is not None:
                print("Received:", msg_in.__dict__)
        """
        return self._midi

    @staticmethod
    def NoteOn(
        note: Union[int, str], velocity: int = 127, *, channel: Optional[int] = None
    ) -> NoteOn:
        """
        Note On Change MIDI message. For more details, see the ``adafruit_midi.note_on``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param note: The note (key) number either as an int (0-127) or a str which is parsed, e.g.
                     “C4” (middle C) is 60, “A4” is 69.
        :param velocity: The strike velocity, 0-127, 0 is equivalent to a Note Off, defaults to
                         127.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        The following example plays a single note by MIDI number, at full velocity.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("NoteOn/NoteOff MIDI using note number")
            macropad.midi.send(macropad.NoteOn(44, 127))
            time.sleep(0.5)
            macropad.midi.send(macropad.NoteOff(44, 0))
            time.sleep(1)

        The following example plays a chord.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Multiple notes on/off in one message")
            macropad.midi.send([macropad.NoteOn(44, 127),
                                macropad.NoteOn(48, 127),
                                macropad.NoteOn(51, 127)])
            time.sleep(1)
            macropad.midi.send([macropad.NoteOff(44, 0),
                                macropad.NoteOff(48, 0),
                                macropad.NoteOff(51, 0)])
            time.sleep(1)
        """
        return NoteOn(note=note, velocity=velocity, channel=channel)

    @staticmethod
    def NoteOff(
        note: Union[int, str], velocity: int = 127, *, channel: Optional[int] = None
    ) -> NoteOff:
        """
        Note Off Change MIDI message. For more details, see the ``adafruit_midi.note_off``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param note: The note (key) number either as an int (0-127) or a str which is parsed, e.g.
                     “C4” (middle C) is 60, “A4” is 69.
        :param velocity: The release velocity, 0-127, defaults to 0.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        The following example plays a single note by MIDI number, at half velocity.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("NoteOn/NoteOff using note name")
            macropad.midi.send(macropad.NoteOn("G#2", 64))
            time.sleep(0.5)
            macropad.midi.send(macropad.NoteOff("G#2", 0))
            time.sleep(1)
        """
        return NoteOff(note=note, velocity=velocity, channel=channel)

    @staticmethod
    def PitchBend(pitch_bend: int, *, channel: Optional[int] = None) -> PitchBend:
        """
        Pitch Bend Change MIDI message. For more details, see the ``adafruit_midi.pitch_bend``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param pitch_bend: A 14bit unsigned int representing the degree of bend from 0 through 8192
                           (midpoint, no bend) to 16383.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        The following example sets a pitch bend.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Set pitch bend")
            macropad.midi.send(macropad.PitchBend(4096))

        The following example sweeps a pitch bend.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Sweep pitch bend")
            for i in range(0, 4096, 8):
                macropad.midi.send(macropad.PitchBend(i))
            for i in range(0, 4096, 8):
                macropad.midi.send(macropad.PitchBend(4096-i))
        """
        return PitchBend(pitch_bend=pitch_bend, channel=channel)

    @staticmethod
    def ControlChange(
        control: int, value: int, *, channel: Optional[int] = None
    ) -> ControlChange:
        """
        Control Change MIDI message. For more details, see the ``adafruit_midi.control_change``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param control: The control number, 0-127.
        :param value: The 7bit value of the control, 0-127.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        The following example sets a control change value.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Set a CC value")
            macropad.midi.send(macropad.ControlChange(7, 64))

        The following example sweeps a control change value.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Sweep a CC value")
            for i in range(127):
                macropad.midi.send(macropad.ControlChange(1, i))
                time.sleep(0.01)
            for i in range(127):
                macropad.midi.send(macropad.ControlChange(1, 127-i))
                time.sleep(0.01)
        """
        return ControlChange(control=control, value=value, channel=channel)

    @staticmethod
    def ProgramChange(patch: int, *, channel: Optional[int] = None) -> ProgramChange:
        """
        Program Change MIDI message. For more details, see the ``adafruit_midi.program_change``
        documentation in CircuitPython MIDI:
        https://circuitpython.readthedocs.io/projects/midi/en/latest/

        :param patch: The note (key) number either as an int (0-127) or a str which is parsed,
                      e.g. “C4” (middle C) is 60, “A4” is 69.
        :param channel: The channel number of the MIDI message where appropriate. This is updated
                        by MIDI.send() method.

        The following example sends a program change for bank switching.

        .. code-block:: python

            import time
            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            print("Send ProgramChange bank messages")
            macropad.midi.send(macropad.ProgramChange(63))
            time.sleep(2)
            macropad.midi.send(macropad.ProgramChange(8))
            time.sleep(2)
        """
        return ProgramChange(patch=patch, channel=channel)

    def display_image(
        self,
        file_name: Optional[str] = None,
        position: Optional[Tuple[int, int]] = None,
    ) -> None:
        """
        Display an image on the built-in display.

        :param str file_name: The path to a compatible bitmap image, e.g. ``"/image.bmp"``. Must be
                              a string.
        :param tuple position: Optional ``(x, y)`` coordinates to place the image.

        The following example displays an image called "image.bmp" located in / on the CIRCUITPY
        drive on the display.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            macropad.display_image("image.bmp")

            while True:
                pass
        """
        if not file_name:
            return
        if not position:
            position = (0, 0)
        group = displayio.Group(scale=1)
        self.display.root_group = group
        with open(file_name, "rb") as image_file:
            background = displayio.OnDiskBitmap(image_file)
            sprite = displayio.TileGrid(
                background,
                pixel_shader=background.pixel_shader,
                x=position[0],
                y=position[1],
            )
            group.append(sprite)
            self.display.refresh()

    @staticmethod
    def display_text(
        title: Optional[str] = None,
        title_scale: int = 1,
        title_length: int = 80,
        text_scale: int = 1,
        font: Optional[str] = None,
    ) -> SimpleTextDisplay:
        """
        Display lines of text on the built-in display. Note that if you instantiate this without
        a title, it will display the first (``[0]``) line of text at the top of the display - use
        this feature to have a dynamic "title".

        :param str title: The title displayed above the data. Set ``title="Title text"`` to provide
                          a title. Defaults to None.
        :param int title_scale: Scale the size of the title. Not necessary if no title is provided.
                                Defaults to 1.
        :param int title_length: The maximum number of characters allowed in the title. Only
                                 necessary if the title is longer than the default 80 characters.
                                 Defaults to 80.
        :param int text_scale: Scale the size of the data lines. Scales the title as well.
                               Defaults to 1.
        :param ~FontProtocol|None font: The custom font to use to display the text. Defaults to the
                                        built-in ``terminalio.FONT``. For more details, see:
                                        https://docs.circuitpython.org/en/latest/shared-bindings/fontio/index.html

        The following example displays a title and lines of text indicating which key is pressed,
        the relative position of the rotary encoder, and whether the encoder switch is pressed.
        Note that the key press line does not show up until a key is pressed.

        .. code-block:: python

            from adafruit_bitmap_font import bitmap_font
            from adafruit_macropad import MacroPad
            from displayio import Bitmap

            macropad = MacroPad()

            custom_font = bitmap_font.load_font("/Arial12.bdf", Bitmap)
            text_lines = macropad.display_text(title="MacroPad Info", font=custom_font)

            while True:
                key_event = macropad.keys.events.get()
                if key_event:
                    text_lines[0].text = "Key {} pressed!".format(key_event.key_number)
                text_lines[1].text = "Rotary encoder {}".format(macropad.encoder)
                text_lines[2].text = "Encoder switch: {}".format(macropad.encoder_switch)
                text_lines.show()
        """
        return SimpleTextDisplay(
            title=title,
            title_color=SimpleTextDisplay.WHITE,
            title_scale=title_scale,
            title_length=title_length,
            text_scale=text_scale,
            font=font,
            colors=(SimpleTextDisplay.WHITE,),
            display=board.DISPLAY,
        )

    @staticmethod
    def _sine_sample(length: int) -> Iterator[int]:
        tone_volume = (2**15) - 1
        shift = 2**15
        for i in range(length):
            yield int(tone_volume * math.sin(2 * math.pi * (i / length)) + shift)

    def _generate_sample(self, length: int = 100) -> None:
        if self._sample is not None:
            return
        self._sine_wave = array.array("H", self._sine_sample(length))
        self._sample = audiopwmio.PWMAudioOut(board.SPEAKER)
        self._sine_wave_sample = audiocore.RawSample(self._sine_wave)

    def play_tone(self, frequency: int, duration: float) -> None:
        """Produce a tone using the speaker at a specified hz for a specified duration in seconds.

        :param int frequency: The frequency of the tone in Hz
        :param float duration: The duration of the tone in seconds

        The following example plays a 292hz tone for 1 second when the rotary encoder switch is
        pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.play_tone(292, 1)
        """
        self.start_tone(frequency)
        time.sleep(duration)
        self.stop_tone()

    def start_tone(self, frequency: int) -> None:
        """Produce a tone using the speaker. Will continue playing until ``stop_tone`` is called.

        :param int frequency: The frequency of the tone in Hz

        The following example plays 292hz a tone while the rotary encoder switch is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.start_tone(292)
                else:
                    macropad.stop_tone()
        """
        self._speaker_enable.value = True
        length = 100
        if length * frequency > 350000:
            length = 350000 // frequency
        self._generate_sample(length)
        # Start playing a tone of the specified frequency (hz).
        self._sine_wave_sample.sample_rate = int(len(self._sine_wave) * frequency)
        if not self._sample.playing:
            self._sample.play(self._sine_wave_sample, loop=True)

    def stop_tone(self) -> None:
        """Use with ``start_tone`` to stop the tone produced. See usage example in ``start_tone``
        documentation."""
        # Stop playing any tones.
        if self._sample is not None and self._sample.playing:
            self._sample.stop()
            self._sample.deinit()
            self._sample = None
        self._speaker_enable.value = False

    def play_file(self, file_name: str) -> None:
        """Play a .wav or .mp3 file using the onboard speaker.

        :param file_name: The name of your .wav or .mp3 file in quotation marks including
                          .wav or .mp3, e.g. "sound.wav" or "sound.mp3". Include location if file
                          is placed somewhere other than /, e.g. "audio/sound.wav".

        The following example plays the file "sound.wav" when the rotary encoder switch is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.play_file("sound.wav")

        The following example plays the file "sound.mp3" when the rotary encoder switch is pressed.

        .. code-block:: python

            from adafruit_macropad import MacroPad

            macropad = MacroPad()

            while True:
                if macropad.encoder_switch:
                    macropad.play_file("sound.mp3")
        """
        self.stop_tone()
        self._speaker_enable.value = True
        if file_name.lower().endswith(".wav"):
            with audiopwmio.PWMAudioOut(board.SPEAKER) as audio, open(
                file_name, "rb"
            ) as audio_file:  # pylint: disable=not-callable
                wavefile = audiocore.WaveFile(audio_file)
                audio.play(wavefile)
                while audio.playing:
                    pass
        elif file_name.lower().endswith(".mp3"):
            with audiopwmio.PWMAudioOut(board.SPEAKER) as audio, open(
                file_name, "rb"
            ) as audio_file:  # pylint: disable=not-callable
                mp3file = audiomp3.MP3Decoder(audio_file)
                audio.play(mp3file)
                while audio.playing:
                    pass
        else:
            raise ValueError("Filetype must be wav or MP3.")
        self._speaker_enable.value = False
