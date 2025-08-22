from agents.personal_assistant_agent import run_personal_assistant

text, meta = run_personal_assistant(
    prompt="Find the latest on GPT-5 research progress and check my next 3 calendar events.",
    memory_id="ram-memory",
    actor_id="ram",
    session_id="session-123",
    summary_namespace="personal-assistant",
    use_hooks=True,
)

print(text)
print(meta)
