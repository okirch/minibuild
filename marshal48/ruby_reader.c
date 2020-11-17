/*
reader object for ruby unmarshal code

Copyright (C) 2020 SUSE

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
*/

#include <assert.h>
#include <stdarg.h>
#include <Python.h>
#include <structmember.h>

#include "extension.h"
#include "ruby_impl.h"

enum {
	RUBY_READER_OKAY = 0,
	RUBY_READER_EOF = -1,
	RUBY_READER_ERROR = -2,
};


struct ruby_iobuf;
extern void			ruby_iobuf_init(struct ruby_iobuf *bp);
extern void			ruby_iobuf_clear(struct ruby_iobuf *bp);
extern void			ruby_iobuf_destroy(struct ruby_iobuf *bp);

struct ruby_io {
	PyObject *		io;

	struct ruby_iobuf {
		unsigned int	pos;
		unsigned int	count;
		unsigned char	_data[1024];
	} buffer;
};


ruby_io_t *
ruby_io_new(PyObject *io)
{
	ruby_io_t *reader = calloc(1, sizeof(*reader));

	Py_INCREF(io);
	reader->io = io;

	return reader;
}

void
ruby_io_free(ruby_io_t *reader)
{
	drop_object(&reader->io);
	free(reader);
}

/*
 * Manage the buffer object
 */
void
ruby_iobuf_init(struct ruby_iobuf *bp)
{
	memset(bp, 0, sizeof(*bp));
}

void
ruby_iobuf_clear(struct ruby_iobuf *bp)
{
	bp->pos = bp->count = 0;
	memset(bp->_data, 0, sizeof(bp->_data));
}

void
ruby_iobuf_destroy(struct ruby_iobuf *bp)
{
	ruby_iobuf_init(bp);
}

int
ruby_io_fillbuf(ruby_io_t *reader)
{
	struct ruby_iobuf *bp = &reader->buffer;
	PyObject *b;

	memset(bp, 0, sizeof(*bp));

	b = PyObject_CallMethod(reader->io, "read", "i", sizeof(bp->_data));
	if (b == NULL)
		return RUBY_READER_ERROR;

	bp->pos = 0;
	if (PyBytes_Check(b)) {
		bp->count = PyBytes_GET_SIZE(b);

		assert(bp->count <= sizeof(bp->_data));
		memcpy(bp->_data, PyBytes_AS_STRING(b), bp->count);
	} else {
		bp->count = PyByteArray_GET_SIZE(b);

		assert(bp->count <= sizeof(bp->_data));
		memcpy(bp->_data, PyByteArray_AS_STRING(b), bp->count);
	}

	Py_DECREF(b);
	return RUBY_READER_OKAY;
}

int
__ruby_io_nextc(ruby_io_t *reader)
{
	struct ruby_iobuf *bp = &reader->buffer;

	if (bp->pos >= bp->count) {
		if (ruby_io_fillbuf(reader) < 0)
			return RUBY_READER_ERROR;
		if (bp->count == 0)
			return RUBY_READER_EOF;
	}

	return bp->_data[bp->pos++];
}

inline bool
ruby_io_nextc(ruby_io_t *reader, int *cccp)
{
	*cccp = __ruby_io_nextc(reader);
	if (*cccp < 0) {
		/* unmarshal_raise_exception(*cccp); */
		return false;
	}

	return true;
}

bool
ruby_io_nextw(ruby_io_t *reader, unsigned int count, long *resultp)
{
	unsigned int shift = 0;

	*resultp = 0;

	/* little endian byte order */
	for (shift = 0; count; --count, shift += 8) {
		int cc;

		if (!ruby_io_nextc(reader, &cc))
			return false;

		*resultp += (cc << shift);
	}

	return true;
}

bool
ruby_io_next_byteseq(ruby_io_t *reader, unsigned int count, ruby_byteseq_t *seq)
{
	struct ruby_iobuf *bp = &reader->buffer;

	assert(seq->count == 0);

	while (seq->count < count) {
		long copy;

		/* refill buffer if empty */
		if (bp->pos >= bp->count) {
			if (ruby_io_fillbuf(reader) < 0) {
				fprintf(stderr, "Read error");
				return false;
			}
		}

		copy = count - seq->count;
		if (bp->pos + copy > bp->count)
			copy = bp->count - bp->pos;

		ruby_byteseq_append(seq, bp->_data + bp->pos, copy);
		bp->pos += copy;
	}

	return true;
}

bool
ruby_io_flushbuf(ruby_io_t *writer)
{
	struct ruby_iobuf *bp = &writer->buffer;
	PyObject *b, *r;

	b = PyBytes_FromStringAndSize((const char *) bp->_data, bp->count);

	r = PyObject_CallMethod(writer->io, "write", "O", b);
	Py_DECREF(b);

	if (r == NULL) {
		/* Display exception? */
		return false;
	}

	Py_DECREF(r);

	memset(bp, 0, sizeof(*bp));
	return true;
}

bool
ruby_io_putc(ruby_io_t *writer, int cc)
{
	struct ruby_iobuf *bp = &writer->buffer;

	if (bp->count >= sizeof(bp->_data)) {
		if (!ruby_io_flushbuf(writer))
			return false;
	}

	bp->_data[bp->count++] = cc;
	return true;
}

