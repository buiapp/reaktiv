import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    candidate_a = Signal(100)
    candidate_b = Signal(100)
    
    total_votes = ComputeSignal(lambda: candidate_a.get() + candidate_b.get())
    percent_a = ComputeSignal(lambda: (candidate_a.get() / total_votes.get()) * 100)
    percent_b = ComputeSignal(lambda: (candidate_b.get() / total_votes.get()) * 100)

    async def display_results():
        print(f"Total: {total_votes.get()} | A: {candidate_a.get()} ({percent_a.get():.1f}%) | B: {candidate_b.get()} ({percent_b.get():.1f}%)")

    async def check_dominance():
        if percent_a.get() > 60:
            print("Alert: Candidate A is dominating!")
        elif percent_b.get() > 60:
            print("Alert: Candidate B is dominating!")

    # Assign effects to variables to ensure they are retained
    display_effect = Effect(display_results)
    alert_effect = Effect(check_dominance)
    
    display_effect.schedule()
    alert_effect.schedule()

    for _ in range(3):
        await asyncio.sleep(1)
        candidate_a.set(candidate_a.get() + 40)
        candidate_b.set(candidate_b.get() + 10)
    
    await asyncio.sleep(1)

asyncio.run(main())