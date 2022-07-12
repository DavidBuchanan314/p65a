# p65a
Pythonic 6502 Assembler: An experimental alternative to traditional assemblers.

At this point I'm unsure whether it's a useful concept or not, but I quite enjoy
writing code this way. Consider the API to be unstable.

See the `examples/` directory for examples of code written using this library.

Here's a snippet from `examples/bootloader.py`, which showcases a few nice features:

```python
[...,
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
...]
```

This snippet implements a CRC16 checksum function. The lookup tables are generated
automagically by Python list comprehensions.
Each "line" of assembly is an expression contained within a Python list. The
`<=` operator is overloaded to express assignment.

It is possible to make forward-references to labels. They are treated as symbolic
expressions until the layout of code is known (and thus, their concrete value),
and then the machine code can finally be finally emitted.

## TODO

- Make an installable package
- Put it on pypi
- Refactor - there's a lot of code in places it shouldn't be
- Documentation
