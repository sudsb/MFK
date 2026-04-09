UPGRADE GUIDE — MessageBus framework (v2.0)

This document describes breaking changes and migration steps for projects upgrading to the new MessageBus framework version. It focuses on the most important runtime and compatibility items: process delivery requirements (handler_info), pickling constraints for process delivery, channel compatibility (HighSpeedChannel vs NormalChannel), and automated checks you can add to validate your codebase before deployment.

1. Summary of breaking changes
   - MessageBus now supports three delivery backends: "thread" (default), "process", and "asyncio".
   - Process delivery re-instantiates subscribed handlers inside child processes. To use process delivery safely and deterministically you MUST provide handler_info when subscribing.
   - HighSpeedChannel (mmap ring buffer) is same-process only and MUST NOT be used for cross-process delivery.
   - All message payloads and any values required to re-instantiate handlers in process mode must be picklable.

2. handler_info: why it exists and required shape
   - Reason: In process mode, the framework cannot serialize live bound methods or closures. Instead it re-imports and constructs a fresh instance of the component inside the child process and calls the specified method. handler_info provides the metadata needed to perform that re-instantiation.

   Required keys in handler_info:
   - module: Python import path to the component's module (e.g. "features.file_reader").
   - class_name: The component class name (e.g. "FileReader").
   - method_name: The instance method to call for handling messages (e.g. "handle_message").
   - params: dict of kwargs passed to the component constructor when re-instantiated in the child process. All values must be picklable.

   Example — subscribing a class instance method (thread-safe and process-safe):

   bus.subscribe(
       topic="file.lines",
       handler=my_reader.handle_message,
       handler_info={
           "module": "features.file_reader",
           "class_name": "FileReader",
           "method_name": "handle_message",
           "params": {"path": "data/input.txt", "encoding": "utf-8"}
       }
   )

   Example — subscribing a plain function from a module (process mode will call function directly):

   bus.subscribe(
       topic="metrics",
       handler=metrics.process_metric,
       handler_info={
           "module": "features.metrics",
           "class_name": null,
           "method_name": "process_metric",
           "params": {}
       }
   )

   Notes:
   - If you pass None for class_name the loader will import the module and look for a top-level function named method_name. Use this for module-level functions.
   - params must be a plain dict of picklable values. Avoid open file objects, sockets, lambda, bound method references, or objects from C extensions that are not picklable.

3. Pickling requirements and common pitfalls
   - Anything sent in publish() payloads or included in handler_info.params must be picklable when delivery_mode="process".
   - Builtins and simple containers are picklable: numbers, strings, bytes, tuples, lists, dicts, sets (with picklable elements).
   - Custom class instances are picklable only if their classes are importable by module path and reconstructable using their module-level definition and state. Prefer using dataclasses or simple dicts for cross-process safety.
   - Avoid:
     - Lambda functions or nested function objects
     - Open file handles, sockets, threads, asyncio event loop objects
     - Local classes defined inside functions
     - Objects from extension modules without pickle support

   - Debugging tip: Use the standard library pickle module to verify picklability locally:

     python - <<'PY'
     import pickle
     from features.file_reader import FileReader

     obj = {"params": {"path": "data/input.txt"}}
     pickle.dumps(obj)  # raises if not picklable
     print("ok")
     PY

4. Channel compatibility
   - NormalChannel: uses queue.Queue or multiprocessing.Queue under the hood and is cross-process safe. Use this for process delivery.
   - HighSpeedChannel: uses mmap ring buffers for low latency but is NOT cross-process safe. It is limited to same-process operation (thread and asyncio modes). When using delivery_mode="process" ensure channels are NormalChannel.

5. Automated checks you can add to CI
   - 5.1 Lint for handler_info usage
     - Add a small script that searches the codebase for subscribe( and ensures handler_info is present on subscribe calls that are not obviously using module-level functions. This is a fast heuristic to catch missing handler_info for new code.

     Example check (grep + python validator):

     - Use ruff or grep to find "subscribe(" occurrences and run a short AST-based check to ensure handler_info kwarg is present.

   - 5.2 Pickle validation test
     - Create a unit test that iterates over all handler_info entries defined in your runtime config (config.json) and attempts to pickle the params and a sample publish payload.

     tests/test_pickling.py (example):

     import json
     import pickle
     from pathlib import Path

     def test_picklable_handler_info():
         cfg = json.loads(Path("config.json").read_text())
         handlers = cfg.get("components", [])
         for h in handlers:
             params = h.get("params", {})
             pickle.dumps(params)  # will raise if not picklable

   - 5.3 Channel selection validation
     - Add a test to ensure that when delivery_mode is "process" the configured channel is not HighSpeedChannel.

     Example (pytest):

     def test_channel_for_process_delivery():
         cfg = json.loads(Path("config.json").read_text())
         if cfg.get("delivery_mode") == "process":
             assert cfg.get("channel", "normal") != "highspeed", "HighSpeedChannel cannot be used with process delivery"

   - 5.4 End-to-end dry run in CI
     - Add a short smoke test that starts the MessageBus in thread mode and process mode with a minimal pipeline (one producer, one consumer) using picklable payloads to verify there are no runtime errors.

6. Migration checklist
   - [ ] Audit all bus.subscribe calls; add handler_info where missing and ensure params are picklable.
   - [ ] Replace HighSpeedChannel with NormalChannel for any configuration expecting delivery_mode="process".
   - [ ] Add picklability unit tests to CI (see tests/test_pickling.py example).
   - [ ] Add channel validation test to CI.
   - [ ] Run the smoke tests in CI for thread/process/asyncio delivery backends.

7. Examples and patterns (best practices)
   - Prefer module-level functions for pure-message handlers when possible; they are easiest to call from process delivery.
   - For class-based components: keep __init__ parameters simple (primitive types, path strings, small config dicts) and move non-picklable resources (open files, sockets, threads) to on_start() so they are created in-process.

   Example pattern:

   class FileReader(BaseComponent):
       def __init__(self, path: str, encoding: str = "utf-8"):
           super().__init__(name="file_reader")
           self.path = path
           self.encoding = encoding
           self._file = None  # created in on_start(), not pickled

       def on_start(self):
           self._file = open(self.path, "r", encoding=self.encoding)

       def handle_message(self, message):
           for line in self._file:
               self._bus.publish("file.lines", line)

8. Troubleshooting
   - Error: "Can't pickle <function ...>"
     - Cause: a non-picklable object was included in handler_info.params or payload. Use the pickle.dumps() quick check to find the culprit.
   - Error: "HighSpeedChannel used in process delivery"
     - Cause: channel misconfiguration. Switch to NormalChannel for cross-process usage.

9. Further reading
   - docs/process_delivery.md — deeper implementation details and examples
   - USAGE.md — component API and lifecycle notes

If you want, I can also add the pickling unit test files (tests/test_pickling.py) and the CI job snippet. This file contains only guidance and examples; follow your project conventions when copying the snippets into tests and CI.
