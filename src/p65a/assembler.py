from copy import copy
from enum import Enum
from .symbolics import Expression, SymbolFactory, Symbol, Literal


class Mode(Enum):
	A = 0     #  A	Accumulator	OPC A	operand is AC (implied single byte instruction)
	ABS = 1   #  abs	absolute	OPC $LLHH	operand is address $HHLL *
	ABSX = 2  #  abs,X	absolute, X-indexed	OPC $LLHH,X	operand is address; effective address is address incremented by X with carry **
	ABSY = 3  #  abs,Y	absolute, Y-indexed	OPC $LLHH,Y	operand is address; effective address is address incremented by Y with carry **
	IMM = 4   #  	immediate	OPC #$BB	operand is byte BB
	IMPL = 5  #  impl	implied	OPC	operand implied
	IND = 6   #  ind	indirect	OPC ($LLHH)	operand is address; effective address is contents of word at address: C.w($HHLL)
	XIND = 7  #  X,ind	X-indexed, indirect	OPC ($LL,X)	operand is zeropage address; effective address is word in (LL + X, LL + X + 1), inc. without carry: C.w($00LL + X)
	INDY = 8  #  ind,Y	indirect, Y-indexed	OPC ($LL),Y	operand is zeropage address; effective address is word in (LL, LL + 1) incremented by Y with carry: C.w($00LL) + Y
	REL = 9   #  rel	relative	OPC $BB	branch target is PC + signed offset BB ***
	ZPG = 10  #  zpg	zeropage	OPC $LL	operand is zeropage address (hi-byte is zero, address = $00LL)
	ZPGX = 11 #  zpg,X	zeropage, X-indexed	OPC $LL,X	operand is zeropage address; effective address is address incremented by X without carry **
	ZPGY = 12 #  zpg,Y	zeropage, Y-indexed	OPC $LL,Y	operand is zeropage address; effective address is address incremented by Y without carry **


mode_lengths = {
	Mode.A:    1,
	Mode.ABS:  3,
	Mode.ABSX: 3,
	Mode.ABSY: 3,
	Mode.IMM:  2,
	Mode.IMPL: 1,
	Mode.IND:  3,
	Mode.XIND: 2,
	Mode.INDY: 2,
	Mode.REL:  2,
	Mode.ZPG:  2,
	Mode.ZPGX: 2,
	Mode.ZPGY: 2,
}


class Register:
	pass

class Areg(Register):
	def __le__(self, other):
		if type(other) is tuple:
			op = other[0]
			if op == "Axor":
				return EOR(other[1])
			elif op == "Aand":
				return AND(other[1])
			elif op == "A>>":
				return [LSR(A)] * other[1]
			elif op == "A<<":
				return [ASL(A)] * other[1]
			elif op == "Aadd":
				return ADC(other[1])
			elif op == "Asub":
				return SBC(other[1])
			elif op == "Aor":
				return ORA(other[1])
			else:
				raise Exception("bad op")
		
		if other is X:
			return TXA()
		elif other is Y:
			return TYA()
		return LDA(other)
	
	def __eq__(self, other):
		return CMP(other)

	# TODO: use special class instead of tuples
	def __xor__(self, other):
		return ("Axor", other)
	
	def __and__(self, other):
		return ("Aand", other)
	
	def __add__(self, other):
		return ("Aadd", other)
	
	def __sub__(self, other):
		return ("Asub", other)
	
	def __or__(self, other):
		return ("Aor", other)
	
	def __rshift__(self, other):
		return ("A>>", other)
	
	def __lshift__(self, other):
		return ("A<<", other)

class Xreg(Register):
	def __le__(self, other):
		if other is A:
			return TAX()
		return LDX(other)

class Yreg(Register):
	def __le__(self, other):
		if other is A:
			return TAY()
		return LDY(other)

A = Areg()
X = Xreg()
Y = Yreg()

class Address:
	def __init__(self, addr):
		self.addr = addr
	
	def get_concrete_addr(self, labels):
		if isinstance(self.addr, Expression):
			return self.addr.evaluate(labels)
		assert(type(self.addr) is int)
		return self.addr
	
	def __le__(self, other):
		if other is A:
			return STA(self)
		elif other is X:
			return STX(self)
		elif other is Y:
			return STY(self)
		else:
			raise Exception("I dunno how to store that")

class ZP(Address):
	def __getitem__(self, item):
		if item == 0:
			return ZPindY_partial(self.addr)
		if not isinstance(item, (Xreg, Yreg)):
			raise Exception(f"ZP can't be indexed by {item}")
		return ZPIndex(self.addr, item)

class ZPIndex(Address):
	def __init__(self, addr, index):
		self.addr = addr
		self.index = index
	
	def __getitem__(self, item):
		if isinstance(self.index, Xreg) and item == 0:
			return ZPXind(self.addr, self.index)
		raise Exception("too much indirection")

class ZPXind(ZPIndex):
	pass

class ZPindY_partial(Address):
	def __getitem__(self, item):
		if isinstance(item, Yreg):
			return ZPindY(self.addr, item)

class ZPindY(ZPIndex):
	pass



class Addr(Address):
	def __getitem__(self, item):
		if not isinstance(item, (Xreg, Yreg)):
			raise Exception(f"Addr can't be indexed by {item}")
		return AddrIndex(self.addr, item)
	
	def __call__(self):
		return JSR(self)


class AddrIndex(Address):
	def __init__(self, addr, index):
		self.addr = addr
		self.index = index

class Instruction:
	modes = {}
	address = None
	length = None

	def __init__(self, oper=None):
		if isinstance(oper, Expression):
			oper = oper.type(oper)
		
		# jank for indirect jmps
		if type(oper) is list and len(oper) == 1 and isinstance(oper[0], Expression):
			oper = [oper[0].type(oper[0])]
		
		self.oper = oper
		self.mode = self.determine_mode(oper)
		if self.mode == Mode.ABS and Mode.REL in self.modes:
			self.mode = Mode.REL
		if self.mode == Mode.IND:
			self.oper = self.oper[0]
		if self.mode not in self.modes:
			raise Exception(f"Unsupported mode {self.mode} for opcode {self.__class__.__name__}")
		self.length = mode_lengths[self.mode]
		self.encoding = bytes([self.modes[self.mode]])
	
	def determine_mode(self, oper):
		match oper:
			case None:
				return Mode.IMPL
			case Areg():
				return Mode.A
			case Addr():
				return Mode.ABS
			case [Address()]: # TODO: test this
				return Mode.IND
			case AddrIndex(index=Xreg()):
				return Mode.ABSX
			case AddrIndex(index=Yreg()):
				return Mode.ABSY
			case int():
				if oper >= 0x100:
					raise Exception(f"Immediate argument is too big: {oper}")
				return Mode.IMM
			case ZPXind():
				return Mode.XIND
			case ZPindY():
				return Mode.INDY
			case ZP():
				return Mode.ZPG
			case ZPIndex(index=Xreg()):
				return Mode.ZPGX
			case ZPIndex(index=Yreg()):
				return Mode.ZPGY
			case _:
				raise Exception(f"I don't recognise this addressing mode: {oper}")
	
	def assemble(self, labels={}):
		match self.mode:
			case Mode.A | Mode.IMPL:
				return self.encoding
			case Mode.ABS | Mode.ABSX | Mode.ABSY | Mode.IND:
				return self.encoding + self.oper.get_concrete_addr(labels).to_bytes(2, "little")
			case Mode.ZPG | Mode.ZPGX | Mode.ZPGY | Mode.XIND | Mode.INDY:
				return self.encoding + self.oper.get_concrete_addr(labels).to_bytes(1, "little")
			case Mode.IMM:
				return self.encoding + self.oper.to_bytes(1, "little") # TODO: symbolic immediates?
			case Mode.REL:
				offset = self.oper.get_concrete_addr(labels) - 2 - self.address
				return self.encoding + offset.to_bytes(1, "little", signed=True)
			case _:
				raise Exception("I dunno how to assemble that mode")

	def disas(self, labels={}):
		name = self.__class__.__name__
		# todo: attempt symbolification of addresses
		match self.mode:
			case Mode.A:
				return f"{name} A"
			case Mode.ABS | Mode.REL:
				return f"{name} ${self.oper.get_concrete_addr(labels):04x}"
			case Mode.ABSX:
				return f"{name} ${self.oper.get_concrete_addr(labels):04x},X"
			case Mode.ABSY:
				return f"{name} ${self.oper.get_concrete_addr(labels):04x},Y"
			case Mode.IMM:
				return f"{name} #${self.oper:02x}"
			case Mode.IMPL:
				return name
			case Mode.IND:
				return f"{name} (${self.oper.get_concrete_addr(labels):04x})"
			case Mode.XIND:
				return f"{name} (${self.oper.get_concrete_addr(labels):04x},X)"
			case Mode.INDY:
				return f"{name} (${self.oper.get_concrete_addr(labels):04x}),Y"
			case Mode.ZPG:
				return f"{name} ${self.oper.get_concrete_addr(labels):02x}"
			case Mode.ZPGX:
				return f"{name} ${self.oper.get_concrete_addr(labels):02x},X"
			case Mode.ZPGY:
				return f"{name} ${self.oper.get_concrete_addr(labels):02x},Y"
			case _:
				raise Exception("I dunno how to disas that")

	def __repr__(self):
		return f"{self.__class__.__name__}({self.mode}, {self.oper})"


# labels are pseudo-instructions of zero length
class Label(Instruction):
	length = 0

	def __init__(self, label):
		self.label = label

	def assemble(self, labels):
		return b""
	
	def disas(self, labels):
		return self.label + ":"

	def __repr__(self):
		return f"Label({self.label})"


class Org(Instruction):
	length = 0

	def __init__(self, addr):
		assert(type(addr) is int)
		self.address = addr
	
	def assemble(self, labels):
		return b""
	
	def disas(self, labels):
		return f".org ${self.address:04x}"
	
	def __repr__(self):
		return f"Org({hex(self.address)})"

class Dw(Instruction):
	length = 2

	def __init__(self, value):
		self.value = Addr(value)
	
	def assemble(self, labels):
		return self.value.get_concrete_addr(labels).to_bytes(2, "little")
	
	def disas(self, labels):
		return f".dw ${self.value.get_concrete_addr(labels):04x}"

	def __repr__(self):
		return f"Dw({self.value})"


class Db(Instruction):
	length = None

	def __init__(self, value):
		try:
			self.length = len(value)
			self.value = value
		except TypeError:
			self.length = 1
			self.value = [value]
	
	def concrete_value(self, labels):
		return bytes([Expression.cast(x).evaluate(labels) for x in self.value])

	def assemble(self, labels):
		return self.concrete_value(labels)
	
	def disas(self, labels):
		return f".db {repr(self.concrete_value(labels))[1:]}"

	def __repr__(self):
		return f"Db({self.value})"


class ADC(Instruction):
	modes = {
		Mode.IMM : 0x69,
		Mode.ZPG : 0x65,
		Mode.ZPGX: 0x75,
		Mode.ABS : 0x6D,
		Mode.ABSX: 0x7D,
		Mode.ABSY: 0x79,
		Mode.XIND: 0x61,
		Mode.INDY: 0x71,
	}

class AND(Instruction):
	modes = {
		Mode.IMM : 0x29,
		Mode.ZPG : 0x25,
		Mode.ZPGX: 0x35,
		Mode.ABS : 0x2D,
		Mode.ABSX: 0x3D,
		Mode.ABSY: 0x39,
		Mode.XIND: 0x21,
		Mode.INDY: 0x31,
	}

class ASL(Instruction):
	modes = {
		Mode.A   : 0x0A,
		Mode.ZPG : 0x06,
		Mode.ZPGX: 0x16,
		Mode.ABS : 0x0E,
		Mode.ABSX: 0x1E,
	}

class BCC(Instruction):
	modes = {
		Mode.REL : 0x90,
	}

class BCS(Instruction):
	modes = {
		Mode.REL : 0xB0,
	}

class BEQ(Instruction):
	modes = {
		Mode.REL : 0xF0,
	}

class BIT(Instruction):
	modes = {
		Mode.ZPG : 0x24,
		Mode.ABS : 0x2C,
	}

class BMI(Instruction):
	modes = {
		Mode.REL : 0x30,
	}

class BNE(Instruction):
	modes = {
		Mode.REL : 0xD0,
	}

class BPL(Instruction):
	modes = {
		Mode.REL : 0x10,
	}

class BRK(Instruction):
	modes = {
		Mode.IMPL: 0x00,
	}

class BVC(Instruction):
	modes = {
		Mode.REL : 0x50,
	}

class BVS(Instruction):
	modes = {
		Mode.REL : 0x70,
	}

class CLC(Instruction):
	modes = {
		Mode.IMPL: 0x18,
	}

class CLD(Instruction):
	modes = {
		Mode.IMPL: 0xD8,
	}

class CLI(Instruction):
	modes = {
		Mode.IMPL: 0x58,
	}

class CLV(Instruction):
	modes = {
		Mode.IMPL: 0xB8,
	}

class CMP(Instruction):
	modes = {
		Mode.IMM : 0xC9,
		Mode.ZPG : 0xC5,
		Mode.ZPGX: 0xD5,
		Mode.ABS : 0xCD,
		Mode.ABSX: 0xDD,
		Mode.ABSY: 0xD9,
		Mode.XIND: 0xC1,
		Mode.INDY: 0xD1,
	}

class CPX(Instruction):
	modes = {
		Mode.IMM : 0xE0,
		Mode.ZPG : 0xE4,
		Mode.ABS : 0xEC,
	}

class CPY(Instruction):
	modes = {
		Mode.IMM : 0xC0,
		Mode.ZPG : 0xC4,
		Mode.ABS : 0xCC,
	}

class DEC(Instruction):
	modes = {
		Mode.ZPG : 0xC6,
		Mode.ZPGX: 0xD6,
		Mode.ABS : 0xCE,
		Mode.ABSX: 0xDE,
	}

class DEX(Instruction):
	modes = {
		Mode.IMPL: 0xCA,
	}

class DEY(Instruction):
	modes = {
		Mode.IMPL: 0x88,
	}

class EOR(Instruction):
	modes = {
		Mode.IMM : 0x49,
		Mode.ZPG : 0x45,
		Mode.ZPGX: 0x55,
		Mode.ABS : 0x4D,
		Mode.ABSX: 0x5D,
		Mode.ABSY: 0x59,
		Mode.XIND: 0x41,
		Mode.INDY: 0x51,
	}

class INC(Instruction):
	modes = {
		Mode.ZPG : 0xE6,
		Mode.ZPGX: 0xF6,
		Mode.ABS : 0xEE,
		Mode.ABSX: 0xFE,
	}

class INX(Instruction):
	modes = {
		Mode.IMPL: 0xE8,
	}

class INY(Instruction):
	modes = {
		Mode.IMPL: 0xC8,
	}

class JMP(Instruction):
	modes = {
		Mode.ABS : 0x4C,
		Mode.IND : 0x6C,
	}

class JSR(Instruction):
	modes = {
		Mode.ABS : 0x20,
	}

class LDA(Instruction):
	modes = {
		Mode.IMM : 0xA9,
		Mode.ZPG : 0xA5,
		Mode.ZPGX: 0xB5,
		Mode.ABS : 0xAD,
		Mode.ABSX: 0xBD,
		Mode.ABSY: 0xB9,
		Mode.XIND: 0xA1,
		Mode.INDY: 0xB1,
	}

class LDX(Instruction):
	modes = {
		Mode.IMM : 0xA2,
		Mode.ZPG : 0xA6,
		Mode.ZPGY: 0xB6,
		Mode.ABS : 0xAE,
		Mode.ABSY: 0xBE,
	}

class LDY(Instruction):
	modes = {
		Mode.IMM : 0xA0,
		Mode.ZPG : 0xA4,
		Mode.ZPGX: 0xB4,
		Mode.ABS : 0xAC,
		Mode.ABSX: 0xBC,
	}

class LSR(Instruction):
	modes = {
		Mode.A   : 0x4A,
		Mode.ZPG : 0x46,
		Mode.ZPGX: 0x56,
		Mode.ABS : 0x4E,
		Mode.ABSX: 0x5E,
	}

class NOP(Instruction):
	modes = {
		Mode.IMPL: 0xEA,
	}

class ORA(Instruction):
	modes = {
		Mode.IMM : 0x09,
		Mode.ZPG : 0x05,
		Mode.ZPGX: 0x15,
		Mode.ABS : 0x0D,
		Mode.ABSX: 0x1D,
		Mode.ABSY: 0x19,
		Mode.XIND: 0x01,
		Mode.INDY: 0x11,
	}

class PHA(Instruction):
	modes = {
		Mode.IMPL: 0x48,
	}

class PHP(Instruction):
	modes = {
		Mode.IMPL: 0x08,
	}

class PLA(Instruction):
	modes = {
		Mode.IMPL: 0x68,
	}

class PLP(Instruction):
	modes = {
		Mode.IMPL: 0x28,
	}

class ROL(Instruction):
	modes = {
		Mode.A   : 0x2A,
		Mode.ZPG : 0x26,
		Mode.ZPGX: 0x36,
		Mode.ABS : 0x2E,
		Mode.ABSX: 0x3E,
	}

class ROR(Instruction):
	modes = {
		Mode.A   : 0x6A,
		Mode.ZPG : 0x66,
		Mode.ZPGX: 0x76,
		Mode.ABS : 0x6E,
		Mode.ABSX: 0x7E,
	}

class RTI(Instruction):
	modes = {
		Mode.IMPL: 0x40,
	}

class RTS(Instruction):
	modes = {
		Mode.IMPL: 0x60,
	}

class SBC(Instruction):
	modes = {
		Mode.IMM : 0xE9,
		Mode.ZPG : 0xE5,
		Mode.ZPGX: 0xF5,
		Mode.ABS : 0xED,
		Mode.ABSX: 0xFD,
		Mode.ABSY: 0xF9,
		Mode.XIND: 0xE1,
		Mode.INDY: 0xF1,
	}

class SEC(Instruction):
	modes = {
		Mode.IMPL: 0x38,
	}

class SED(Instruction):
	modes = {
		Mode.IMPL: 0xF8,
	}

class SEI(Instruction):
	modes = {
		Mode.IMPL: 0x78,
	}

class STA(Instruction):
	modes = {
		Mode.ZPG : 0x85,
		Mode.ZPGX: 0x95,
		Mode.ABS : 0x8D,
		Mode.ABSX: 0x9D,
		Mode.ABSY: 0x99,
		Mode.XIND: 0x81,
		Mode.INDY: 0x91,
	}

class STX(Instruction):
	modes = {
		Mode.ZPG : 0x86,
		Mode.ZPGY: 0x96,
		Mode.ABS : 0x8E,
	}

class STY(Instruction):
	modes = {
		Mode.ZPG : 0x84,
		Mode.ZPGX: 0x94,
		Mode.ABS : 0x8C,
	}

class TAX(Instruction):
	modes = {
		Mode.IMPL: 0xAA,
	}

class TAY(Instruction):
	modes = {
		Mode.IMPL: 0xA8,
	}

class TSX(Instruction):
	modes = {
		Mode.IMPL: 0xBA,
	}

class TXA(Instruction):
	modes = {
		Mode.IMPL: 0x8A,
	}

class TXS(Instruction):
	modes = {
		Mode.IMPL: 0x9A,
	}

class TYA(Instruction):
	modes = {
		Mode.IMPL: 0x98,
	}


orig_INC = INC # TODO: don't do this, lol - I just don't want to touch autogen'd code
# TODO: check the code generator into git

def INC(oper=None):
	if oper is X:
		return INX()
	elif oper is Y:
		return INY()
	return orig_INC(oper)

orig_DEC = DEC # likewise

def DEC(oper=None):
	if oper is X:
		return DEX()
	elif oper is Y:
		return DEY()
	return orig_DEC(oper)


class Allocator():
	def __init__(self, base=0, max=0xffff, addrtype=Addr):
		self.offset = base
		self.max = max
		self.addrtype = addrtype
	
	def alloc(self, size):
		if self.offset + size > self.max:
			raise Exception("Out of space")
		allocation = self.addrtype(self.offset)
		self.offset += size
		return allocation


zp = SymbolFactory(type=ZP)
lbl = SymbolFactory(type=Addr)


def flatten(S):
	if S == []:
		return S
	if isinstance(S[0], list):
		return flatten(S[0]) + flatten(S[1:])
	return S[:1] + flatten(S[1:])


def concretise(program, base=0):
	program = flatten(program)
	prog_out = []
	labels = {}
	current_addr = base
	for instr in program:
		if type(instr) is Symbol:
			labels[instr.name] = current_addr
			instr = Label(instr.name)
		else:
			instr = copy(instr)
		
		if type(instr) == Org:
			current_addr = instr.address
		else:
			instr.address = current_addr
		
		current_addr += instr.length
		prog_out.append(instr)
	
	return prog_out, labels

def assemble(program, labels):
	memory = bytearray(0x10000)
	for instr in program:
		memory[instr.address:instr.address+instr.length] = instr.assemble(labels)
	return memory


def make_listing(program, labels):
	listing = []
	for instr in program:
		listing.append(f"${instr.address:04x}:  {instr.assemble(labels).hex()}\t{instr.disas(labels)}")
	return "\n".join(listing)


if __name__ == "__main__":
	allocator = Allocator(base=0x200)
	zpallocator = Allocator(max=0xff, addrtype=ZP)

	zpallocator.alloc(0x37)
	allocator.alloc(0x1234)

	zpvar = zpallocator.alloc(2)
	var = allocator.alloc(2)

	print(ADC(0x10))
	print(ADC(zpvar))
	print(ADC(zpvar[X]))
	print(ADC(var))
	print(ADC(var[X]))
	print(ADC(var[Y]))
	print(ADC(zpvar[X][0]))
	print(ADC(zpvar[0][Y]))
	print(TYA())

	print(ADC(0x10).assemble().hex())
	print(ADC(zpvar).assemble().hex())
	print(ADC(zpvar[X]).assemble().hex())
	print(ADC(var).assemble().hex())
	print(ADC(var[X]).assemble().hex())
	print(ADC(var[Y]).assemble().hex())
	print(ADC(zpvar[X][0]).assemble().hex())
	print(ADC(zpvar[0][Y]).assemble().hex())
	print(TYA().assemble().hex())
