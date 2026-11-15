from reaktiv import Signal, computed, batch


def test_known_changed_dependency_skips_refresh_of_retired_implementation():
    calls = []
    source = Signal(1)

    @computed
    def old():
        calls.append('old')
        return source() * 2

    implementation = Signal(old)
    slot = computed(lambda: implementation()())
    assert slot() == 2
    with batch():
        source.set(2)
        implementation.set(computed(lambda: 7))
    assert slot() == 7
    assert calls == ['old']
