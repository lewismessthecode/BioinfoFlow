# Vulture whitelist — structural patterns that vulture incorrectly flags.
# Run: uv run vulture app/ tests/ vulture_whitelist.py --min-confidence 80
#
# Remaining known false positives (cannot be suppressed via whitelist):
#
#   tests/test_scheduler/test_recovery.py:22
#     `if False: yield None` — required to make NoopBackend.submit an async
#     generator without yielding a value. Python needs the `yield` statement
#     in the function body to classify it as a generator function.
#
#   tests/test_scheduler/test_scheduler.py:307
#   tests/test_services/test_image_service.py:127
#     `yield` after `raise` — same reason as above: the yield is syntactically
#     required to make the method an async generator even though it is
#     unreachable at runtime.
