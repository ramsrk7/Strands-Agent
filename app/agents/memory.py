from strands import tool, Agent
from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider
import time
from bedrock_agentcore.memory import MemoryClient

client = MemoryClient(region_name="us-west-2")
# memory = client.create_memory_and_wait(
#     name="MyAgentMemory",
#     strategies=[{
#         "userPreferenceMemoryStrategy": {
#             "name": "UserPreference",
#             "namespaces": ["/users/{actorId}"]
#         }
#     }]
# )

strands_provider = AgentCoreMemoryToolProvider(
    memory_id=memory.get("id"),
    actor_id="CaliforniaPerson",
    session_id="TalkingAboutFood",
    namespace="/users/CaliforniaPerson",
    region="us-west-2"
)
agent = Agent(tools=strands_provider.tools)

agent("Im vegetarian and I prefer restaurants with a quiet atmosphere.")
agent("Im in the mood for Italian cuisine.")
agent("Id prefer something mid-range and located downtown.")
agent("I live in Irvine.")

time.sleep(60)

# This will use the long-term memory tool
agent("I dont remember what I was in a mood for, do you remember?")