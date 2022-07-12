import sys
sys.path.append("../src/") # jank to allow running in-tree

"""
This is a serial bootloader program for my 6502 SBC
"""

from p65a import *
import crcmod
crc16 = crcmod.predefined.mkCrcFun("xmodem")

UART_CTRL = Literal(0xa000, type=Addr)
UART_DATA = Literal(0xa001, type=Addr)

program = [
	Org(0x0000),
	zp.crc,
	zp.crc_lo,
		Db(0),
	zp.crc_hi,
		Db(0),

	zp.cmd,
		Db(0),
	zp.cmdlen,
		Db(0),
	zp.cmdbuf,
		Db([0]*32), # 32 bytes ought to be enough for anyone...

	Org(0xc000),

	lbl.uart_init, # clobbers: A
		A <= 0b11, # master reset
		UART_CTRL <= A,

		A <= 0b0_00_101_01,
		UART_CTRL <= A,  # no interrupts, 8N1, divide clock by 16 (250000 baud)

		RTS(),

	lbl.putchar, # input: A, clobbers: A
		PHA(),
	lbl.wait_to_send,
		A <= UART_CTRL,
		A <= A & 0b10,
		BEQ(lbl.wait_to_send),
		PLA(),
		UART_DATA <= A,
		RTS(),

	lbl.getchar, # output: A, clobbers: A
		A <= UART_CTRL,
		A <= A & 1,
		BEQ(lbl.getchar),
		A <= UART_DATA,
		RTS(),

	lbl.HEX,
		Db(b"0123456789abcdef"),

	lbl.puthex, # input: A, clobbers: A, X, Y
		X <= A,
		A <= A >> 4,
		Y <= A,
		A <= lbl.HEX[Y],
		lbl.putchar(),
		A <= X,
		A <= A & 0x0f,
		Y <= A,
		A <= lbl.HEX[Y],
		lbl.putchar(),
		RTS(),

	# TODO: alignment
	lbl.CRC_LUT_HI,
		Db([crc16(bytes([i])) >> 8 for i in range(0x100)]),
	lbl.CRC_LUT_LO,
		Db([crc16(bytes([i])) & 0xff for i in range(0x100)]),

	lbl.crc_update, # input: A, clobbers: A, Y
		A <= A ^ zp.crc_hi,
		Y <= A,
		A <= zp.crc_lo,
		A <= A  ^ lbl.CRC_LUT_HI[Y],
		zp.crc_hi <= A,
		A <= lbl.CRC_LUT_LO[Y],
		zp.crc_lo <= A,
		RTS(),


	lbl.start,
		lbl.uart_init(),
		X <= 0,
	lbl.helloloop,
		A <= lbl.hello[X],
		BEQ(lbl.recv_cmd_loop),
		lbl.putchar(),
		INC(X),
		JMP(lbl.helloloop),
	
	lbl.recv_cmd_loop,

		lbl.getchar(),
		zp.cmd <= A,

		lbl.getchar(),
		zp.cmdlen <= A,

		# zero the crc accumulator
		A <= 0,
		zp.crc_lo <= A,
		zp.crc_hi <= A,

		# note: timing is pretty tight in this loop,
		# we have ~160 cycles for each iteration before the receive buffer would
		# overflow
		X <= 0, # X tracks the number of bytes received
	lbl.recvloop,
		A <= X,
		A == zp.cmdlen,
		BEQ(lbl.recvloopdone),
		lbl.getchar(),
		zp.cmdbuf[X] <= A,
		lbl.crc_update(), # note: this clobbers Y
		INC(X),
		JMP(lbl.recvloop),


	lbl.recvloopdone,
		lbl.getchar(), # crc
		A == zp.crc_lo,
		BNE(lbl.badcrclo),
		lbl.getchar(),
		A == zp.crc_hi,
		BNE(lbl.badcrchi),

		# note: command handlers are responsible for ack'ing
		JMP(lbl.handle_cmd),

	lbl.badcrclo,
		lbl.getchar(), # eat second char
	lbl.badcrchi,
		A <= 0x01,
		lbl.putchar(), # nak
		JMP(lbl.recv_cmd_loop),


	lbl.handle_cmd,
		A <= 0,
		A == zp.cmd,
		BEQ(lbl.handle_cmd_write),

		A <= 1,
		A == zp.cmd,
		BEQ(lbl.handle_cmd_exec),

		# fallthru
	lbl.badcmd,
		# bad command
		A <= 0x02,
		lbl.putchar(),
		JMP(lbl.recv_cmd_loop),

	lbl.handle_cmd_write,
		A <= zp.cmdlen,
		A == 3,
		BNE(lbl.badcmd),

		# zero the crc accumulator
		A <= 0,
		zp.crc_lo <= A,
		zp.crc_hi <= A,

		A <= 0x00, # ack
		lbl.putchar(),

	# same 160-cycle constraint applies here
		X <= 0xff, # will become 0 after first inc
	lbl.writeloop,
		INC(X),
		A <= X,
		Y <= A, # copy X to Y so we can use zp-indirect-y adressing
		lbl.getchar(),
		zp.cmdbuf[0][Y] <= A,
		lbl.crc_update(), # clobbers Y
		A <= X,
		A == zp.cmdbuf + 2,
		BNE(lbl.writeloop),
		# fallthru

	lbl.writedone,
		A <= zp.crc_lo,
		lbl.putchar(),
		A <= zp.crc_hi,
		lbl.putchar(),

		JMP(lbl.recv_cmd_loop),

	lbl.handle_cmd_exec,
		A <= zp.cmdlen,
		A == 2,
		BNE(lbl.badcmd),

		A <= 0x00, # ack
		lbl.putchar(),

		lbl.exec_trampoline(), # make this a call so the program can return
		JMP(lbl.recv_cmd_loop),
	
	lbl.exec_trampoline,
		JMP([zp.cmdbuf]),

	lbl.hello,
		Db(b"HELLO\r\n\0"),


	Org(0xfffc),
		Dw(lbl.start)
]


concrete_prog, labels = concretise(program)
out = assemble(concrete_prog, labels)
rom = out[0xc000:]
open("rom.bin", "wb").write(rom)

print(make_listing(concrete_prog, labels))
