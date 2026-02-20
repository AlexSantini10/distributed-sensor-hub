# tests/state/test_lww.py
from queue import Queue
from state.node_state_worker import NodeStateWorker


class DummyLog:
	def info(self, *args, **kwargs):
		pass

	def error(self, *args, **kwargs):
		pass


def make_worker(node_id="A"):
	q = Queue()
	return NodeStateWorker(node_id=node_id, event_queue=q, log=DummyLog())


def test_new_insert():
	w = make_worker()

	applied = w.merge_update("s1", 10, 1000, "A")
	assert applied is True

	state = w.get_state_snapshot()["A"]
	assert state["A:s1"]["value"] == 10
	assert state["A:s1"]["ts_ms"] == 1000
	assert state["A:s1"]["origin"] == "A"


def test_newer_timestamp_wins():
	w = make_worker()

	w.merge_update("s1", 10, 1000, "A")
	applied = w.merge_update("s1", 20, 2000, "A")

	assert applied is True
	state = w.get_state_snapshot()["A"]
	assert state["A:s1"]["value"] == 20


def test_stale_timestamp_ignored():
	w = make_worker()

	w.merge_update("s1", 10, 2000, "A")
	applied = w.merge_update("s1", 5, 1000, "A")

	assert applied is False
	state = w.get_state_snapshot()["A"]
	assert state["A:s1"]["value"] == 10


def test_tie_break_origin():
	w = make_worker()

	w.merge_update("s1", 10, 1000, "A")
	applied = w.merge_update("s1", 20, 1000, "B")

	assert applied is True
	state = w.get_state_snapshot()["A"]
	assert state["B:s1"]["value"] == 20
	assert state["B:s1"]["origin"] == "B"


def test_tie_break_origin_lower_loses():
	w = make_worker()

	w.merge_update("s1", 10, 1000, "B")
	applied = w.merge_update("s1", 20, 1000, "A")

	assert applied is False
	state = w.get_state_snapshot()["A"]
	assert state["B:s1"]["value"] == 10
	assert state["B:s1"]["origin"] == "B"