from reaktiv import signal, computed, effect, batch
from time import sleep


candidate_a = signal(100)
candidate_b = signal(100)


@computed
def total_votes():
    return candidate_a() + candidate_b()


@computed
def percent_a():
    return (candidate_a() / total_votes()) * 100


@computed
def percent_b():
    return (candidate_b() / total_votes()) * 100


def display_results():
    print(f"Candidate A: {candidate_a()} votes ({percent_a():.1f}%)")
    print(f"Candidate B: {candidate_b()} votes ({percent_b():.1f}%)")
    print(f"Total: {total_votes()} votes\n")


def check_dominance():
    if percent_a() >= 60:
        print("📊 ALERT: Candidate A has a significant lead!\n")
    elif percent_b() >= 60:
        print("📊 ALERT: Candidate B has a significant lead!\n")


# Assign effects to variables to ensure they are retained
_display_effect = effect(display_results)
_alert_effect = effect(check_dominance)

for _ in range(3):
    sleep(1)
    with batch():
        candidate_a.update(lambda x: x + 40)
        candidate_b.update(lambda x: x + 10)
