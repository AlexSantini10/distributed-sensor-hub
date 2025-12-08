class SensorOutput:
	def __init__(self, type_name, value, unit=None):
		self.type = type_name			# numeric | boolean | categorical
		self.value = value				# produced value
		self.unit = unit				# optional unit

	def to_dict(self):
		return {
			"type": self.type,
			"value": self.value,
			"unit": self.unit
		}


class NumericOutput(SensorOutput):
	def __init__(self, value, unit=None):
		super().__init__("numeric", value, unit)


class BooleanOutput(SensorOutput):
	def __init__(self, value):
		super().__init__("boolean", value)


class CategoricalOutput(SensorOutput):
	def __init__(self, value):
		super().__init__("categorical", value)
