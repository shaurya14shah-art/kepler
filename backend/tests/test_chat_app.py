"""The full-screen chat app, driven headlessly: questions, follow-ups, teaching, the side panel."""
import asyncio

from kepler.bot import store
from kepler.bot.chat_app import ChatApp


def _log_text(app) -> str:
    log = app.query_one("#ai-log")
    return "\n".join(line.text for line in log.lines)


async def _ask(app, pilot, text: str) -> None:
    inp = app.query_one("#ai-input")
    inp.value = text
    await pilot.press("enter")
    for _ in range(200):  # wait for the worker thread to answer
        await pilot.pause(0.05)
        if not app.busy:
            break


def test_chat_app_answers_follows_up_and_learns():
    async def run():
        app = ChatApp()
        async with app.run_test(size=(140, 45)) as pilot:
            await _ask(app, pilot, "wats the sum of 1st 10 natural numbers")
            await _ask(app, pilot, "and for 20?")
            await _ask(app, pilot, "what is a median")
            await _ask(app, pilot, "gimme the vibe check")
            await _ask(app, pilot, "/n status")
            text = _log_text(app)
            assert "55" in text and "210" in text            # answer, then the follow-up with 20
            assert "read as" in text                         # it showed how it read the slang
            assert "middle value" in text                    # knowledge base
            assert "learned" in text                         # the lesson
            assert store.taught_intent("gimme the vibe check") == "status"
            side = str(app.query_one("#ai-training").render())
            assert "1" in side and "examples" in side
            # clicking a suggestion asks it
            from kepler.bot.chat_app import TRIES
            app.query_one("#ai-tries").index = TRIES.index("sum of first n natural numbers")
            app.query_one("#ai-tries").focus()
            await pilot.press("enter")
            for _ in range(200):
                await pilot.pause(0.05)
                if not app.busy:
                    break
            assert "n·(n + 1)/2" in _log_text(app)
    asyncio.run(run())


def test_kepler_opens_the_ai_alone_when_the_server_is_off(monkeypatch):
    from kepler.bot import chat_app
    from kepler.cli import commands
    opened = {}
    monkeypatch.setattr(chat_app, "run", lambda bot=None, note="": opened.update(bot=bot, note=note) or 0)
    assert commands.main(["--url", "http://127.0.0.1:9", "ui"]) == 0
    assert opened["bot"] is None and "kepler serve" in opened["note"]


def test_main_ui_has_the_kepler_ai_tab():
    from kepler.tui import app as tui
    assert "ai" in tui.TABS
    src = open(tui.__file__).read()
    assert 'TabPane("7 Kepler AI", id="ai")' in src and "ChatPanel(self.app.bot" in src
