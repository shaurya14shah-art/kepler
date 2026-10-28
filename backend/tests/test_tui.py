"""The full-screen app's screens. No server needed: refresh errors only show as notifications."""
import asyncio

from kepler.cli.client import Client
from kepler.tui.app import HelpScreen, KeplerApp


def _run(test):
    async def go():
        app = KeplerApp(Client("http://127.0.0.1:9"), skip_welcome=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            await test(app, pilot)
    asyncio.run(go())


def test_closing_a_modal_twice_keeps_the_main_screen():
    """Textual's dismiss() pops whatever is on top, so a second Esc while a modal was closing used to pop the main
    screen too: the app went blank and the clock crashed on '#topbar' (found by the stress test's key-mashing)."""
    async def test(app, pilot):
        app.push_screen(HelpScreen())
        await pilot.pause(0.1)
        help_screen = app.screen
        assert isinstance(help_screen, HelpScreen)
        help_screen.dismiss()
        help_screen.dismiss()
        await pilot.pause(0.1)
        assert app.screen is app.main
        app._tick()  # the 1-second clock still finds the top bar
        await pilot.press("question_mark")
        await pilot.press("escape", "escape", "question_mark", "escape")
        await pilot.pause(0.2)
        assert app.screen is app.main
        app._tick()
    _run(test)
