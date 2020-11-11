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


struct ruby_read_buffer;
extern void			ruby_read_buffer_init(struct ruby_read_buffer *bp);
extern void			ruby_read_buffer_clear(struct ruby_read_buffer *bp);
extern void			ruby_read_buffer_destroy(struct ruby_read_buffer *bp);

struct ruby_reader {
	PyObject *		io;

	struct ruby_read_buffer {
		unsigned int	pos;
		unsigned int	count;
		unsigned char	_data[1024];
	} buffer;
};


ruby_reader_t *
ruby_reader_new(PyObject *io)
{
	ruby_reader_t *reader = calloc(1, sizeof(*reader));

	Py_INCREF(io);
	reader->io = io;

	return reader;
}

void
ruby_reader_free(ruby_reader_t *reader)
{
	drop_object(&reader->io);
	free(reader);
}

/*
 * Manage the buffer object
 */
void
ruby_read_buffer_init(struct ruby_read_buffer *bp)
{
	memset(bp, 0, sizeof(*bp));
}

void
ruby_read_buffer_clear(struct ruby_read_buffer *bp)
{
	bp->pos = bp->count = 0;
	memset(bp->_data, 0, sizeof(bp->_data));
}

void
ruby_read_buffer_destroy(struct ruby_read_buffer *bp)
{
	ruby_read_buffer_init(bp);
}

int
ruby_reader_fillbuf(ruby_reader_t *reader)
{
	struct ruby_read_buffer *bp = &reader->buffer;
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
__ruby_reader_nextc(ruby_reader_t *reader)
{
	struct ruby_read_buffer *bp = &reader->buffer;

	if (bp->pos >= bp->count) {
		if (ruby_reader_fillbuf(reader) < 0)
			return RUBY_READER_ERROR;
		if (bp->count == 0)
			return RUBY_READER_EOF;
	}

	return bp->_data[bp->pos++];
}

inline bool
ruby_reader_nextc(ruby_reader_t *reader, int *cccp)
{
	*cccp = __ruby_reader_nextc(reader);
	if (*cccp < 0) {
		/* unmarshal_raise_exception(*cccp); */
		return false;
	}

	return true;
}

bool
ruby_reader_nextw(ruby_reader_t *reader, unsigned int count, long *resultp)
{
	unsigned int shift = 0;

	*resultp = 0;

	/* little endian byte order */
	for (shift = 0; count; --count, shift += 8) {
		int cc;

		if (!ruby_reader_nextc(reader, &cc))
			return false;

		*resultp += (cc << shift);
	}

	return true;
}

bool
ruby_reader_next_byteseq(ruby_reader_t *reader, unsigned int count, ruby_byteseq_t *seq)
{
	struct ruby_read_buffer *bp = &reader->buffer;

	assert(seq->count == 0);

	while (seq->count < count) {
		long copy;

		/* refill buffer if empty */
		if (bp->pos >= bp->count) {
			if (ruby_reader_fillbuf(reader) < 0) {
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

