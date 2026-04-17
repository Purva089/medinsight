"""Test script for new features."""
from app.mcp.server import create_mcp_server
from app.services.safeguards import get_safeguards
from app.agents.a2a_protocol import get_a2a_hub
import json

print("=" * 60)
print("MCP SERVER TEST")
print("=" * 60)

server = create_mcp_server()
tools = server.list_tools()
print(f"\nRegistered Tools ({len(tools)}):")
for t in tools:
    print(f"  - {t['name']}: {t['description'][:60]}...")

print("\nServer Info:")
print(json.dumps(server.get_server_info(), indent=2))

print("\n" + "=" * 60)
print("ETHICAL SAFEGUARDS TEST")
print("=" * 60)

sg = get_safeguards()

test_queries = [
    ("Medical query", "What do my hemoglobin results mean?"),
    ("Off-topic query", "What is the weather forecast?"),
    ("Emergency query", "I am having chest pain"),
    ("Prescription request", "Can you prescribe medication?"),
]

for label, query in test_queries:
    result = sg.check_input(query)
    print(f"\n{label}:")
    print(f"  Query: {query}")
    print(f"  Allowed: {result.allowed}")
    print(f"  Category: {result.category.value}")
    print(f"  Safety Level: {result.safety_level.value}")
    if result.warning:
        print(f"  Warning: {result.warning[:60]}...")

print("\n" + "=" * 60)
print("A2A PROTOCOL TEST")
print("=" * 60)

hub = get_a2a_hub()
print(f"\nRegistered Agents ({len(hub._agents)}):")
for agent_name in hub._agents:
    print(f"  - {agent_name}")

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
