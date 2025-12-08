import random
from sensors.base_sensor import BaseSensor

class SpikeSensor(BaseSensor):
	def __init__(self, sensor_id, baseline, spike_height, p_spike, period_ms, callback=None):
		super().__init__(sensor_id, period_ms, callback)
		self.baseline = baseline
		self.spike_height = spike_height
		self.p_spike = p_spike

	def generate_value(self):
		if random.random() < self.p_spike:
			return self.baseline + self.spike_height
		return self.baseline
