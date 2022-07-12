import operator
from abc import ABC, abstractmethod


class Expression(ABC):
	type = None

	@staticmethod
	def cast(value):
		if isinstance(value, Expression):
			return value
		return Literal(value)

	def __mul__(self, other):
		return BinaryOp(operator.mul, self, other)

	def __add__(self, other):
		return BinaryOp(operator.add, self, other)

	def __sub__(self, other):
		return BinaryOp(operator.sub, self, other)

	def __neg__(self):
		return UnaryOp(operator.neg, self)

	def __rshift__(self, other):
		return BinaryOp(operator.rshift, self, other)

	def __lshift__(self, other):
		return BinaryOp(operator.lshift, self, other)

	def __and__(self, other):
		return BinaryOp(operator.and_, self, other)

	# this is a hack to allow LDA(foo[X]) syntax etc.
	def __getitem__(self, item):
		return self.type(self)[item]
	
	def __le__(self, other):
		return self.type(self) <= other
	
	def __call__(self):
		return self.type(self)()

	@abstractmethod
	def evaluate(self, symbols):
		"""`symbols` should be a dictionary mapping symbols to values
		(which may or may not be expressions themselves).
		Should return a numeric value"""


class UnaryOp(Expression):
	def __init__(self, operator, operand):
		self.operator = operator
		self.operand = Expression.cast(operand)
		self.type = self.operand.type

	def evaluate(self, symbols):
		return self.operator(self.operand.evaluate(symbols))


class BinaryOp(Expression):
	def __init__(self, operator, left, right):
		self.operator = operator
		self.left = Expression.cast(left)
		self.right = Expression.cast(right)

		# propagate type info if present, giving priority to the type of the lval
		self.type = self.right.type if self.left.type is None else self.left.type

	def evaluate(self, symbols):
		return self.operator(
			self.left.evaluate(symbols),
			self.right.evaluate(symbols)
		)


class Literal(Expression):
	def __init__(self, value, type=None):
		self.value = int(value)  # we only support int literals, for now
		self.type = type

	def evaluate(self, symbols):
		_ = symbols  # unused
		return self.value


class Symbol(Expression):
	def __init__(self, name, type=None):
		self.name = name
		self.type = type

	def evaluate(self, symbols):
		return Expression.cast(symbols[self.name]).evaluate(symbols)


class SymbolFactory:
	def __init__(self, type=None):
		self.type = type

	def __getattribute__(self, name):
		# we can't just do self.type because that'd call __getattribute__
		# and then we'd get infinite recursion...
		type_ = object.__getattribute__(self, "type")
		return Symbol(name, type=type_)


if __name__ == "__main__":
	sym = SymbolFactory(type="foobar")

	expression = sym.x * 5 + 9 - 2

	print(7 * 5 + 9 - 2)
	print(expression.evaluate({"x": 7}))
	print(expression.type)
