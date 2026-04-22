from app.runtime.task_runner import TaskRunner


background_tasks = TaskRunner(max_concurrency=2)
