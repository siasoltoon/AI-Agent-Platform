"""
Task Scheduler

Responsible for:
- Fetching tasks from queue
- Priority handling
- Duplicate protection
- Retry management
- Timeout control
- Execution history
"""


import time
import traceback
from typing import Optional, Any


class TaskScheduler:

    def __init__(
        self,
        queue,
        priority_manager=None,
        retry_manager=None,
        timeout_manager=None,
        duplicate_guard=None,
        history_manager=None,
    ):
        self.queue = queue

        self.priority_manager = priority_manager
        self.retry_manager = retry_manager
        self.timeout_manager = timeout_manager
        self.duplicate_guard = duplicate_guard
        self.history_manager = history_manager


    def run_next(self) -> Optional[Any]:
        """
        Execute next available task
        """

        task = self._get_next_task()

        if task is None:
            return None


        task_id = self._get_task_id(task)


        # Duplicate protection
        if self.duplicate_guard:

            if self.duplicate_guard.exists(task_id):
                self._record_history(
                    task,
                    "duplicate_blocked"
                )

                return {
                    "status": "blocked",
                    "reason": "duplicate_task"
                }


            self.duplicate_guard.register(task_id)



        try:

            self._record_history(
                task,
                "started"
            )


            result = self._execute_task(task)


            self._record_history(
                task,
                "completed",
                result
            )


            return {
                "status": "success",
                "task_id": task_id,
                "result": result
            }


        except Exception as error:


            self._record_history(
                task,
                "failed",
                str(error)
            )


            if self._should_retry(task):

                return self._retry_task(task)


            return {
                "status": "failed",
                "task_id": task_id,
                "error": str(error)
            }



    def _get_next_task(self):

        """
        Get highest priority task
        """

        if self.priority_manager:

            return self.priority_manager.get_next(
                self.queue
            )


        return self.queue.pop()



    def _execute_task(self, task):

        """
        Execute task handler
        """

        handler = task.get("handler")


        if not handler:

            raise Exception(
                "Task handler missing"
            )


        timeout = None


        if self.timeout_manager:

            timeout = self.timeout_manager.get_timeout(
                task
            )


        if timeout:

            return self.timeout_manager.execute(
                handler,
                timeout
            )


        return handler()



    def _should_retry(self, task):

        if not self.retry_manager:
            return False


        return self.retry_manager.can_retry(
            self._get_task_id(task)
        )



    def _retry_task(self, task):

        if self.retry_manager:

            self.retry_manager.retry(
                task
            )


        return {
            "status": "retry_scheduled",
            "task_id": self._get_task_id(task)
        }



    def _get_task_id(self, task):

        if isinstance(task, dict):

            return task.get(
                "id",
                str(id(task))
            )


        return str(id(task))



    def _record_history(
        self,
        task,
        status,
        data=None
    ):

        if self.history_manager:

            self.history_manager.add(
                {
                    "task_id": self._get_task_id(task),
                    "status": status,
                    "timestamp": time.time(),
                    "data": data
                }
            )
