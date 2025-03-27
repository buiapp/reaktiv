import asyncio
from reaktiv import signal, computed, effect

async def main():
    candidate_a = signal(100)
    candidate_b = signal(100)
    
    total_votes = computed(lambda: candidate_a() + candidate_b())
    percent_a = computed(lambda: (candidate_a() / total_votes()) * 100)
    percent_b = computed(lambda: (candidate_b() / total_votes()) * 100)
    
    async def display_results():
        print(f"Total: {total_votes()} | A: {candidate_a()} ({percent_a():.1f}%) | B: {candidate_b()} ({percent_b():.1f}%)")
    
    async def check_dominance():
        if percent_a() > 60:
            print("Alert: Candidate A is dominating!")
        elif percent_b() > 60:
            print("Alert: Candidate B is dominating!")
    
    # Assign effects to variables to ensure they are retained
    display_effect = effect(display_results)
    alert_effect = effect(check_dominance)
    
    for _ in range(3):
        await asyncio.sleep(1)
        candidate_a.update(lambda x: x + 40)
        candidate_b.update(lambda x: x + 10)
    
    await asyncio.sleep(1)

asyncio.run(main())