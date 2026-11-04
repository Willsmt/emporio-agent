from emporio.agent.providers.rate_limit import RateLimitedProvider
from emporio.agent.types import ModelTurn


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 2))
        self.now += seconds


class Inner:
    name = "inner"

    def generate(self, system_prompt, history, tools):
        return ModelTurn(text="ok", tool_calls=[])

    def user_message(self, text):
        return {"text": text}


def test_waits_only_what_is_left_of_the_interval():
    clock = FakeClock()
    provider = RateLimitedProvider(Inner(), min_interval_seconds=13, clock=clock.time, sleep=clock.sleep)
    provider.generate("p", [], [])   # first call: no wait
    clock.now += 5                    # 5s of tool work
    provider.generate("p", [], [])   # waits the remaining 8s
    clock.now += 20
    provider.generate("p", [], [])   # interval already passed: no wait
    assert clock.sleeps == [8.0]


def test_delegates_everything_else():
    provider = RateLimitedProvider(Inner(), min_interval_seconds=13)
    assert provider.name == "inner"
    assert provider.user_message("oi") == {"text": "oi"}
