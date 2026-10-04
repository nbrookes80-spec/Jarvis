import os

from plugin import LINUX, MACOS, WINDOWS, plugin, require


@require(platform=WINDOWS)
@plugin('screencapture')
def Screencapture_Windows(jarvis, s):
    """
    By holding Windows + Alt + R key we start screen capture in
    """
    # Imported here: pyautogui connects to the display on import, which
    # kept this plugin from loading at all without a desktop session.
    import pyautogui as pg

    def engine():
        pg.keyDown("win")
        pg.keyDown("alt")
        pg.press("r")
        pg.keyUp("alt")
        pg.keyUp("win")

    jarvis.say('Screen Recording Started')
    engine()
    n = input("Press Q to stop : ")
    if n == 'Q':
        engine()
        jarvis.say('Screen Recording Ended')


@require(platform=LINUX)
@plugin('screencapture')
def Scrrencapture_LINUX(jarvis, s):
    """
    By holding Ctrl + Alt + Shift + R key we start screen capture in
    """
    # Imported here: pyautogui connects to the display on import, which
    # kept this plugin from loading at all without a desktop session.
    import pyautogui as pg

    def engine():
        pg.keyDown("ctrl")
        pg.keyDown("alt")
        pg.keyDown("shift")
        pg.press("r")
        pg.keyDown("shift")
        pg.keyUp("alt")
        pg.keyUp("ctrl")

    jarvis.say('Screen Recording Started')
    engine()
    n = input("Press Q to stop : ")
    if n == 'Q':
        engine()
        jarvis.say('Screen Recording Ended')


@require(platform=MACOS)
@plugin('screencapture')
def Scrrencapture_MACOS(jarvis, s):
    """
    By holding Ctrl + Alt + Shift + R key we start screen capture in
    """
    # Imported here: pyautogui connects to the display on import, which
    # kept this plugin from loading at all without a desktop session.
    import pyautogui as pg

    def engine():
        pg.keyDown("command")
        pg.keyDown("shift")
        pg.press("5")
        pg.keyDown("shift")
        pg.keyUp("command")

    jarvis.say('Screen Recording Started')
    engine()
    n = input("Press Q to stop : ")
    if n == 'Q':
        engine()
        jarvis.say('Screen Recording Ended')
