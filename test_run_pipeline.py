from framework.config_loader import load_pipeline_from_config
from framework.orchestrator import run_pipeline
import logging

logging.basicConfig(level=logging.DEBUG)

l = load_pipeline_from_config("config.json")
pipeline = l["pipeline"]
execution = l.get("execution")
ctx = {"root": "D:/code-project/python/content"}
print("Before ctx", ctx)
import inspect

print("run_pipeline function:", run_pipeline, "module:", run_pipeline.__module__)
print("run_pipeline file:", inspect.getsourcefile(run_pipeline))
run_pipeline(pipeline, ctx, execution)
print("After ctx", ctx)
