Process-mode delivery (handler reconstruction)
===========================================

Overview
--------

The framework supports three delivery modes for message handlers: thread, process, and asyncio. When you choose delivery_mode="process", handlers execute inside child processes created by multiprocessing.Pool. To enable this safely, the framework needs a way to re-instantiate the target component inside the child process — this is done via handler_info supplied when subscribing.

handler_info format
-------------------

When subscribing in process mode, pass handler_info with the following shape:

{
  "module": "<module.path>",
  "class_name": "<ClassName>",
  "method_name": "<method_to_call>",
  "params": { ... constructor kwargs ... }
}

Example
-------

See examples/process_subscribe_example.py for a runnable demonstration. Key points:

- Ensure the module in "module" is importable by the child process. Run the script via `python -m examples.process_subscribe_example` or put your component classes in a package (e.g. features.my_worker) so they can be imported by name.
- The message payload must be picklable. Avoid lambdas, open file handles, thread locks, and other non-picklable objects.
- HighSpeedChannel (mmap) is not cross-process safe. Use NormalChannel (queue-backed) for cross-process channels.

Why this design
----------------

Re-instantiating handlers in child processes provides isolation and allows CPU-bound handlers to run safely without blocking the main process. The trade-offs are serialization overhead (pickling) and the requirement to supply deterministic constructor parameters.

Troubleshooting
---------------

- If you see a warning like "Process delivery requires handler_info on subscribe; falling back to thread delivery", verify you passed handler_info to subscribe.
- If child process fails to import the module, check PYTHONPATH and prefer putting reusable components in a proper package (features/...).
