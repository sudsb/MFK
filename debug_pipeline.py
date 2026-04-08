from framework.config_loader import load_pipeline_from_config

l = load_pipeline_from_config("config.json")
for c in l["pipeline"]:
    print(c.__class__.__name__, getattr(c, "params", None))
print("Execution:", l.get("execution"))
