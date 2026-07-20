"""TaskState 단위 테스트"""

from src.agent.memory.task_state import TaskState, TaskStatus


def make_task():
    return TaskState(
        task_id="t1",
        user_request="fix bug",
        workspace_path="/tmp/ws",
    )


def test_initial_status_is_pending():
    task = make_task()
    assert task.status == TaskStatus.PENDING
    assert task.started_at is None


def test_start_sets_running():
    task = make_task()
    task.start()
    assert task.status == TaskStatus.RUNNING
    assert task.started_at is not None


def test_complete_sets_result():
    task = make_task()
    task.start()
    task.complete({"message": "done"})
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"message": "done"}
    assert task.get_duration() is not None


def test_fail_sets_error():
    task = make_task()
    task.start()
    task.fail("boom")
    assert task.status == TaskStatus.FAILED
    assert task.error == "boom"


def test_to_dict_roundtrip():
    task = make_task()
    task.start()
    task.add_iteration(1, "thinking", [{"tool": "finish"}], [{"success": True}])
    task.complete({})

    d = task.to_dict()
    assert d["task_id"] == "t1"
    assert d["status"] == "completed"
    assert len(d["iterations"]) == 1
    assert d["duration_seconds"] >= 0
