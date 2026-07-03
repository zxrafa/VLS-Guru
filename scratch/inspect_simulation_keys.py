import re

content = open("simulation.py", encoding="utf-8").read()

# Find all occurrences of .get('...') or player['...'] or similar
gets = set(re.findall(r"\.get\(\s*['\"]([a-zA-Z0-9_]+)['\"]", content))
dicts = set(re.findall(r"\[\s*['\"]([a-zA-Z0-9_]+)['\"]\s*\]", content))

print("Simulation keys accessed via .get():")
print(sorted(gets))

print("\nSimulation keys accessed via dictionary lookup [key]:")
print(sorted(dicts))
